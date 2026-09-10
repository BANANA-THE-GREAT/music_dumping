from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest
from app.renderer_client import (
    RendererFailedError,
    RendererUnavailableError,
    convert_svg,
    engrave_musicxml,
)


class ResponseBuffer(BytesIO):
    def __enter__(self) -> "ResponseBuffer":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_convert_svg_posts_to_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: int) -> ResponseBuffer:
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["timeout"] = timeout
        return ResponseBuffer(b"PNG")

    monkeypatch.setattr("app.renderer_client.urlopen", fake_urlopen)
    assert convert_svg(b"<svg></svg>", "png", "http://renderer:8090/") == b"PNG"
    assert captured == {
        "url": "http://renderer:8090/render?format=png",
        "data": b"<svg></svg>",
        "timeout": 120,
    }


def test_engrave_musicxml_posts_musicxml(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: int) -> ResponseBuffer:
        captured["url"] = request.full_url
        captured["content_type"] = request.headers["Content-type"]
        return ResponseBuffer(b"<svg></svg>")

    monkeypatch.setattr("app.renderer_client.urlopen", fake_urlopen)
    assert engrave_musicxml(b"<score-partwise/>", "svg", "http://renderer") == b"<svg></svg>"
    assert captured == {
        "url": "http://renderer/engrave?format=svg",
        "content_type": "application/vnd.recordare.musicxml+xml",
    }


def test_convert_svg_reports_unavailable_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RendererUnavailableError):
        convert_svg(b"<svg></svg>", "pdf", None)

    def unavailable(*args: object, **kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr("app.renderer_client.urlopen", unavailable)
    with pytest.raises(RendererUnavailableError):
        convert_svg(b"<svg></svg>", "pdf", "http://renderer:8090")


def test_convert_svg_reports_renderer_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(*args: object, **kwargs: object) -> None:
        raise HTTPError("http://renderer", 422, "failed", {}, None)

    monkeypatch.setattr("app.renderer_client.urlopen", failed)
    with pytest.raises(RendererFailedError):
        convert_svg(b"<svg></svg>", "png", "http://renderer:8090")
