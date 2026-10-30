from pathlib import Path

import pytest

from libretto_printer.config import Settings, load_settings
from libretto_printer.servers import LlamaServer


def test_host_other_than_localhost_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('host = "0.0.0.0"\nllama_server = "llama-server"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(config)


def test_server_command_stays_on_localhost(tmp_path: Path) -> None:
    settings = Settings(
        root=tmp_path,
        llama_server=tmp_path / "llama-server",
        qwen_gguf=tmp_path / "qwen.gguf",
        qwen_mmproj=tmp_path / "qwen.mmproj",
        glm_gguf=tmp_path / "glm.gguf",
        glm_mmproj=tmp_path / "glm.mmproj",
        host="127.0.0.1",
        port=8080,
        ctx_size=8192,
        threads=6,
        fit_target_mib=2048,
        image_max_tokens=2048,
        pages_dir=tmp_path,
        out_dir=tmp_path / "out",
        title="Zaïs",
        tail_verses=40,
        qwen_temperature=0.1,
        glm_temperature=0.0,
        startup_timeout_s=5,
        request_timeout_s=5,
    )
    server = LlamaServer(
        settings,
        settings.qwen_gguf,
        settings.qwen_mmproj,
        "qwen",
        "off",
        tmp_path / "qwen.log",
    )
    command = server.command()
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "--no-webui" in command
    assert "Vulkan0" in command
    assert "0.0.0.0" not in command
