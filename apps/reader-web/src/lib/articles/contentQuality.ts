import type { ArticleContentIssue, ArticleContentStatus } from "./types";

export type ArticleContentAssessment = {
  status: ArticleContentStatus;
  issue: ArticleContentIssue;
  textLength: number;
};

export type ArticleContentFetchResult =
  | {
      outcome: "applied";
      quality: ArticleContentStatus;
      issue: ArticleContentIssue;
      textLength: number;
    }
  | {
      outcome: "rejected";
      reason: "blocked_or_error_page";
      issue: "blocked_or_error_page";
      textLength: number;
    }
  | {
      outcome: "unchanged";
      reason: "not_better";
      issue: ArticleContentIssue;
      textLength: number;
    }
  | {
      outcome: "failed";
      reason: "fetch_content_failed";
      issue: "fetch_failed";
      textLength: 0;
    };

export type FetchedArticleContentDecision = {
  html: string;
  fetchResult: ArticleContentFetchResult;
};

const MIN_FULL_TEXT_LENGTH = 280;
const MAX_ERROR_PAGE_TEXT_LENGTH = 1400;

const STRONG_BLOCKED_OR_ERROR_PATTERNS = [
  /enable javascript/i,
  /please enable (?:cookies|javascript)/i,
  /access denied/i,
  /forbidden/i,
  /just a moment/i,
  /checking your browser/i,
  /sign in to view/i,
  /login to view/i,
];

const WEAK_BLOCKED_OR_ERROR_PATTERNS = [
  /something went wrong/i,
  /try again/i,
  /privacy related extensions/i,
];

export function articleTextFromHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isPlaceholderText(text: string): boolean {
  return /^comments?$/i.test(text);
}

function isLikelyBlockedOrErrorPage(text: string): boolean {
  if (text.length === 0) return false;
  if (STRONG_BLOCKED_OR_ERROR_PATTERNS.some((pattern) => pattern.test(text))) return true;
  if (text.length > MAX_ERROR_PAGE_TEXT_LENGTH) return false;
  const weakMatches = WEAK_BLOCKED_OR_ERROR_PATTERNS.filter((pattern) => pattern.test(text)).length;
  return weakMatches >= 2;
}

export function assessArticleContent(html: string): ArticleContentAssessment {
  const text = articleTextFromHtml(html);
  if (isLikelyBlockedOrErrorPage(text)) {
    return { status: "partial", issue: "blocked_or_error_page", textLength: text.length };
  }
  if (text.length === 0 || isPlaceholderText(text) || text.length < MIN_FULL_TEXT_LENGTH) {
    return { status: "partial", issue: "rss_fragment", textLength: text.length };
  }
  return { status: "full", issue: null, textLength: text.length };
}

export function decideFetchedArticleContent(
  currentHtml: string,
  fetchedHtml: string,
): FetchedArticleContentDecision {
  const current = assessArticleContent(currentHtml);
  const fetched = assessArticleContent(fetchedHtml);

  if (fetched.issue === "blocked_or_error_page") {
    return {
      html: currentHtml,
      fetchResult: {
        outcome: "rejected",
        reason: "blocked_or_error_page",
        issue: "blocked_or_error_page",
        textLength: fetched.textLength,
      },
    };
  }

  if (fetched.textLength <= Math.max(current.textLength + 24, current.textLength * 1.08)) {
    return {
      html: currentHtml,
      fetchResult: {
        outcome: "unchanged",
        reason: "not_better",
        issue: current.issue,
        textLength: fetched.textLength,
      },
    };
  }

  return {
    html: fetchedHtml,
    fetchResult: {
      outcome: "applied",
      quality: fetched.status,
      issue: fetched.issue,
      textLength: fetched.textLength,
    },
  };
}

export function failedArticleContentFetchResult(): ArticleContentFetchResult {
  return {
    outcome: "failed",
    reason: "fetch_content_failed",
    issue: "fetch_failed",
    textLength: 0,
  };
}
