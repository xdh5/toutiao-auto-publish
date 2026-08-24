import json
from pathlib import Path

from scripts import notify_telegram


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_send_success_is_silent(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return _Response({"ok": True})

    monkeypatch.setattr(notify_telegram.urllib.request, "urlopen", fake_urlopen)
    notify_telegram.send_telegram("token", "chat", "早发布已成功", silent=True)

    assert captured == {
        "chat_id": "chat",
        "text": "早发布已成功",
        "disable_notification": True,
    }


def test_send_failure_requests_system_notification(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return _Response({"ok": True})

    monkeypatch.setattr(notify_telegram.urllib.request, "urlopen", fake_urlopen)
    notify_telegram.send_telegram("token", "chat", "发布失败：登录状态过期", silent=False)

    assert captured["disable_notification"] is False


def test_publish_marker_detection(tmp_path: Path):
    assert not notify_telegram.has_publish_marker(tmp_path)
    marker = tmp_path / "pipeline" / "finance" / "publish-success"
    marker.parent.mkdir(parents=True)
    marker.touch()
    assert notify_telegram.has_publish_marker(tmp_path)
