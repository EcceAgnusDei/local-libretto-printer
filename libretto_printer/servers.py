from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TextIO

from libretto_printer.config import LOCAL_HOST, Settings


class LlamaServer:
    def __init__(
        self,
        settings: Settings,
        model: Path,
        mmproj: Path,
        alias: str,
        reasoning: str,
        log_path: Path,
    ) -> None:
        if settings.host != LOCAL_HOST:
            raise ValueError("Le serveur ne peut écouter que sur 127.0.0.1.")
        self.settings = settings
        self.model = model
        self.mmproj = mmproj
        self.alias = alias
        self.reasoning = reasoning
        self.log_path = log_path
        self.process: subprocess.Popen[str] | None = None
        self._log_handle: TextIO | None = None

    def command(self) -> list[str]:
        settings = self.settings
        return [
            str(settings.llama_server),
            "--host",
            LOCAL_HOST,
            "--port",
            str(settings.port),
            "--model",
            str(self.model),
            "--mmproj",
            str(self.mmproj),
            "--alias",
            self.alias,
            "--ctx-size",
            str(settings.ctx_size),
            "--n-gpu-layers",
            "99",
            "--device",
            "Vulkan0",
            "--fit",
            "on",
            "--fit-target",
            str(settings.fit_target_mib),
            "--threads",
            str(settings.threads),
            "--image-max-tokens",
            str(settings.image_max_tokens),
            "--reasoning",
            self.reasoning,
            "--no-webui",
        ]

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = self.log_path.open("a", encoding="utf-8")
        environment = os.environ.copy()
        backend = str(self.settings.llama_server.parent)
        previous = environment.get("LD_LIBRARY_PATH", "")
        environment["LD_LIBRARY_PATH"] = backend if not previous else f"{backend}:{previous}"
        environment["GGML_VK_VISIBLE_DEVICES"] = "0"
        self.process = subprocess.Popen(
            self.command(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=environment,
            text=True,
        )
        self._log_handle = log_handle
        try:
            self._wait_until_ready()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        handle = self._log_handle
        self._log_handle = None
        if handle is not None:
            handle.close()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.settings.startup_timeout_s
        url = f"http://{LOCAL_HOST}:{self.settings.port}/health"
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(f"Le serveur s'est arrêté. Journal : {self.log_path}")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.4)
        raise TimeoutError(f"Le serveur n'a pas répondu. Journal : {self.log_path}")
