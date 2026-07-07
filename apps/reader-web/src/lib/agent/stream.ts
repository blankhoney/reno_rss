export function extractOpenAICompatibleEventText(data: string): string {
  const trimmed = data.trim();
  if (trimmed.length === 0 || trimmed === "[DONE]") return "";

  try {
    const payload = JSON.parse(trimmed) as unknown;
    if (payload === null || typeof payload !== "object") return "";

    const choices = Reflect.get(payload, "choices");
    if (!Array.isArray(choices) || choices.length === 0) return "";

    const first = choices[0] as unknown;
    if (first === null || typeof first !== "object") return "";

    const delta = Reflect.get(first, "delta");
    if (delta !== null && typeof delta === "object") {
      const content = Reflect.get(delta, "content");
      if (typeof content === "string") return content;
    }

    const message = Reflect.get(first, "message");
    if (message !== null && typeof message === "object") {
      const content = Reflect.get(message, "content");
      if (typeof content === "string") return content;
    }
  } catch {
    return "";
  }

  return "";
}

export function createThinkTagFilter() {
  let insideThink = false;
  let buffer = "";

  return {
    push(chunk: string): string {
      buffer += chunk;
      const output: string[] = [];

      while (buffer.length > 0) {
        const lower = buffer.toLowerCase();
        if (insideThink) {
          const closeIndex = lower.indexOf("</think>");
          if (closeIndex < 0) {
            const tailLength = partialTagPrefixLength(buffer, "</think>");
            buffer = tailLength > 0 ? buffer.slice(-tailLength) : "";
            break;
          }
          buffer = buffer.slice(closeIndex + "</think>".length);
          insideThink = false;
          continue;
        }

        const openTag = findOpenThinkTag(buffer);
        if (openTag == null) {
          const tailLength = partialTagPrefixLength(buffer, "<think");
          const emitLength = buffer.length - tailLength;
          if (emitLength === 0) break;
          output.push(buffer.slice(0, emitLength));
          buffer = buffer.slice(emitLength);
          break;
        }

        output.push(buffer.slice(0, openTag.start));
        if (openTag.end == null) {
          buffer = buffer.slice(openTag.start);
          break;
        }
        buffer = buffer.slice(openTag.end);
        insideThink = true;
      }

      return output.join("");
    },

    flush(): string {
      if (buffer.length === 0 || insideThink) {
        buffer = "";
        return "";
      }
      const output = stripThinkTagsFromBufferedText(buffer);
      buffer = "";
      return output;
    },
  };
}

function findOpenThinkTag(text: string): { start: number; end: number | null } | null {
  const lower = text.toLowerCase();
  let searchFrom = 0;
  const marker = "<think";

  while (true) {
    const start = lower.indexOf(marker, searchFrom);
    if (start < 0) return null;

    const boundaryIndex = start + marker.length;
    if (boundaryIndex >= lower.length) return { start, end: null };

    const boundary = lower[boundaryIndex] ?? "";
    if (boundary === ">") return { start, end: boundaryIndex + 1 };
    if (/\s/.test(boundary)) {
      const end = lower.indexOf(">", boundaryIndex + 1);
      return { start, end: end < 0 ? null : end + 1 };
    }

    searchFrom = start + 1;
  }
}

function partialTagPrefixLength(text: string, tag: string): number {
  const lower = text.toLowerCase();
  for (let length = Math.min(tag.length - 1, lower.length); length > 0; length -= 1) {
    if (lower.endsWith(tag.slice(0, length))) return length;
  }
  return 0;
}

function stripThinkTagsFromBufferedText(text: string): string {
  return text
    .replace(/<think\b[^>]*>.*?<\/think>/gis, "")
    .replace(/<think\b[^>]*>.*$/is, "");
}

export function stripThinkTags(text: string): string {
  const filter = createThinkTagFilter();
  return filter.push(text) + filter.flush();
}

function encodeOpenAICompatibleSseContent(content: string): string {
  return `data: ${JSON.stringify({ choices: [{ delta: { content } }] })}\n\n`;
}

function extractDataLines(event: string): string[] {
  return event
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart());
}

export function cleanOpenAICompatibleSseStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const thinkFilter = createThinkTagFilter();
  let pending = "";

  return new ReadableStream({
    async start(controller) {
      const reader = upstream.getReader();

      function emitContent(content: string) {
        if (content.length === 0) return;
        controller.enqueue(encoder.encode(encodeOpenAICompatibleSseContent(content)));
      }

      function processEvent(event: string) {
        const dataLines = extractDataLines(event);
        for (const data of dataLines) {
          if (data.trim() === "[DONE]") {
            emitContent(thinkFilter.flush());
            controller.enqueue(encoder.encode("data: [DONE]\n\n"));
            continue;
          }
          emitContent(thinkFilter.push(extractOpenAICompatibleEventText(data)));
        }
      }

      function processPending(force = false) {
        const events = pending.split(/\r?\n\r?\n/);
        pending = force ? "" : (events.pop() ?? "");
        for (const event of events) {
          if (event.trim().length > 0) processEvent(event);
        }
      }

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          pending += decoder.decode(value, { stream: true });
          processPending();
        }

        pending += decoder.decode();
        processPending(true);
        emitContent(thinkFilter.flush());
        controller.close();
      } catch (error) {
        controller.error(error);
      } finally {
        reader.releaseLock();
      }
    },
  });
}
