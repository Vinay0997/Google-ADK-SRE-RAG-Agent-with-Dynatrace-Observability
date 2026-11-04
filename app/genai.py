import json

from app.settings import get_settings


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    s = get_settings()
    cost = (input_tokens / 1_000_000) * s.input_price_per_mtok
    cost += (output_tokens / 1_000_000) * s.output_price_per_mtok
    return round(cost, 8)


def messages_json(role: str, text: str, finish_reason: str | None = None) -> str:
    # OpenTelemetry GenAI semantic-convention message format.
    message = {"role": role, "parts": [{"type": "text", "content": text}]}
    if finish_reason:
        message["finish_reason"] = finish_reason
    return json.dumps([message])
