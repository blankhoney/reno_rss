"""Build portable research exports for project-queue articles (GOAL Keep)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ExportArticle:
    id: int
    title: str
    url: str
    summary_zh: str
    score: int | None
    tier: str | None
    reason: str
    tags: list[str]


def build_project_export_markdown(
    articles: Sequence[ExportArticle],
    *,
    generated_at: datetime | None = None,
) -> str:
    stamp = (generated_at or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# AI Reader 立项导出",
        "",
        f"生成时间：{stamp}",
        f"共 {len(articles)} 篇",
        "",
    ]
    if not articles:
        lines.append("_当前没有立项文章。_")
        lines.append("")
        return "\n".join(lines)

    for index, article in enumerate(articles, start=1):
        score_label = f"{article.score}" if article.score is not None else "未评"
        tier_label = article.tier or "—"
        lines.extend(
            [
                f"## {index}. {article.title}",
                "",
                f"- URL: {article.url}",
                f"- 分数: {score_label} / 档位: {tier_label}",
                f"- 标签: {', '.join(article.tags) if article.tags else '无'}",
                f"- 理由: {article.reason or '无'}",
                f"- 摘要: {article.summary_zh or '无'}",
                "",
            ]
        )
    return "\n".join(lines)


def build_project_export_json(
    articles: Sequence[ExportArticle],
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    stamp = (generated_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "generated_at": stamp.isoformat(),
        "count": len(articles),
        "items": [
            {
                "id": article.id,
                "title": article.title,
                "url": article.url,
                "summary_zh": article.summary_zh,
                "score": article.score,
                "tier": article.tier,
                "reason": article.reason,
                "tags": list(article.tags),
            }
            for article in articles
        ],
    }
