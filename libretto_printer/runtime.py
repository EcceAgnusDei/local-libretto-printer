from __future__ import annotations

from pathlib import Path

from libretto_printer.client import PAGE_SCHEMA, HttpChat
from libretto_printer.config import Settings
from libretto_printer.servers import LlamaServer


class ModelSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._server: LlamaServer | None = None
        self._name: str | None = None

    def qwen(self) -> HttpChat:
        self._activate("qwen", self.settings.qwen_gguf, self.settings.qwen_mmproj)
        return HttpChat(self.settings, "qwen", self.settings.qwen_temperature)

    def glm(self) -> HttpChat:
        self._activate("glm", self.settings.glm_gguf, self.settings.glm_mmproj)
        return HttpChat(self.settings, "glm", self.settings.glm_temperature)

    def close(self) -> None:
        if self._server is not None:
            self._server.stop()
        self._server = None
        self._name = None

    def _activate(self, name: str, model: Path, mmproj: Path) -> None:
        if self._name == name and self._server is not None:
            return
        self.close()
        server = LlamaServer(
            self.settings,
            model,
            mmproj,
            name,
            "off",
            self.settings.out_dir / "logs" / f"{name}.log",
        )
        server.start()
        self._server = server
        self._name = name


class QwenReader:
    def __init__(self, session: ModelSession) -> None:
        self._session = session

    def ask(self, image: Path, prompt: str) -> str:
        return self._session.qwen().ask(image, prompt, PAGE_SCHEMA)


class GlmReader:
    def __init__(self, session: ModelSession) -> None:
        self._session = session

    def ask(self, image: Path, prompt: str) -> str:
        return self._session.glm().ask(image, prompt, None)
