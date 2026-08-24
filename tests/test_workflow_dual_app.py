from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_scheduled_workflow_queues_finance_then_football():
    workflow = (ROOT / ".github" / "workflows" / "batch.yml").read_text(
        encoding="utf-8"
    )

    assert "github.event_name == 'schedule' || inputs.app == 'both'" in workflow
    assert "'[\"finance\",\"football\"]'" in workflow
    assert "max-parallel: 1" in workflow
    assert 'APP="${{ matrix.app }}"' in workflow


def test_manual_workflows_offer_both():
    for name in ("batch.yml", "daily.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

        assert "default: both" in workflow
        assert "- both" in workflow
        assert "max-parallel: 1" in workflow
