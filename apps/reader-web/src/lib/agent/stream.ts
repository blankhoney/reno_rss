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
  let pendingTag = "";

  return {
    push(chunk: string): string {
      let output = "";

      for (const char of chunk) {
        if (pendingTag.length > 0) {
          pendingTag += char;
          const lower = pendingTag.toLowerCase();
          if ("<think>".startsWith(lower) || "</think>".startsWith(lower)) {
            if (lower === "<think>") {
              insideThink = true;
              pendingTag = "";
            } else if (lower === "</think>") {
              insideThink = false;
              pendingTag = "";
            }
            continue;
          }

          if (!insideThink) output += pendingTag;
          pendingTag = "";
          continue;
        }

        if (char === "<") {
          pendingTag = char;
          continue;
        }

        if (!insideThink) output += char;
      }

      return output;
    },

    flush(): string {
      if (pendingTag.length === 0 || insideThink) {
        pendingTag = "";
        return "";
      }
      const output = pendingTag;
      pendingTag = "";
      return output;
    },
  };
}

export function stripThinkTags(text: string): string {
  const filter = createThinkTagFilter();
  return filter.push(text) + filter.flush();
}
