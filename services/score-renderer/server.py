from __future__ import annotations

import json
import subprocess
import tempfile
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import Element, SubElement, fromstring, register_namespace, tostring

MAX_SVG_BYTES = 16 * 1024 * 1024
CONTENT_TYPES = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}
PAGE_WIDTH = 2100
PAGE_HEIGHT = 2970
PNG_DPI = 144
MAX_CONCURRENT_RENDERS = 2
RENDER_QUEUE_TIMEOUT_SECONDS = 5
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
INKSCAPE_NAMESPACE = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NAMESPACE = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

register_namespace("", SVG_NAMESPACE)
register_namespace("inkscape", INKSCAPE_NAMESPACE)
register_namespace("sodipodi", SODIPODI_NAMESPACE)
RENDER_SLOTS = BoundedSemaphore(MAX_CONCURRENT_RENDERS)


@lru_cache
def renderer_metadata() -> dict[str, str]:
    import verovio

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
    return {
        "engraver": f"Verovio {verovio.getVersion()}",
        "converter": inkscape_version,
        "font": font or "Noto Sans CJK SC",
        "page_width": str(PAGE_WIDTH),
        "page_height": str(PAGE_HEIGHT),
        "png_dpi": str(PNG_DPI),
        "max_concurrent_renders": str(MAX_CONCURRENT_RENDERS),
    }


def render(svg: bytes, output_format: str) -> bytes:
    if output_format not in CONTENT_TYPES:
        raise ValueError("unsupported output format")
    if not svg.lstrip().startswith(b"<svg"):
        raise ValueError("request body must be an SVG document")
    if output_format == "svg":
        return svg
    with tempfile.TemporaryDirectory(prefix="vss-render-") as directory:
        source = Path(directory) / "score.svg"
        output = Path(directory) / f"score.{output_format}"
        source.write_bytes(svg)
        command = [
            "inkscape",
            str(source),
            f"--export-filename={output}",
        ]
        if output_format == "png":
            command.extend(("--export-area-drawing", f"--export-dpi={PNG_DPI}"))
        subprocess.run(command, check=True, timeout=90, capture_output=True)
        return output.read_bytes()


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
        page.set("x", "0")
        page.set("y", str(index * PAGE_HEIGHT))
        page.set("width", str(PAGE_WIDTH))
        page.set("height", str(PAGE_HEIGHT))
        root.append(page)
    return tostring(root, encoding="utf-8", xml_declaration=True)


def engrave_musicxml(musicxml: bytes) -> bytes:
    import verovio

    toolkit = verovio.toolkit()
    toolkit.setOptions(
        {
            "adjustPageHeight": False,
            "breaks": "auto",
            "footer": "none",
            "header": "none",
            "pageHeight": PAGE_HEIGHT,
            "pageWidth": PAGE_WIDTH,
            "scale": 42,
        }
    )
    if not toolkit.loadData(musicxml.decode("utf-8")):
        raise ValueError("Verovio could not load the MusicXML document")
    return _combine_svg_pages(
        [toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1)]
    )


class RendererHandler(BaseHTTPRequestHandler):
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
        except (ImportError, AttributeError, OSError, subprocess.SubprocessError):
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
            source = self.rfile.read(length)
            if not RENDER_SLOTS.acquire(timeout=RENDER_QUEUE_TIMEOUT_SECONDS):
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"code": "RENDERER_BUSY", "message": "renderer queue is full"},
                )
                return
            try:
                svg = engrave_musicxml(source) if parsed.path == "/engrave" else source
                output = render(svg, output_format)
            finally:
                RENDER_SLOTS.release()
        except ValueError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"code": "INVALID_SVG", "message": str(error)})
            return
        except (OSError, subprocess.SubprocessError) as error:
            self._json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"code": "RENDER_FAILED", "message": str(error)},
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES[output_format])
        self.send_header("Content-Length", str(len(output)))
        try:
            metadata = renderer_metadata()
        except (ImportError, AttributeError, OSError, subprocess.SubprocessError):
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
        self.wfile.write(output)

    def log_message(self, format: str, *args: object) -> None:
        print(f"score-renderer: {format % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), RendererHandler).serve_forever()
