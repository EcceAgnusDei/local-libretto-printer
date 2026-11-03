from pathlib import Path

import pytest

from libretto_printer.config import Settings, load_settings
from libretto_printer.servers import LlamaServer, _server_failure


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
        image_min_tokens=1024,
        out_dir=tmp_path / "out",
        title="Zaïs",
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
    assert command[command.index("--image-min-tokens") + 1] == "1024"
    assert command[command.index("--image-max-tokens") + 1] == "2048"


def test_a_bind_error_is_read_from_the_server_log(tmp_path: Path) -> None:
    log = tmp_path / "glm.log"
    log.write_text(
        "0.00.148.065 E srv         start: couldn't bind HTTP server socket, "
        "hostname: 127.0.0.1, port: 8080\n",
        encoding="utf-8",
    )
    assert _server_failure(log) == (
        "couldn't bind HTTP server socket, hostname: 127.0.0.1, port: 8080"
    )
