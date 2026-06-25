import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, apiGet, apiPost, streamArticleAsk } from "./client";

function withMockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response,
): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler as typeof fetch;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

function streamFromStrings(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function openStreamFromStrings(chunks: string[]): { stream: ReadableStream<Uint8Array>; wasCanceled: () => boolean } {
  const encoder = new TextEncoder();
  let canceled = false;
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
    },
    cancel() {
      canceled = true;
    },
  });

  return { stream, wasCanceled: () => canceled };
}

async function collectChunks(chunks: AsyncIterable<string>): Promise<string[]> {
  const collected: string[] = [];
  for await (const chunk of chunks) {
    collected.push(chunk);
  }
  return collected;
}

function headerValue(headers: HeadersInit | undefined, name: string): string | null {
  if (!headers) {
    return null;
  }
  return new Headers(headers).get(name);
}

test("apiGet returns JSON from same-origin requests with cookies", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });

  try {
    const result = await apiGet<{ ok: boolean }>("/api/healthz");

    assert.deepEqual(result, { ok: true });
    assert.equal(capturedInput, "/api/healthz");
    assert.equal(capturedInit?.method, "GET");
    assert.equal(capturedInit?.credentials, "include");
  } finally {
    restoreFetch();
  }
});

test("apiPost normalizes API error envelopes", async () => {
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((_input, init) => {
    capturedInit = init;
    return new Response(
      JSON.stringify({
        error: {
          code: "content_required",
          message: "Article content is required before asking",
          details: { article_id: 42 },
        },
      }),
      {
        status: 409,
        headers: { "content-type": "application/json" },
      },
    );
  });

  try {
    await assert.rejects(
      apiPost<unknown, { question: string }>("/api/articles/42/ask", { question: "总结" }),
      (error) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.status, 409);
        assert.equal(error.code, "content_required");
        assert.equal(error.message, "Article content is required before asking");
        assert.deepEqual(error.details, { article_id: 42 });
        return true;
      },
    );
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.credentials, "include");
    assert.equal(headerValue(capturedInit?.headers, "content-type"), "application/json");
    assert.equal(capturedInit?.body, JSON.stringify({ question: "总结" }));
  } finally {
    restoreFetch();
  }
});

test("apiGet normalizes non-JSON responses", async () => {
  const restoreFetch = withMockFetch(() => {
    return new Response("<html>not json</html>", {
      status: 200,
      headers: { "content-type": "text/html" },
    });
  });

  try {
    await assert.rejects(apiGet("/api/healthz"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 200);
      assert.equal(error.code, "invalid_response");
      assert.match(error.message, /Expected JSON response/);
      assert.deepEqual(error.details, { contentType: "text/html" });
      return true;
    });
  } finally {
    restoreFetch();
  }
});

test("apiGet rejects absolute API URLs", async () => {
  await assert.rejects(apiGet("https://example.com/api/healthz"), {
    name: "TypeError",
    message: "API path must be same-origin relative",
  });
});

test("apiPost rejects protocol-relative API URLs", async () => {
  await assert.rejects(apiPost("//example.com/api/healthz", {}), {
    name: "TypeError",
    message: "API path must be same-origin relative",
  });
});

test("apiPost supports bodyless POST requests", async () => {
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((_input, init) => {
    capturedInit = init;
    return new Response(null, { status: 204 });
  });

  try {
    const result = await apiPost("/api/auth/logout");

    assert.equal(result, undefined);
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.credentials, "include");
    assert.equal(headerValue(capturedInit?.headers, "content-type"), null);
    assert.equal(capturedInit?.body, undefined);
  } finally {
    restoreFetch();
  }
});

test("streamArticleAsk assembles SSE chunks until done", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(
      streamFromStrings([
        "data: Hel",
        "lo\n\n",
        "data:  wor",
        "ld\n\n",
        "event: done\n",
        "data: {}\n\n",
        "data: ignored\n\n",
      ]),
      {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      },
    );
  });

  try {
    const chunks = await collectChunks(
      streamArticleAsk(99, {
        question: "解释这段",
        selected_text: "Important quote",
      }),
    );

    assert.deepEqual(chunks, ["Hello", " world"]);
    assert.equal(chunks.join(""), "Hello world");
    assert.equal(capturedInput, "/api/articles/99/ask");
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.credentials, "include");
    assert.equal(headerValue(capturedInit?.headers, "accept"), "text/event-stream");
    assert.equal(headerValue(capturedInit?.headers, "content-type"), "application/json");
    assert.equal(capturedInit?.body, JSON.stringify({ question: "解释这段", selected_text: "Important quote" }));
  } finally {
    restoreFetch();
  }
});

test("streamArticleAsk cancels the response body after done before later frames", async () => {
  const { stream, wasCanceled } = openStreamFromStrings([
    "data: first\n\n",
    "event: done\n",
    "data: {}\n\n",
    "data: ignored\n\n",
  ]);
  const restoreFetch = withMockFetch(() => {
    return new Response(stream, {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    });
  });

  try {
    const chunks = await collectChunks(streamArticleAsk(99, { question: "总结" }));

    assert.deepEqual(chunks, ["first"]);
    assert.equal(wasCanceled(), true);
  } finally {
    restoreFetch();
  }
});

test("streamArticleAsk cancels the response body when the consumer stops early", async () => {
  const { stream, wasCanceled } = openStreamFromStrings(["data: first\n\n", "data: second\n\n"]);
  const restoreFetch = withMockFetch(() => {
    return new Response(stream, {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    });
  });

  try {
    const chunks = streamArticleAsk(99, { question: "总结" });
    assert.deepEqual(await chunks.next(), { done: false, value: "first" });

    await chunks.return(undefined);

    assert.equal(wasCanceled(), true);
  } finally {
    restoreFetch();
  }
});

test("streamArticleAsk rejects successful non-SSE responses", async () => {
  const restoreFetch = withMockFetch(() => {
    return new Response("<html>not an event stream</html>", {
      status: 200,
      headers: { "content-type": "text/html" },
    });
  });

  try {
    await assert.rejects(collectChunks(streamArticleAsk(99, { question: "总结" })), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 200);
      assert.equal(error.code, "invalid_response");
      assert.match(error.message, /Expected SSE response/);
      assert.deepEqual(error.details, { contentType: "text/html" });
      return true;
    });
  } finally {
    restoreFetch();
  }
});
