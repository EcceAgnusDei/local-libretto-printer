from __future__ import annotations

from pathlib import Path

from libretto_printer.client import HttpChat
from libretto_printer.config import Settings
from libretto_printer.journal import Journal
from libretto_printer.servers import LlamaServer


class ModelSession:
    def __init__(self, settings: Settings, journal: Journal | None = None) -> None:
        self.settings = settings
        self.journal = journal
        self._server: LlamaServer | None = None
        self._name: str | None = None

    def qwen(self) -> HttpChat:
        self._activate("qwen", self.settings.qwen_gguf, self.settings.qwen_mmproj)
        return HttpChat(self.settings, "qwen", self.settings.qwen_temperature, self.journal)

    def glm(self) -> HttpChat:
        self._activate("glm", self.settings.glm_gguf, self.settings.glm_mmproj)
        return HttpChat(self.settings, "glm", self.settings.glm_temperature, self.journal)

    def close(self) -> None:
        name = self._name
        if self._server is not None:
            self._server.stop()
            if self.journal is not None and name is not None:
                self.journal.event(f"arrêt du serveur {name}")
        self._server = None
        self._name = None

    def _activate(self, name: str, model: Path, mmproj: Path) -> None:
        if self._name == name and self._server is not None:
            return
        self.close()
        log_path = self.settings.out_dir / "logs" / f"{name}.log"
        if self.journal is not None:
            self.journal.event(f"démarrage du serveur {name}, sortie logs/{log_path.name}")
        server = LlamaServer(
            self.settings,
            model,
            mmproj,
            name,
            "off",
            log_path,
        )
        server.start()
        self._server = server
        self._name = name
        if self.journal is not None:
            self.journal.event(f"serveur {name} prêt")


class QwenReader:
    def __init__(self, session: ModelSession) -> None:
        self._session = session

    def ask(
        self,
        image: Path,
        prompt: str,
        schema: dict[str, object] | None = None,
    ) -> str:
        return self._session.qwen().ask(image, prompt, schema)

    def ask_text(self, prompt: str, schema: dict[str, object] | None = None) -> str:
        return self._session.qwen().ask_text(prompt, schema)


class GlmReader:
    def __init__(self, session: ModelSession) -> None:
        self._session = session

    def ask(
        self,
        image: Path,
        prompt: str,
        schema: dict[str, object] | None = None,
    ) -> str:
        del schema
        return self._session.glm().ask(image, prompt, None)
