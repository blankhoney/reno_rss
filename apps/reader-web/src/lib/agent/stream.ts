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
