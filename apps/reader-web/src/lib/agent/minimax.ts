import { type AgentChatMessage } from "./prompt";
import { getConfig } from "../config";

export async function streamMinimaxChat(messages: AgentChatMessage[]): Promise<ReadableStream<Uint8Array>> {
  const config = getConfig();

  const apiKey = config.MINIMAX_API_KEY;
  const baseUrlRaw = config.MINIMAX_BASE_URL;
  const model = config.MINIMAX_MODEL;

  if (apiKey === undefined || apiKey.trim().length === 0) {
    throw new Error("MINIMAX_API_KEY must be configured");
  }
  if (baseUrlRaw === undefined || baseUrlRaw.trim().length === 0) {
    throw new Error("MINIMAX_BASE_URL must be configured");
  }
  if (model === undefined || model.trim().length === 0) {
    throw new Error("MINIMAX_MODEL must be configured");
  }

  const baseUrl = baseUrlRaw.replace(/\/$/, "");
  const url = `${baseUrl}/chat/completions`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages,
      stream: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`MiniMax request failed (${response.status})`);
  }
  const body = response.body;
  if (!body) {
    throw new Error("MiniMax response missing body stream");
  }
  return body;
}
