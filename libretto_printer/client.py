from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from libretto_printer.config import LOCAL_HOST, Settings
from libretto_printer.journal import Journal


def image_url(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"Image refusée : {path.name}")
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.removeprefix('.')}"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@dataclass(frozen=True)
class StreamPiece:
    done: bool
    content: str
    reasoning: str


def take_delta(line: str) -> StreamPiece:
    stripped = line.strip()
    if not stripped:
        return StreamPiece(False, "", "")
    if not stripped.startswith("data:"):
        raise ValueError("Flux du serveur illisible.")
    data = stripped[5:].strip()
    if data == "[DONE]":
        return StreamPiece(True, "", "")
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("Flux du serveur illisible.")
    content, reasoning = _delta_parts(payload)
    return StreamPiece(False, content, reasoning)


def _delta_parts(payload: dict[str, object]) -> tuple[str, str]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", ""
    choice = choices[0]
    delta = choice.get("delta")
    if isinstance(delta, dict):
        return _text(delta.get("content")), _text(delta.get("reasoning_content"))
    message = choice.get("message")
    if isinstance(message, dict):
        return _text(message.get("content")), _text(message.get("reasoning_content"))
    return _text(choice.get("text")), ""


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


class HttpChat:
    def __init__(
        self,
        settings: Settings,
        alias: str,
        temperature: float,
        journal: Journal | None = None,
    ) -> None:
        self.settings = settings
        self.alias = alias
        self.temperature = temperature
        self.journal = journal

    def ask(self, image: Path, prompt: str, schema: dict[str, object] | None) -> str:
        content: object = [
            {"type": "image_url", "image_url": {"url": image_url(image)}},
            {"type": "text", "text": prompt},
        ]
        return self._send(content, schema)

    def ask_text(self, prompt: str, schema: dict[str, object] | None) -> str:
        return self._send(prompt, schema)

    def _send(self, content: object, schema: dict[str, object] | None) -> str:
        body: dict[str, object] = {
            "model": self.alias,
            "temperature": self.temperature,
            "top_k": 20,
            "top_p": 0.8,
            "presence_penalty": 0,
            "seed": 0,
            "max_tokens": 3072,
            "stream": True,
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
        if self.journal is not None:
            self.journal.model_begin(self.alias)
        try:
            return self._read(request)
        finally:
            if self.journal is not None:
                self.journal.model_end()

    def _read(self, request: urllib.request.Request) -> str:
        parts: list[str] = []
        reasoning_started = False
        try:
            response = urllib.request.urlopen(request, timeout=self.settings.request_timeout_s)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Le serveur a répondu {error.code} : {detail}") from error
        with response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                piece = take_delta(line)
                if piece.reasoning and self.journal is not None:
                    if not reasoning_started:
                        self.journal.event(f"{self.alias} raisonnement")
                        reasoning_started = True
                    self.journal.model(piece.reasoning)
                if piece.content:
                    parts.append(piece.content)
                    if self.journal is not None:
                        self.journal.model(piece.content)
                if piece.done:
                    break
        return "".join(parts)
