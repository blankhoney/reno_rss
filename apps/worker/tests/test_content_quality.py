from app.content_quality import assess_article_content, decide_fetched_article_content


def test_assess_article_content_classifies_full_partial_and_blocked_pages():
    full = assess_article_content(f"<article>{'useful text ' * 40}</article>")
    short = assess_article_content("<p>Short body</p>")
    blocked = assess_article_content("<html><body>Access denied. Please enable JavaScript.</body></html>")

    assert full.status == "full"
    assert full.issue is None
    assert short.status == "partial"
    assert short.issue == "rss_fragment"
    assert blocked.status == "partial"
    assert blocked.issue == "blocked_or_error_page"


def test_decide_fetched_article_content_applies_only_better_non_blocked_content():
    current = "<p>Short body</p>"
    better = f"<article>{'useful text ' * 40}</article>"

    applied = decide_fetched_article_content(current, better)
    blocked = decide_fetched_article_content(current, "<p>Just a moment, checking your browser</p>")
    unchanged = decide_fetched_article_content(current, "<p>Short body</p>")

    assert applied.html == better
    assert applied.fetch_result["outcome"] == "applied"
    assert blocked.html == current
    assert blocked.fetch_result["outcome"] == "rejected"
    assert unchanged.html == current
    assert unchanged.fetch_result["outcome"] == "unchanged"
