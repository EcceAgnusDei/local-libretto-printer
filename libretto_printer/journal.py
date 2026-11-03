from __future__ import annotations

import os
import threading
from pathlib import Path

JOURNAL_NAME = "journal.log"


class Journal:
    def __init__(self, root: Path) -> None:
        resolved_root = root.resolve()
        path = (resolved_root / JOURNAL_NAME).resolve()
        if path.parent != resolved_root or path.name != JOURNAL_NAME:
            raise ValueError("Le journal sortirait de la session.")
        flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o644)
        self.path = path
        self._handle = os.fdopen(descriptor, "a", encoding="utf-8", closefd=True)
        self._lock = threading.Lock()
        self._closed = False

    def event(self, message: str) -> None:
        self._write(f"[harnais] {message}\n")

    def model_begin(self, name: str) -> None:
        self._write(f"\n[modèle:{name}]\n")

    def model(self, text: str) -> None:
        if text:
            self._write(text)

    def model_end(self) -> None:
        self._write("\n[modèle:fin]\n")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._handle.close()

    def _write(self, text: str) -> None:
        with self._lock:
            if self._closed:
                return
            self._handle.write(text)
            self._handle.flush()
