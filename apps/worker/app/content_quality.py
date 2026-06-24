from __future__ import annotations

from dataclasses import dataclass
import re


MIN_FULL_TEXT_LENGTH = 280
MAX_ERROR_PAGE_TEXT_LENGTH = 1400

STRONG_BLOCKED_OR_ERROR_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"enable javascript",
        r"please enable (?:cookies|javascript)",
        r"access denied",
        r"forbidden",
        r"just a moment",
        r"checking your browser",
        r"sign in to view",
        r"login to view",
    ]
]

WEAK_BLOCKED_OR_ERROR_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"something went wrong",
        r"try again",
        r"privacy related extensions",
    ]
]


@dataclass(frozen=True)
class ArticleContentAssessment:
    status: str
    issue: str | None
    text_length: int


@dataclass(frozen=True)
class FetchedArticleContentDecision:
    html: str
    fetch_result: dict[str, object]


def article_text_from_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def assess_article_content(html: str) -> ArticleContentAssessment:
    text = article_text_from_html(html)
    if _is_likely_blocked_or_error_page(text):
        return ArticleContentAssessment(
            status="partial",
            issue="blocked_or_error_page",
            text_length=len(text),
        )
    if len(text) == 0 or _is_placeholder_text(text) or len(text) < MIN_FULL_TEXT_LENGTH:
        return ArticleContentAssessment(status="partial", issue="rss_fragment", text_length=len(text))
    return ArticleContentAssessment(status="full", issue=None, text_length=len(text))


def decide_fetched_article_content(
    current_html: str,
    fetched_html: str,
) -> FetchedArticleContentDecision:
    current = assess_article_content(current_html)
    fetched = assess_article_content(fetched_html)

    if fetched.issue == "blocked_or_error_page":
        return FetchedArticleContentDecision(
            html=current_html,
            fetch_result={
                "outcome": "rejected",
                "reason": "blocked_or_error_page",
                "issue": "blocked_or_error_page",
                "textLength": fetched.text_length,
            },
        )

    if fetched.text_length <= max(current.text_length + 24, int(current.text_length * 1.08)):
        return FetchedArticleContentDecision(
            html=current_html,
            fetch_result={
                "outcome": "unchanged",
                "reason": "not_better",
                "issue": current.issue,
                "textLength": fetched.text_length,
            },
        )

    return FetchedArticleContentDecision(
        html=fetched_html,
        fetch_result={
            "outcome": "applied",
            "quality": fetched.status,
            "issue": fetched.issue,
            "textLength": fetched.text_length,
        },
    )


def _is_placeholder_text(text: str) -> bool:
    return bool(re.fullmatch(r"comments?", text, flags=re.IGNORECASE))


def _is_likely_blocked_or_error_page(text: str) -> bool:
    if len(text) == 0:
        return False
    if any(pattern.search(text) for pattern in STRONG_BLOCKED_OR_ERROR_PATTERNS):
        return True
    if len(text) > MAX_ERROR_PAGE_TEXT_LENGTH:
        return False
    weak_matches = sum(1 for pattern in WEAK_BLOCKED_OR_ERROR_PATTERNS if pattern.search(text))
    return weak_matches >= 2
