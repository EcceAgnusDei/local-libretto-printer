from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

LOCAL_HOST = "127.0.0.1"


@dataclass(frozen=True)
class Settings:
    root: Path
    llama_server: Path
    qwen_gguf: Path
    qwen_mmproj: Path
    glm_gguf: Path
    glm_mmproj: Path
    host: str
    port: int
    ctx_size: int
    threads: int
    fit_target_mib: int
    image_max_tokens: int
    pages_dir: Path
    out_dir: Path
    title: str
    tail_verses: int
    qwen_temperature: float
    glm_temperature: float
    startup_timeout_s: float
    request_timeout_s: float


def _path(root: Path, value: str) -> Path:
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return expanded
    return (root / expanded).resolve()


def load_settings(path: Path) -> Settings:
    config_path = path.expanduser().resolve()
    root = config_path.parent
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    host = str(raw.get("host", LOCAL_HOST))
    if host != LOCAL_HOST:
        raise ValueError("Le serveur ne peut écouter que sur 127.0.0.1.")
    return Settings(
        root=root,
        llama_server=_path(root, str(raw["llama_server"])),
        qwen_gguf=_path(root, str(raw["qwen_gguf"])),
        qwen_mmproj=_path(root, str(raw["qwen_mmproj"])),
        glm_gguf=_path(root, str(raw["glm_gguf"])),
        glm_mmproj=_path(root, str(raw["glm_mmproj"])),
        host=host,
        port=int(raw.get("port", 8080)),
        ctx_size=int(raw.get("ctx_size", 8192)),
        threads=int(raw.get("threads", 6)),
        fit_target_mib=int(raw.get("fit_target_mib", 2048)),
        image_max_tokens=int(raw.get("image_max_tokens", 2048)),
        pages_dir=_path(root, str(raw.get("pages_dir", "partitions/Zais/pages"))),
        out_dir=_path(root, str(raw.get("out_dir", "out/Zais"))),
        title=str(raw.get("title", "Zaïs")),
        tail_verses=int(raw.get("tail_verses", 40)),
        qwen_temperature=float(raw.get("qwen_temperature", 0.1)),
        glm_temperature=float(raw.get("glm_temperature", 0.0)),
        startup_timeout_s=float(raw.get("startup_timeout_s", 180)),
        request_timeout_s=float(raw.get("request_timeout_s", 300)),
    )


def missing_files(settings: Settings) -> list[Path]:
    required = (
        settings.llama_server,
        settings.qwen_gguf,
        settings.qwen_mmproj,
        settings.glm_gguf,
        settings.glm_mmproj,
        settings.pages_dir,
    )
    return [item for item in required if not item.exists()]
