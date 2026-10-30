from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from libretto_printer.config import LOCAL_HOST, Settings

PAGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "needs_glm",
        "number_label",
        "verses",
        "corrections",
        "last_system_roles",
        "uncertain",
    ],
    "properties": {
        "needs_glm": {"type": "boolean"},
        "number_label": {"type": "string"},
        "uncertain": {"type": "boolean"},
        "last_system_roles": {"type": "array", "items": {"type": "string"}},
        "verses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["role", "text", "used_glm"],
                "properties": {
                    "role": {"type": "string"},
                    "text": {"type": "string"},
                    "used_glm": {"type": "boolean"},
                },
            },
        },
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["verse_id", "role", "text"],
                "properties": {
                    "verse_id": {"type": "string"},
                    "role": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
}


def image_url(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"Image refusée : {path.name}")
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.removeprefix('.')}"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def message_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Réponse du serveur sans choix.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("Réponse du serveur illisible.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("Réponse du serveur sans message.")
    content = message.get("content") or ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if not isinstance(content, str):
        raise ValueError("Contenu de réponse illisible.")
    return content


class HttpChat:
    def __init__(self, settings: Settings, alias: str, temperature: float) -> None:
        self.settings = settings
        self.alias = alias
        self.temperature = temperature

    def ask(self, image: Path, prompt: str, schema: dict[str, object] | None) -> str:
        content = [
            {"type": "image_url", "image_url": {"url": image_url(image)}},
            {"type": "text", "text": prompt},
        ]
        body: dict[str, object] = {
            "model": self.alias,
            "temperature": self.temperature,
            "top_k": 20,
            "top_p": 0.8,
            "presence_penalty": 0,
            "seed": 0,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": content}],
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "page_decision",
                    "strict": True,
                    "schema": schema,
                },
            }
        url = f"http://{LOCAL_HOST}:{self.settings.port}/v1/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Le serveur a répondu {error.code} : {detail}") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Réponse du serveur illisible.")
        return message_text(payload)
