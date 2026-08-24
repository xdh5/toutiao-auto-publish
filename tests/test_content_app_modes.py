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


def test_micro_publisher_has_no_independent_llm_or_validation_gate():
    import inspect

    source = inspect.getsource(micro_publisher.generate_draft)
    assert "call_llm" not in source
    assert "_validate_content" not in source
    assert "micro_content" in source
