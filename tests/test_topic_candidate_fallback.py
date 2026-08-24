import app.orchestrator as orchestrator


def test_direct_news_topics_prefer_articles_with_body():
    topics = orchestrator._build_direct_news_topics({
        "news_articles": [
            {"title": "只有标题", "url": "https://example.com/1", "article_text": ""},
            {
                "title": "正文完整",
                "url": "https://example.com/2",
                "article_text": "正文" * 60,
                "_content_type_hint": "交易资讯",
            },
        ]
    })

    assert [topic["title"] for topic in topics] == ["正文完整", "只有标题"]
    assert topics[0]["content_type"] == "交易资讯"
    assert topics[0]["_source_url"] == "https://example.com/2"


def test_direct_news_topics_use_shared_title_dedup_rule():
    topics = orchestrator._build_direct_news_topics(
        {
            "news_articles": [
                {"title": "湖人今日完成一笔重要签约消息", "url": "https://example.com/used"},
                {"title": "湖人今日完成一笔重要签约消息，球队随后回应", "url": "https://example.com/similar"},
                {"title": "勇士公布新赛季训练计划", "url": "https://example.com/new"},
            ]
        },
        used_sources={"湖人今日完成一笔重要签约消息"},
    )

    assert [topic["title"] for topic in topics] == ["勇士公布新赛季训练计划"]


def test_finance_and_basketball_share_source_filter():
    articles = [
        {"title": "国内企业发布季度经营情况", "url": "https://example.com/old"},
        {"title": "国内企业发布季度经营情况，收入继续增长", "url": "https://example.com/same"},
        {"title": "海外消费品牌公布新计划", "url": "https://example.com/new"},
    ]

    filtered = orchestrator._filter_news_by_source_history(
        articles, {"国内企业发布季度经营情况"}
    )

    assert [item["title"] for item in filtered] == ["海外消费品牌公布新计划"]


def test_failed_topic_falls_back_until_target_count(monkeypatch):
    topics = [
        {"title": "候选一", "content_type": "热点球评", "_batch_name": "晚间"},
        {"title": "候选二", "content_type": "交易资讯"},
        {"title": "候选三", "content_type": "排行榜"},
    ]
    attempted = []

    def fake_generate(topic, *_args, **_kwargs):
        attempted.append((topic["title"], topic.get("_batch_name")))
        if topic["title"] == "候选一":
            return {}, "未找到匹配源文章"
        return {"title": "成功文章", "content": "正文"}, None

    monkeypatch.setattr(orchestrator, "generate_article_with_retry", fake_generate)
    monkeypatch.setattr(orchestrator, "search_images", lambda *_args, **_kwargs: [])

    images = {}
    stats = {"generated": 0, "failed": 0, "valid": 0, "issues": []}
    articles = []
    successful_topics = orchestrator._generate_articles_from_topics(
        topics,
        1,
        {"data_source": "worldnews"},
        images,
        stats,
        articles,
        date_str="2026-08-24",
    )

    assert attempted == [("候选一", "晚间"), ("候选二", "晚间")]
    assert articles == [(
        0,
        {"title": "成功文章", "content": "正文", "sources_used": ["候选二"]},
    )]
    assert stats == {
        "generated": 2,
        "failed": 1,
        "valid": 1,
        "issues": ["候选1(热点球评): 未找到匹配源文章"],
    }
    assert images == {0: []}
    assert successful_topics == [topics[1]]


def test_finance_searches_images_only_after_final_article_succeeds(monkeypatch):
    topics = [
        {"title": "失败素材", "content_type": "国内商业"},
        {"title": "成功素材", "content_type": "国内商业", "keywords": ["business"]},
    ]
    image_inputs = []

    def fake_generate(topic, *_args, **_kwargs):
        if topic["title"] == "失败素材":
            return {}, "改写失败"
        return {"title": "最终财经标题", "content": "最终正文包含新能源汽车工厂信息。",
                "keywords": ["electric vehicle"]}, None

    def fake_search(article, *_args, **_kwargs):
        image_inputs.append(article)
        return [{"url": "https://images.example/finance.jpg", "query": "electric vehicle factory"}]

    monkeypatch.setattr(orchestrator, "CONTENT_APP", "finance")
    monkeypatch.setattr(orchestrator, "generate_article_with_retry", fake_generate)
    monkeypatch.setattr(orchestrator, "search_images", fake_search)

    images = {}
    stats = {"generated": 0, "failed": 0, "valid": 0, "issues": []}
    articles = []
    orchestrator._generate_articles_from_topics(
        topics, 1, {"data_source": "worldnews"}, images, stats, articles,
        date_str="2026-08-24",
    )

    assert len(image_inputs) == 1
    assert image_inputs[0]["title"] == "最终财经标题"
    assert image_inputs[0]["keywords"] == ["electric vehicle"]
    assert images == {0: [{"url": "https://images.example/finance.jpg",
                           "query": "electric vehicle factory"}]}
