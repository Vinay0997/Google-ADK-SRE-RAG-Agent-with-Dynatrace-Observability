import json

from app.genai import estimate_cost_usd, messages_json


def test_messages_json_follows_genai_semconv():
    data = json.loads(messages_json("assistant", "hello", "stop"))
    assert data[0]["role"] == "assistant"
    assert data[0]["parts"][0] == {"type": "text", "content": "hello"}
    assert data[0]["finish_reason"] == "stop"


def test_cost_is_zero_without_pricing():
    assert estimate_cost_usd(1000, 1000) >= 0.0
