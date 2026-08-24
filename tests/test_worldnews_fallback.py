import orchestrator


def _row(article_id, title):
    return {
        "article_id": article_id,
        "title": title,
        "article_text": "这是一段足够长的来源正文。" * 20,
        "url": f"https://example.com/{article_id}",
        "source": "example.com",
        "_content_type_hint": "海外商业",
    }


def test_worldnews_http_400_skips_to_next_article(monkeypatch):
    first = _row("first", "第一篇触发审核")
    second = _row("second", "第二篇正常生成")
    context = {"data_source": "worldnews", "news_articles": [first, second]}
    topic = {"title": first["title"], "content_type": "海外商业", "_source_article_id": "first"}
    calls = []

    def fake_rewrite(candidate_topic, match_context, index, source, max_retries, date_str):
        calls.append(candidate_topic["_source_article_id"])
        if candidate_topic["_source_article_id"] == "first":
            return {}, "LLM HTTP 400: 400 Client Error"
        return {"title": candidate_topic["title"], "content": "生成成功"}, None

    monkeypatch.setattr(orchestrator, "_rewrite_with_retry", fake_rewrite)
    article, error = orchestrator.generate_article_with_retry(topic, context, 1)

    assert error is None
    assert article["title"] == second["title"]
    assert topic["title"] == second["title"]
    assert topic["_source_article_id"] == "second"
    assert calls == ["first", "second"]


def test_worldnews_non_400_does_not_switch_source(monkeypatch):
    first = _row("first", "第一篇")
    second = _row("second", "第二篇")
    context = {"data_source": "worldnews", "news_articles": [first, second]}
    topic = {"title": first["title"], "content_type": "海外商业", "_source_article_id": "first"}
    calls = []

    def fake_rewrite(candidate_topic, match_context, index, source, max_retries, date_str):
        calls.append(candidate_topic["_source_article_id"])
        return {}, "独立复核未通过"

    monkeypatch.setattr(orchestrator, "_rewrite_with_retry", fake_rewrite)
    article, error = orchestrator.generate_article_with_retry(topic, context, 1)

    assert article == {}
    assert error == "独立复核未通过"
    assert calls == ["first"]
