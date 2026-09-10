from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from xml.etree.ElementTree import fromstring

import pytest


def _renderer_module() -> ModuleType:
    path = Path(__file__).parents[3] / "services" / "score-renderer" / "server.py"
    spec = importlib.util.spec_from_file_location("score_renderer_server", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _benchmark_module() -> ModuleType:
    path = Path(__file__).parents[3] / "services" / "score-renderer" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("score_renderer_benchmark", path)
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
    assert "--export-area-drawing" in captured
    assert "--export-dpi=144" in captured


def test_renderer_combines_pages_with_inkscape_page_boundaries() -> None:
    renderer = _renderer_module()
    page = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2100 2970">'
        '<rect x="0" y="0" width="100" height="100"/></svg>'
    )
    combined = renderer._combine_svg_pages([page, page])
    root = renderer.fromstring(combined)
    assert root.get("data-page-count") == "2"
    assert root.get("height") == "5940"
    pages = root.findall(f".//{{{renderer.INKSCAPE_NAMESPACE}}}page")
    assert [item.get("y") for item in pages] == ["0", "2970"]


def test_renderer_benchmark_generates_requested_measure_count() -> None:
    benchmark = _benchmark_module()
    root = fromstring(benchmark.musicxml(40).split(b"\n", 1)[1])
    measures = root.findall("./part/measure")
    assert len(measures) == 40
    assert len(root.findall(".//note")) == 160


def test_renderer_metadata_requires_noto_cjk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _renderer_module()
    renderer.renderer_metadata.cache_clear()
    fake_verovio = ModuleType("verovio")
    fake_verovio.getVersion = lambda: "6.2.1"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "verovio", fake_verovio)

    def fake_run(command: list[str], **kwargs: object) -> object:
        output = "Inkscape 1.4" if command[0] == "inkscape" else "DejaVu Sans"
        return type("Result", (), {"stdout": output})()

    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="required font is unavailable"):
        renderer.renderer_metadata()


def test_engraver_rejects_invalid_utf8_before_loading_verovio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _renderer_module()
    fake_verovio = ModuleType("verovio")

    class Toolkit:
        def setOptions(self, options: dict[str, object]) -> None:
            pass

        def loadData(self, source: str) -> bool:
            raise AssertionError("invalid UTF-8 must not reach Verovio")

    fake_verovio.toolkit = Toolkit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "verovio", fake_verovio)
    with pytest.raises(UnicodeDecodeError):
        renderer.engrave_musicxml(b"\xff")
