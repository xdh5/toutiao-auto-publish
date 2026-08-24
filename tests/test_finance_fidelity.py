import inspect

import app.orchestrator as orchestrator
from app.finance.validator import validate_article


def _article(content="中" * 500, micro_content="短" * 250, **extra):
    return {"title": "财经新闻标题", "content": content,
            "micro_content": micro_content, **extra}


def test_finance_program_review_is_in_rewrite_pipeline():
    source = inspect.getsource(orchestrator._rewrite_with_retry)
    assert "from .finance.validator import validate_article" in source


def test_finance_fidelity_accepts_target_lengths_and_unit_conversion():
    fixture = {"article_text": "The company reported revenue of 1.5 billion yuan, up 12 percent."}
    article = _article(
        content="公司披露营收达到15亿元，同比增长12%。" + "中" * 480,
        micro_content="营收15亿元，同比增长12%。" + "短" * 230,
        title="营收达到15亿元",
    )
    passed, issues = validate_article(fixture, article)
    assert passed is True
    assert issues == []


def test_finance_fidelity_rejects_number_absent_from_source():
    fixture = {"article_text": "公司公布了新的经营计划。"}
    article = _article(content="公司预计投入99亿元。" + "中" * 488)
    passed, issues = validate_article(fixture, article)
    assert passed is False
    assert any("新增数字" in issue and "99亿" in issue for issue in issues)


def test_finance_fidelity_checks_article_and_micro_lengths():
    fixture = {"article_text": "公司公布经营计划。"}
    passed, issues = validate_article(
        fixture, _article(content="中" * 449, micro_content="短" * 351))
    assert passed is False
    assert any("长文章字数449" in issue for issue in issues)
    assert any("微头条字数351" in issue for issue in issues)


def test_finance_fidelity_does_not_review_nonnumeric_details():
    fixture = {"article_text": "公司宣布调整产品价格。"}
    article = _article(
        content="知情人士称，公司管理层震怒后连夜决定调整价格。" + "中" * 474,
        micro_content="消费者随后疯抢。" + "短" * 241,
    )
    passed, issues = validate_article(fixture, article)
    assert passed is True
    assert issues == []


def test_finance_fidelity_ignores_image_path_numbers():
    fixture = {"article_text": "公司公布了新的经营计划。"}
    marker = "![配图1](images/article-1-img-001.jpg)"
    article = _article(content=marker + "中" * (500 - len(marker)))
    passed, issues = validate_article(fixture, article)
    assert passed is True
    assert issues == []
