from __future__ import annotations

import json
import select
import socket
import subprocess
import tempfile
from collections.abc import Callable
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Protocol, cast
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import (
    Element,
    ParseError,
    SubElement,
    fromstring,
    register_namespace,
    tostring,
)

MAX_SVG_BYTES = 16 * 1024 * 1024
CONTENT_TYPES = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}
PAGE_WIDTH = 2100
PAGE_HEIGHT = 2970
PNG_DPI = 144
MAX_CONCURRENT_RENDERS = 2
RENDER_QUEUE_TIMEOUT_SECONDS = 5
REQUIRED_FONT_FAMILY = "Noto Sans CJK"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
INKSCAPE_NAMESPACE = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NAMESPACE = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

register_namespace("", SVG_NAMESPACE)
register_namespace("inkscape", INKSCAPE_NAMESPACE)
register_namespace("sodipodi", SODIPODI_NAMESPACE)
RENDER_SLOTS = BoundedSemaphore(MAX_CONCURRENT_RENDERS)
VEROVIO_LOCK = Lock()
CancelCheck = Callable[[], bool]


class RenderCancelled(RuntimeError):
    pass


class VerovioToolkit(Protocol):
    def getVersion(self) -> str: ...

    def setOptions(self, options: dict[str, object]) -> None: ...

    def loadData(self, data: str) -> bool: ...

    def getPageCount(self) -> int: ...

    def renderToSVG(self, page: int) -> str: ...


VEROVIO_TOOLKIT: VerovioToolkit | None = None


def initialize_engraver() -> VerovioToolkit:
    global VEROVIO_TOOLKIT
    if VEROVIO_TOOLKIT is None:
        import verovio  # type: ignore[import-not-found]

        VEROVIO_TOOLKIT = cast(VerovioToolkit, verovio.toolkit())
    return VEROVIO_TOOLKIT


@lru_cache
def renderer_metadata() -> dict[str, str]:
    toolkit = initialize_engraver()
    inkscape_version = subprocess.run(
        ["inkscape", "--version"],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    ).stdout.strip()
    font = subprocess.run(
        ["fc-match", "Noto Sans CJK SC", "--format=%{family}"],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if REQUIRED_FONT_FAMILY.casefold() not in font.casefold():
        raise RuntimeError(f"required font is unavailable: {REQUIRED_FONT_FAMILY}")
    return {
        "engraver": f"Verovio {toolkit.getVersion()}",
        "converter": inkscape_version,
        "font": font,
        "page_width": str(PAGE_WIDTH),
        "page_height": str(PAGE_HEIGHT),
        "png_dpi": str(PNG_DPI),
        "max_concurrent_renders": str(MAX_CONCURRENT_RENDERS),
    }


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_converter(command: list[str], cancel_check: CancelCheck | None = None) -> None:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = monotonic() + 90
    while True:
        if cancel_check and cancel_check():
            _stop_process(process)
            raise RenderCancelled("render request was cancelled")
        remaining = deadline - monotonic()
        if remaining <= 0:
            _stop_process(process)
            raise subprocess.TimeoutExpired(command, 90)
        try:
            stdout, stderr = process.communicate(timeout=min(0.1, remaining))
            break
        except subprocess.TimeoutExpired:
            continue
    if process.returncode:
        raise subprocess.CalledProcessError(
            process.returncode, command, output=stdout, stderr=stderr
        )


def render(
    svg: bytes, output_format: str, cancel_check: CancelCheck | None = None
) -> bytes:
    if output_format not in CONTENT_TYPES:
        raise ValueError("unsupported output format")
    try:
        root = fromstring(svg)
    except (ParseError, ValueError) as error:
        raise ValueError("request body must be an SVG document") from error
    if root.tag not in {"svg", f"{{{SVG_NAMESPACE}}}svg"}:
        raise ValueError("request body must be an SVG document")
    if cancel_check and cancel_check():
        raise RenderCancelled("render request was cancelled")
    if output_format == "svg":
        return svg
    with tempfile.TemporaryDirectory(prefix="vss-render-") as directory:
        source = Path(directory) / "score.svg"
        output = Path(directory) / f"score.{output_format}"
        source.write_bytes(_prepare_pdf_svg(svg) if output_format == "pdf" else svg)
        command = [
            "inkscape",
            str(source),
            f"--export-filename={output}",
        ]
        if output_format == "png":
            command.extend(("--export-area-page", f"--export-dpi={PNG_DPI}"))
        _run_converter(command, cancel_check)
        return output.read_bytes()


def _prepare_pdf_svg(svg: bytes) -> bytes:
    root = fromstring(svg)
    if "data-page-count" not in root.attrib:
        return svg
    root.set("height", str(PAGE_HEIGHT))
    root.set("viewBox", f"0 0 {PAGE_WIDTH} {PAGE_HEIGHT}")
    return cast(bytes, tostring(root, encoding="utf-8", xml_declaration=True))


def _prefix_svg_ids(root: Element, prefix: str) -> None:
    replacements: dict[str, str] = {}
    for element in root.iter():
        element_id = element.get("id")
        if element_id:
            replacements[element_id] = f"{prefix}-{element_id}"
            element.set("id", replacements[element_id])
    for element in root.iter():
        for attribute, value in list(element.attrib.items()):
            if value.startswith("#") and value[1:] in replacements:
                element.set(attribute, f"#{replacements[value[1:]]}")
                continue
            updated = value
            for original, replacement in replacements.items():
                updated = updated.replace(f"url(#{original})", f"url(#{replacement})")
            if attribute in {"aria-labelledby", "aria-describedby"}:
                updated = " ".join(replacements.get(item, item) for item in updated.split())
            if updated != value:
                element.set(attribute, updated)
        if element.tag == f"{{{SVG_NAMESPACE}}}style" and element.text:
            for original, replacement in replacements.items():
                element.text = element.text.replace(f"#{original}", f"#{replacement}")


def _combine_svg_pages(pages: list[str]) -> bytes:
    if not pages:
        raise ValueError("Verovio produced no pages")
    root = Element(
        f"{{{SVG_NAMESPACE}}}svg",
        {
            "width": str(PAGE_WIDTH),
            "height": str(PAGE_HEIGHT * len(pages)),
            "viewBox": f"0 0 {PAGE_WIDTH} {PAGE_HEIGHT * len(pages)}",
            "data-page-count": str(len(pages)),
        },
    )
    named_view = SubElement(root, f"{{{SODIPODI_NAMESPACE}}}namedview")
    for index, page_source in enumerate(pages):
        SubElement(
            named_view,
            f"{{{INKSCAPE_NAMESPACE}}}page",
            {
                "x": "0",
                "y": str(index * PAGE_HEIGHT),
                "width": str(PAGE_WIDTH),
                "height": str(PAGE_HEIGHT),
            },
        )
        page = fromstring(page_source)
        _prefix_svg_ids(page, f"page-{index + 1}")
        page.set("x", "0")
        page.set("y", str(index * PAGE_HEIGHT))
        page.set("width", str(PAGE_WIDTH))
        page.set("height", str(PAGE_HEIGHT))
        root.append(page)
    return cast(bytes, tostring(root, encoding="utf-8", xml_declaration=True))


def engrave_musicxml(
    musicxml: bytes, cancel_check: CancelCheck | None = None
) -> bytes:
    toolkit = initialize_engraver()
    if cancel_check and cancel_check():
        raise RenderCancelled("render request was cancelled")
    with VEROVIO_LOCK:
        toolkit.setOptions(
            {
                "adjustPageHeight": False,
                "breaks": "auto",
                "footer": "none",
                "header": "auto",
                "pageHeight": PAGE_HEIGHT,
                "pageWidth": PAGE_WIDTH,
                "scale": 42,
            }
        )
        if not toolkit.loadData(musicxml.decode("utf-8")):
            raise ValueError("Verovio could not load the MusicXML document")
        pages: list[str] = []
        for page in range(1, toolkit.getPageCount() + 1):
            if cancel_check and cancel_check():
                raise RenderCancelled("render request was cancelled")
            pages.append(toolkit.renderToSVG(page))
        return _combine_svg_pages(pages)


class RendererHandler(BaseHTTPRequestHandler):
    def _client_disconnected(self) -> bool:
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return False
            data = cast(
                bytes,
                self.connection.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT),
            )
            return data == b""
        except (BlockingIOError, InterruptedError):
            return False
        except OSError:
            return True

    server_version = "VocalScoreRenderer/1.0"

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/health":
            self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            return
        try:
            metadata = renderer_metadata()
        except (
            ImportError,
            AttributeError,
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
        ):
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "unavailable", "renderer": "score-renderer"},
            )
            return
        self._json(
            HTTPStatus.OK,
            {"status": "ok", **metadata},
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/render", "/engrave"}:
            self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            return
        output_format = parse_qs(parsed.query).get("format", [""])[0]
        if output_format not in CONTENT_TYPES:
            self._json(HTTPStatus.BAD_REQUEST, {"code": "UNSUPPORTED_FORMAT"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_SVG_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"code": "INVALID_SVG_SIZE"})
            return
        try:
            renderer_metadata()
        except (
            ImportError,
            AttributeError,
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"code": "RENDERER_UNAVAILABLE", "message": str(error)},
            )
            return
        try:
            source = self.rfile.read(length)
            if not RENDER_SLOTS.acquire(timeout=RENDER_QUEUE_TIMEOUT_SECONDS):
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"code": "RENDERER_BUSY", "message": "renderer queue is full"},
                )
                return
            try:
                svg = (
                    engrave_musicxml(source, self._client_disconnected)
                    if parsed.path == "/engrave"
                    else source
                )
                output = render(svg, output_format, self._client_disconnected)
            finally:
                RENDER_SLOTS.release()
        except RenderCancelled:
            self.close_connection = True
            return
        except (UnicodeDecodeError, ValueError) as error:
            code = "INVALID_MUSICXML" if parsed.path == "/engrave" else "INVALID_SVG"
            self._json(HTTPStatus.BAD_REQUEST, {"code": code, "message": str(error)})
            return
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self._json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"code": "RENDER_FAILED", "message": str(error)},
            )
            return
        if self._client_disconnected():
            self.close_connection = True
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES[output_format])
        self.send_header("Content-Length", str(len(output)))
        try:
            metadata = renderer_metadata()
        except (
            ImportError,
            AttributeError,
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
        ):
            metadata = {}
        for key, value in metadata.items():
            header = "-".join(part.capitalize() for part in key.split("_"))
            self.send_header(f"X-Renderer-{header}", value)
        try:
            page_count = fromstring(svg).get("data-page-count", "1")
        except ValueError:
            page_count = "1"
        self.send_header("X-Renderer-Page-Count", page_count)
        self.end_headers()
        try:
            self.wfile.write(output)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        print(f"score-renderer: {format % args}", flush=True)


if __name__ == "__main__":
    renderer_metadata()
    ThreadingHTTPServer(("0.0.0.0", 8090), RendererHandler).serve_forever()
