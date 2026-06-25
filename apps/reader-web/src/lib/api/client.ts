import type { components, paths } from "./generated/schema";

type ApiMethod = "get" | "post";

type PathsWithMethod<Method extends ApiMethod> = {
  [Path in keyof paths]: paths[Path] extends Record<Method, infer Operation>
    ? Operation extends never
      ? never
      : Path
    : never;
}[keyof paths] &
  string;

type OperationFor<Path extends keyof paths, Method extends ApiMethod> = paths[Path] extends Record<
  Method,
  infer Operation
>
  ? Operation
  : never;

type JsonSuccess<Operation> = Operation extends { responses: infer Responses }
  ? Responses extends { 200: { content: { "application/json": infer Body } } }
    ? Body
    : unknown
  : unknown;

type JsonRequestBody<Operation> = Operation extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? Body
  : never;

export type ApiRequestInit = Omit<RequestInit, "body" | "credentials" | "method">;
export type ArticleAskRequest = components["schemas"]["AskRequest"];

type ApiErrorOptions = {
  status: number;
  code: string;
  message: string;
  details?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor({ status, code, message, details = {} }: ApiErrorOptions) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function apiGet<Path extends PathsWithMethod<"get">>(
  path: Path,
  init?: ApiRequestInit,
): Promise<JsonSuccess<OperationFor<Path, "get">>>;
export async function apiGet<ResponseBody = unknown>(
  path: string,
  init?: ApiRequestInit,
): Promise<ResponseBody>;
export async function apiGet<ResponseBody = unknown>(
  path: string,
  init: ApiRequestInit = {},
): Promise<ResponseBody> {
  const response = await fetch(sameOriginPath(path), {
    ...init,
    method: "GET",
    credentials: "include",
    headers: buildHeaders(init.headers, { accept: "application/json" }),
  });
  return parseJsonResponse<ResponseBody>(response);
}

export async function apiPost<Path extends PathsWithMethod<"post">>(
  path: Path,
  body?: JsonRequestBody<OperationFor<Path, "post">>,
  init?: ApiRequestInit,
): Promise<JsonSuccess<OperationFor<Path, "post">>>;
export async function apiPost<ResponseBody = unknown, RequestBody = unknown>(
  path: string,
  body?: RequestBody,
  init?: ApiRequestInit,
): Promise<ResponseBody>;
export async function apiPost<ResponseBody = unknown, RequestBody = unknown>(
  path: string,
  body?: RequestBody,
  init: ApiRequestInit = {},
): Promise<ResponseBody> {
  const hasBody = body !== undefined;
  const response = await fetch(sameOriginPath(path), {
    ...init,
    method: "POST",
    credentials: "include",
    headers: buildHeaders(
      init.headers,
      hasBody
        ? {
            accept: "application/json",
            "content-type": "application/json",
          }
        : { accept: "application/json" },
    ),
    body: hasBody ? JSON.stringify(body) : undefined,
  });
  return parseJsonResponse<ResponseBody>(response);
}

export async function* streamArticleAsk(
  articleId: number,
  body: ArticleAskRequest,
  init: ApiRequestInit = {},
): AsyncGenerator<string> {
  if (!Number.isInteger(articleId) || articleId <= 0) {
    throw new TypeError("articleId must be a positive integer");
  }

  const response = await fetch(sameOriginPath(`/api/articles/${articleId}/ask`), {
    ...init,
    method: "POST",
    credentials: "include",
    headers: buildHeaders(init.headers, {
      accept: "text/event-stream",
      "content-type": "application/json",
    }),
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!isEventStreamContentType(contentType)) {
    await response.body?.cancel();
    throw new ApiError({
      status: response.status,
      code: "invalid_response",
      message: `Expected SSE response from API, got ${contentType || "empty content-type"}`,
      details: { contentType },
    });
  }
  if (!response.body) {
    throw new ApiError({
      status: response.status,
      code: "invalid_response",
      message: "Expected streaming API response body",
    });
  }

  yield* parseSseTextStream(response.body);
}

function sameOriginPath(path: string): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new TypeError("API path must be same-origin relative");
  }
  return path;
}

function buildHeaders(baseHeaders: HeadersInit | undefined, defaults: Record<string, string>): Headers {
  const headers = new Headers(baseHeaders);
  for (const [name, value] of Object.entries(defaults)) {
    if (!headers.has(name)) {
      headers.set(name, value);
    }
  }
  return headers;
}

async function parseJsonResponse<ResponseBody>(response: Response): Promise<ResponseBody> {
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  if (response.status === 204) {
    return undefined as ResponseBody;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!isJsonContentType(contentType)) {
    throw new ApiError({
      status: response.status,
      code: "invalid_response",
      message: `Expected JSON response from API, got ${contentType || "empty content-type"}`,
      details: { contentType },
    });
  }

  try {
    return (await response.json()) as ResponseBody;
  } catch (cause) {
    throw new ApiError({
      status: response.status,
      code: "invalid_response",
      message: "Expected valid JSON response from API",
      details: { contentType, cause: cause instanceof Error ? cause.message : String(cause) },
    });
  }
}

async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("content-type") ?? "";
  if (isJsonContentType(contentType)) {
    try {
      const payload = (await response.json()) as unknown;
      const envelope = apiErrorEnvelope(payload);
      if (envelope) {
        return new ApiError({
          status: response.status,
          code: envelope.code,
          message: envelope.message,
          details: envelope.details,
        });
      }
      return new ApiError({
        status: response.status,
        code: `http_${response.status}`,
        message: response.statusText || `API request failed with status ${response.status}`,
        details: payload,
      });
    } catch (cause) {
      return new ApiError({
        status: response.status,
        code: "invalid_response",
        message: "API error response was not valid JSON",
        details: { contentType, cause: cause instanceof Error ? cause.message : String(cause) },
      });
    }
  }

  const body = await response.text();
  return new ApiError({
    status: response.status,
    code: `http_${response.status}`,
    message: response.statusText || `API request failed with status ${response.status}`,
    details: { contentType, body: body.slice(0, 500) },
  });
}

function apiErrorEnvelope(payload: unknown): { code: string; message: string; details: unknown } | null {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return null;
  }
  const { code, message, details } = payload.error;
  if (typeof code !== "string" || typeof message !== "string") {
    return null;
  }
  return { code, message, details: details ?? {} };
}

function isJsonContentType(contentType: string): boolean {
  return /\bapplication\/(?:[\w.+-]+\+)?json\b/i.test(contentType);
}

function isEventStreamContentType(contentType: string): boolean {
  return /\btext\/event-stream\b/i.test(contentType);
}

async function* parseSseTextStream(stream: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = normalizeLineBreaks(buffer);

      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const frame = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const parsed = parseSseFrame(frame);
        if (parsed.done) {
          return;
        }
        if (parsed.text !== null) {
          yield parsed.text;
        }
        separatorIndex = buffer.indexOf("\n\n");
      }

      if (done) {
        break;
      }
    }

    if (buffer.trim()) {
      const parsed = parseSseFrame(buffer);
      if (!parsed.done && parsed.text !== null) {
        yield parsed.text;
      }
    }
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}

function parseSseFrame(frame: string): { done: boolean; text: string | null } {
  let eventName = "message";
  const data: string[] = [];

  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    const colonIndex = line.indexOf(":");
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
    const rawValue = colonIndex === -1 ? "" : line.slice(colonIndex + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;

    if (field === "event") {
      eventName = value;
    } else if (field === "data") {
      data.push(value);
    }
  }

  if (eventName === "done") {
    return { done: true, text: null };
  }
  return { done: false, text: data.length > 0 ? data.join("\n") : null };
}

function normalizeLineBreaks(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
