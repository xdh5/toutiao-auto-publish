from app.finance import image_search


class _Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_finance_queries_prefer_company_and_business_scene():
    queries = image_search.build_search_queries({
        "title": "比亚迪扩大新能源汽车生产线",
        "content": "公司计划增加工厂产能。",
        "keywords": ["business", "company", "BYD", "electric vehicles"],
    })

    assert queries[0].startswith("BYD electric vehicle factory")
    assert any("electric vehicles" in query for query in queries)
    assert "business company manufacturing" not in queries


def test_finance_queries_map_infrastructure_news_to_real_scene():
    queries = image_search.build_search_queries({
        "title": "交通运输主要指标保持增长",
        "content": "港口吞吐量增长，多条高速公路项目推进。",
        "keywords": ["business", "company", "manufacturing"],
    })

    assert queries[0] == "cargo port shipping containers"
    assert "transportation infrastructure China" in queries


def test_unsplash_candidates_are_stable_for_same_article_and_day(monkeypatch):
    results = [
        {"id": str(index), "urls": {"regular": f"https://images.example/{index}.jpg"},
         "alt_description": f"image {index}"}
        for index in range(10)
    ]
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params, timeout))
        return _Response(payload={"results": results})

    monkeypatch.setattr(image_search, "UNSPLASH_KEY", "test-key")
    monkeypatch.setattr(image_search.requests, "get", fake_get)
    article = {
        "title": "英伟达推出新一代人工智能芯片",
        "content": "新产品面向数据中心。",
        "keywords": ["NVIDIA", "AI chip"],
    }

    first = image_search.search_images(article, count=5, date_str="2026-08-24")
    second = image_search.search_images(article, count=5, date_str="2026-08-24")

    assert [item["photo_id"] for item in first] == [item["photo_id"] for item in second]
    assert len(first) == 5
    assert calls[0][1]["query"].startswith("NVIDIA semiconductor chip manufacturing")
    assert calls[0][1]["per_page"] == 10
