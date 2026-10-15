import json

import httpx
import pytest

from skill_warden.reader import Reader
from skill_warden.errors import ReaderInvalid

SKILL = "SECRET-SKILL-TEXT do not log this"


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _reader(handler) -> Reader:
    return Reader(
        api_key="test-key",
        base_url="https://reader.test/v1",
        transport=httpx.MockTransport(handler),
    )


def test_request_body():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        content = json.dumps({"flags": [], "evidence": []})
        return httpx.Response(200, json=_completion(content))

    reader = _reader(handler)
    reader.call(SKILL)
    reader.call(SKILL)

    first = json.loads(seen[0].content)
    second = json.loads(seen[1].content)
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert first["model"] == "openai/gpt-oss-120b"
    assert first["temperature"] == 0
    assert first["max_completion_tokens"] == 512
    assert first["tool_choice"] == "none"
    assert "tools" not in first
    assert first["response_format"] == {"type": "json_object"}
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][1]["role"] == "user"
    assert first["messages"][1]["content"].startswith("UNTRUSTED SKILL FOLLOWS")
    assert SKILL in first["messages"][1]["content"]
    assert first["messages"][0]["content"] != second["messages"][0]["content"]


def test_returns_memory_persistence_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"flags": ["memory_persistence"], "evidence": ["quoted line"]})
        return httpx.Response(200, json=_completion(content))

    result = _reader(handler).call(SKILL)

    assert result.flags == ["memory_persistence"]
    assert result.evidence == ["quoted line"]


def test_decision_key_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"decision": "ALLOW", "flags": []})
        return httpx.Response(200, json=_completion(content))

    with pytest.raises(ReaderInvalid):
        _reader(handler).call(SKILL)


def test_echoed_canary_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        content = json.dumps({"flags": [], "evidence": [system]})
        return httpx.Response(200, json=_completion(content))

    with pytest.raises(ReaderInvalid):
        _reader(handler).call(SKILL)


def test_skill_text_absent_from_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"decision": "ALLOW", "flags": [], "evidence": [SKILL]})
        return httpx.Response(200, json=_completion(content))

    with pytest.raises(ReaderInvalid) as raised:
        _reader(handler).call(SKILL)

    assert SKILL not in str(raised.value)
    assert "ALLOW" not in str(raised.value)
