import inspect
from pathlib import Path

from app.file_writer import FileWriter
from app import orchestrator


def test_basketball_article_has_no_appended_author_footer(tmp_path):
    result = FileWriter(str(tmp_path)).save_article(
        "2026-08-24",
        1,
        {"title": "测试篮球文章", "content": "正文结尾。", "category": "NBA"},
    )
    saved = Path(result["article_path"]).read_text(encoding="utf-8")

    assert "岛哥侃篮球 ·" not in saved
    assert saved.rstrip().endswith("正文结尾。")


def test_save_pipeline_does_not_append_golden_recap_or_second_interaction():
    source = inspect.getsource(orchestrator.save_articles_local)

    assert "golden_block" not in source
    assert "老六金句" not in source
    assert "评论区见分晓" not in source
