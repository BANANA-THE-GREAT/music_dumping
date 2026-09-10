from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _renderer_module() -> ModuleType:
    path = Path(__file__).parents[3] / "services" / "score-renderer" / "server.py"
    spec = importlib.util.spec_from_file_location("score_renderer_server", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_renderer_returns_svg_without_starting_a_subprocess() -> None:
    renderer = _renderer_module()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    assert renderer.render(svg, "svg") == svg


def test_renderer_rejects_invalid_input_and_format() -> None:
    renderer = _renderer_module()
    with pytest.raises(ValueError, match="SVG document"):
        renderer.render(b"not svg", "png")
    with pytest.raises(ValueError, match="unsupported output format"):
        renderer.render(b"<svg></svg>", "jpeg")


def test_renderer_uses_fixed_png_dpi(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = _renderer_module()
    captured: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        captured.extend(command)
        output = next(value.split("=", 1)[1] for value in command if "--export-filename=" in value)
        Path(output).write_bytes(b"PNG")

    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    assert renderer.render(b"<svg></svg>", "png") == b"PNG"
    assert "--export-area-page" in captured
    assert "--export-dpi=144" in captured
