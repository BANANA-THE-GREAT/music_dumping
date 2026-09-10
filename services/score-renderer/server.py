from __future__ import annotations

import json
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_SVG_BYTES = 16 * 1024 * 1024
CONTENT_TYPES = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}


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
            "--export-area-page",
            f"--export-filename={output}",
        ]
        if output_format == "png":
            command.append("--export-dpi=144")
        subprocess.run(command, check=True, timeout=90, capture_output=True)
        return output.read_bytes()


def engrave_musicxml(musicxml: bytes) -> bytes:
    import verovio

    toolkit = verovio.toolkit()
    toolkit.setOptions(
        {
            "adjustPageHeight": True,
            "breaks": "auto",
            "footer": "none",
            "header": "none",
            "pageHeight": 60000,
            "pageWidth": 2100,
            "scale": 42,
        }
    )
    if not toolkit.loadData(musicxml.decode("utf-8")):
        raise ValueError("Verovio could not load the MusicXML document")
    return toolkit.renderToSVG(1).encode("utf-8")


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
            version = subprocess.run(
                ["inkscape", "--version"],
                check=True,
                timeout=10,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "unavailable", "renderer": "inkscape"},
            )
            return
        try:
            import verovio

            verovio_version = verovio.getVersion()
        except (ImportError, AttributeError):
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "unavailable", "renderer": "verovio"},
            )
            return
        self._json(
            HTTPStatus.OK,
            {"status": "ok", "renderer": version, "engraver": verovio_version},
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
            svg = engrave_musicxml(source) if parsed.path == "/engrave" else source
            output = render(svg, output_format)
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
        self.end_headers()
        self.wfile.write(output)

    def log_message(self, format: str, *args: object) -> None:
        print(f"score-renderer: {format % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), RendererHandler).serve_forever()
