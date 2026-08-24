import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import micro_publisher


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("app", "expected_column"),
    [("finance", "国内财经科技新闻"), ("basketball", "NBA早报")],
)
def test_content_app_selects_independent_batch_config(app, expected_column):
    env = {**os.environ, "CONTENT_APP": app, "PYTHONUTF8": "1"}
    code = (
        "import app.constants as constants; "
        f"assert constants.CONTENT_APP == {app!r}; "
        f"assert constants.BATCH_CONFIG['morning']['slots'][0]['column_name'] == {expected_column!r}"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("app", "forbidden_module"),
    [("finance", "app.basketball"), ("basketball", "app.finance")],
)
def test_collector_loads_only_selected_business(app, forbidden_module):
    env = {**os.environ, "CONTENT_APP": app, "PYTHONUTF8": "1"}
    code = (
        "import sys; import app.data_collector as collector; collector._collector(); "
        f"assert not any(name == {forbidden_module!r} or name.startswith({forbidden_module!r} + '.') "
        "for name in sys.modules), sorted(sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_basketball_micro_uses_basketball_length_and_question(monkeypatch):
    monkeypatch.setattr(micro_publisher, "CONTENT_APP", "basketball")
    valid = ("这是一段只使用原文事实的篮球评论，球队在比赛中展现了稳定执行力，关键回合的选择也让比赛走势更加清楚。" * 4)[:230]
    valid += "你怎么看这场比赛？\n#NBA#"
    micro_publisher._validate_content(valid, valid)


def test_finance_micro_keeps_finance_length(monkeypatch):
    monkeypatch.setattr(micro_publisher, "CONTENT_APP", "finance")
    valid = ("这是一段客观清楚的财经新闻说明，所有人物机构数字日期和事件都来自正篇，没有增加原文之外的具体事实。" * 5)[:260]
    valid += "\n#财经新闻#"
    micro_publisher._validate_content(valid, valid)
