from __future__ import annotations

import importlib.util
import json
import socket
import struct
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import ModuleType
from urllib.error import HTTPError
from urllib.request import Request, urlopen
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


@contextmanager
def _running_renderer(renderer: ModuleType) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), renderer.RendererHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post_error(url: str, path: str, body: bytes) -> tuple[int, dict[str, object]]:
    request = Request(f"{url}{path}", data=body, method="POST")
    try:
        urlopen(request, timeout=2)
    except HTTPError as error:
        return error.code, json.loads(error.read())
    raise AssertionError("request unexpectedly succeeded")


def test_renderer_returns_svg_without_starting_a_subprocess() -> None:
    renderer = _renderer_module()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    assert renderer.render(svg, "svg") == svg

    declared_svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
    assert renderer.render(declared_svg, "svg") == declared_svg


def test_renderer_rejects_invalid_input_and_format() -> None:
    renderer = _renderer_module()
    with pytest.raises(ValueError, match="SVG document"):
        renderer.render(b"not svg", "png")
    with pytest.raises(ValueError, match="unsupported output format"):
        renderer.render(b"<svg></svg>", "jpeg")


def test_renderer_uses_fixed_png_dpi(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = _renderer_module()
    captured: list[str] = []

    def fake_run(command: list[str], cancel_check: object = None) -> None:
        captured.extend(command)
        output = next(value.split("=", 1)[1] for value in command if "--export-filename=" in value)
        Path(output).write_bytes(b"PNG")

    monkeypatch.setattr(renderer, "_run_converter", fake_run)
    assert renderer.render(b"<svg></svg>", "png") == b"PNG"
    assert "--export-area-page" in captured
    assert "--export-dpi=144" in captured


def test_renderer_cancels_converter_process(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = _renderer_module()

    class RunningProcess:
        returncode = None
        terminated = False

        def communicate(self, timeout: float) -> tuple[bytes, bytes]:
            raise subprocess.TimeoutExpired(["inkscape"], timeout)

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def wait(self, timeout: int | None = None) -> int:
            assert self.terminated
            return -15

        def kill(self) -> None:
            raise AssertionError("terminate should stop the fake process")

    process = RunningProcess()
    monkeypatch.setattr(renderer.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(renderer.RenderCancelled):
        renderer._run_converter(["inkscape"], lambda: True)
    assert process.terminated


def test_renderer_detects_disconnected_client_socket() -> None:
    renderer = _renderer_module()
    server_socket, client_socket = socket.socketpair()
    handler = object.__new__(renderer.RendererHandler)
    handler.connection = server_socket
    try:
        assert handler._client_disconnected() is False
        client_socket.close()
        assert handler._client_disconnected() is True
    finally:
        server_socket.close()


def test_renderer_combines_pages_with_inkscape_page_boundaries() -> None:
    renderer = _renderer_module()
    page = (
        '<svg xmlns="http://www.w3.org/2000/svg" id="root" viewBox="0 0 2100 2970">'
        '<style>#shape{clip-path:url(#clip)}</style><defs><clipPath id="clip"/>'
        '<path id="shape"/></defs><use href="#shape" aria-labelledby="shape"/></svg>'
    )
    combined = renderer._combine_svg_pages([page, page])
    root = renderer.fromstring(combined)
    assert root.get("data-page-count") == "2"
    assert root.get("height") == "5940"
    pages = root.findall(f".//{{{renderer.INKSCAPE_NAMESPACE}}}page")
    assert [item.get("y") for item in pages] == ["0", "2970"]
    ids = [element.get("id") for element in root.iter() if element.get("id")]
    assert len(ids) == len(set(ids))
    assert "page-1-shape" in ids
    assert "page-2-shape" in ids
    uses = root.findall(f".//{{{renderer.SVG_NAMESPACE}}}use")
    assert [item.get("href") for item in uses] == ["#page-1-shape", "#page-2-shape"]
    styles = root.findall(f".//{{{renderer.SVG_NAMESPACE}}}style")
    assert "#page-1-shape" in (styles[0].text or "")
    assert "url(#page-2-clip)" in (styles[1].text or "")

    pdf_svg = renderer.fromstring(renderer._prepare_pdf_svg(combined))
    assert pdf_svg.get("height") == "2970"
    assert pdf_svg.get("viewBox") == "0 0 2100 2970"
    pdf_pages = pdf_svg.findall(f".//{{{renderer.INKSCAPE_NAMESPACE}}}page")
    assert [item.get("y") for item in pdf_pages] == ["0", "2970"]


def test_renderer_benchmark_generates_requested_measure_count() -> None:
    benchmark = _benchmark_module()
    root = fromstring(benchmark.musicxml(40).split(b"\n", 1)[1])
    measures = root.findall("./part/measure")
    assert len(measures) == 40
    assert len(root.findall(".//note")) == 160


def test_renderer_benchmark_validates_output_structures() -> None:
    benchmark = _benchmark_module()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" data-page-count="2"></svg>'
    assert benchmark.validate_output(svg, "svg", 2) == {"validated_pages": 2}

    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 640, 480)
    assert benchmark.validate_output(png, "png", 1) == {"width": 640, "height": 480}

    pdf = b"%PDF-1.7\n1 0 obj<</Type /Page>>endobj\n%%EOF"
    assert benchmark.validate_output(pdf, "pdf", 1) == {"structure_valid": True}


def test_renderer_metadata_requires_noto_cjk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _renderer_module()
    renderer.renderer_metadata.cache_clear()
    fake_verovio = ModuleType("verovio")

    class Toolkit:
        def getVersion(self) -> str:
            return "6.2.1"

    fake_verovio.toolkit = Toolkit  # type: ignore[attr-defined]
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


def test_renderer_http_reports_missing_runtime_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _renderer_module()

    def unavailable() -> dict[str, str]:
        raise RuntimeError("required font is unavailable")

    monkeypatch.setattr(renderer, "renderer_metadata", unavailable)
    with _running_renderer(renderer) as url:
        status, payload = _post_error(url, "/render?format=png", b"<svg></svg>")
    assert status == 503
    assert payload["code"] == "RENDERER_UNAVAILABLE"


def test_renderer_http_reports_full_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    renderer = _renderer_module()

    class FullQueue:
        def acquire(self, timeout: int) -> bool:
            assert timeout == renderer.RENDER_QUEUE_TIMEOUT_SECONDS
            return False

        def release(self) -> None:
            raise AssertionError("an unacquired render slot must not be released")

    monkeypatch.setattr(renderer, "renderer_metadata", lambda: {})
    monkeypatch.setattr(renderer, "RENDER_SLOTS", FullQueue())
    with _running_renderer(renderer) as url:
        status, payload = _post_error(url, "/render?format=png", b"<svg></svg>")
    assert status == 503
    assert payload["code"] == "RENDERER_BUSY"


def test_renderer_http_rejects_invalid_musicxml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _renderer_module()

    def invalid(_: bytes, cancel_check: object = None) -> bytes:
        raise ValueError("Verovio could not load the MusicXML document")

    monkeypatch.setattr(renderer, "renderer_metadata", lambda: {})
    monkeypatch.setattr(renderer, "engrave_musicxml", invalid)
    with _running_renderer(renderer) as url:
        status, payload = _post_error(url, "/engrave?format=svg", b"<broken>")
    assert status == 400
    assert payload["code"] == "INVALID_MUSICXML"
