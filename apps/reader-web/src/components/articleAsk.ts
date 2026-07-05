import { ApiError } from "@/lib/api/client";

export function articleAskErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === "content_required") {
    return "需要先刷新全文或等待摘要评分生成后再提问。";
  }
  if (error instanceof ApiError && error.code === "request_timeout") {
    return "AI 回答超时，请稍后重试。";
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "已取消生成。";
  }
  if (error instanceof Error) return error.message;
  return "Agent request failed.";
}
