from scripts.merge_batch_metadata import merge_metadata


def test_merge_metadata_keeps_old_articles_and_marks_current_batch():
    old = {
        "articles": [{"title": "早间文章", "content_type": "热点", "batch_name": "morning"}],
        "micro_posts": [{"batch": "morning", "content": "早间微头条"}],
        "batches_completed": ["morning"],
    }
    new = {
        "articles": [{"title": "午间文章", "content_type": "交易", "batch_name": "noon"}],
        "micro_posts": [{"batch": "noon", "content": "午间微头条"}],
    }

    merged = merge_metadata(old, new, "noon")

    assert [item["title"] for item in merged["articles"]] == ["早间文章", "午间文章"]
    assert [item["batch"] for item in merged["micro_posts"]] == ["morning", "noon"]
    assert merged["batches_completed"] == ["morning", "noon"]
    assert merged["total_articles"] == 2
