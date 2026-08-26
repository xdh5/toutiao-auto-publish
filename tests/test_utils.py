from app import utils


def test_call_llm_disables_thinking(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, json, headers, timeout):
        captured.update(json)
        return Response()

    monkeypatch.setattr(utils.requests, "post", fake_post)

    result = utils.call_llm(
        "https://example.invalid", "key", "qwen3.7-plus",
        [{"role": "user", "content": "test"}],
    )

    assert result == "ok"
    assert captured["model"] == "qwen3.7-plus"
    assert captured["stream"] is False
    assert captured["enable_thinking"] is False
