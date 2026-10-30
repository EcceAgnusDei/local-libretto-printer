from __future__ import annotations

import json
import re

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json_object(raw: str) -> dict[str, object]:
    text = _THINKING.sub("", raw).strip()
    text = _FENCE.sub("", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Aucun objet JSON dans la réponse.")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("La réponse JSON n'est pas un objet.")
    return parsed
