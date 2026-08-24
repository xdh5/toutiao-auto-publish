"""验证财经和篮球两阶段 Prompt 均存在且被运行时代码调用。"""

import inspect
import json
import hashlib
from pathlib import Path

import pytest

import app.orchestrator as orchestrator
from app.utils import load_prompt_template


PROMPT_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_FILES = ("topic_selector.txt", "rewrite_article.txt")
EXPECTED_PROMPT_HASHES = {
    "basketball/rewrite_article.txt": "09b211d87a8448df86cf416106a04e2cd6adab458493ece1c03022dd4c6add41",
    "basketball/topic_selector.txt": "904a61930ada5b9eede2a9adec7bed6796e020b3df696b0e4bba51e886817474",
    "finance/rewrite_article.txt": "0ef5bb81554a68926af989fd8371c426b270f64a7de45b8e70e9780c7a398062",
    "finance/topic_selector.txt": "0df23297bf665531b07c49e2a3c9662982fc718ff63f4f68774eb017ec98f9df",
}

ALL_RUNTIME_PROMPTS = {
    "common": ("micro_post_system.txt",),
    "finance": (
        "topic_selector.txt", "topic_selector_system.txt",
        "rewrite_article.txt", "rewrite_article_system.txt",
        "fact_audit.txt", "fact_audit_system.txt", "micro_post.txt",
    ),
    "basketball": (
        "topic_selector.txt", "topic_materials.txt", "offseason_guidance.txt",
        "rewrite_article.txt", "rewrite_article_system.txt", "micro_post.txt",
        "emergency_article.txt", "emergency_article_system.txt",
        "prediction_article.txt", "prediction_article_system.txt",
    ),
}


@pytest.mark.parametrize("content_app", ["finance", "basketball"])
@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_business_prompt_files_exist(content_app, filename):
    path = PROMPT_DIR / content_app / filename
    assert path.exists(), f"缺少 {path}"
    assert path.stat().st_size > 500, f"Prompt 内容过短: {path}"
    assert load_prompt_template(filename, content_app)


@pytest.mark.parametrize(
    "content_app,filename",
    [(app, name) for app, names in ALL_RUNTIME_PROMPTS.items() for name in names],
)
def test_all_runtime_prompts_are_external_files(content_app, filename):
    path = PROMPT_DIR / content_app / filename
    assert path.exists(), f"缺少 {path}"
    assert load_prompt_template(filename, content_app)


def test_runtime_calls_selection_and_direct_rewrite():
    selection_source = inspect.getsource(orchestrator.select_topics)
    rewrite_sources = (
        inspect.getsource(orchestrator._rewrite_finance_article)
        + inspect.getsource(orchestrator.rewrite_article)
    )
    pipeline_source = inspect.getsource(orchestrator._rewrite_with_retry)
    assert 'load_prompt_template("topic_selector.txt")' in selection_source
    assert 'load_prompt_template("rewrite_article.txt")' in rewrite_sources
    assert "generate_article_draft" not in pipeline_source
    assert "rewrite_article(" in pipeline_source


def test_micro_and_auxiliary_prompts_are_loaded_at_runtime():
    import app.micro_publisher as micro_publisher

    micro_source = inspect.getsource(micro_publisher.generate_draft)
    orchestrator_source = inspect.getsource(orchestrator)
    assert 'load_prompt_template("micro_post.txt")' in micro_source
    assert 'load_prompt_template("micro_post_system.txt", "common")' in micro_source
    for filename in (
        "topic_materials.txt", "rewrite_article_system.txt", "fact_audit.txt",
        "fact_audit_system.txt", "offseason_guidance.txt", "emergency_article.txt",
        "emergency_article_system.txt", "prediction_article.txt",
        "prediction_article_system.txt",
    ):
        assert f'load_prompt_template("{filename}")' in orchestrator_source


def test_prompts_match_locked_reference_variants():
    for relative_path, expected in EXPECTED_PROMPT_HASHES.items():
        text = (PROMPT_DIR / relative_path).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == expected


def test_finance_selector_uses_ai_selected_article_id(monkeypatch):
    rows = [
        {"article_id": "first", "title": "第一条", "article_text": "甲" * 150,
         "url": "https://example.com/1", "source": "example.com",
         "category": "business", "region": "cn"},
        {"article_id": "second", "title": "第二条", "article_text": "乙" * 150,
         "url": "https://example.com/2", "source": "example.com",
         "category": "technology", "region": "cn"},
    ]
    response = [{"article_id": "second", "title": "第二条", "angle": "产业影响",
                 "keywords": ["technology"], "keywords_cn": ["科技"]}]
    monkeypatch.setattr(orchestrator, "call_llm", lambda *_args, **_kwargs: json.dumps(response, ensure_ascii=False))
    topics = orchestrator.select_topics({
        "data_source": "worldnews", "date": "2026-08-24", "batch_mode": "morning",
        "news_articles": rows,
    }, topic_count=1)
    assert topics[0]["_source_article_id"] == "second"
    assert topics[0]["angle"] == "产业影响"


def test_finance_prompts_keep_finance_scope_and_source_facts():
    selector = load_prompt_template("topic_selector.txt", "finance")
    rewrite = load_prompt_template("rewrite_article.txt", "finance")
    assert "财经" in selector
    assert "来源文章" in rewrite
    assert all("财富研习岛" in prompt for prompt in (selector, rewrite))
    assert all("岛哥" in prompt for prompt in (selector, rewrite))
    assert all("球评人老六" not in prompt for prompt in (selector, rewrite))


def test_basketball_prompts_keep_basketball_scope_and_fidelity():
    prompts = [load_prompt_template(name, "basketball") for name in PROMPT_FILES]
    assert all("篮球" in prompt for prompt in prompts)
    assert all("岛哥侃篮球" in prompt for prompt in prompts)
    assert all("球评人老六" not in prompt for prompt in prompts)
    assert "事实零改动" in prompts[1]
