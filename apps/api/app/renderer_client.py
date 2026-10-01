from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RendererUnavailableError(RuntimeError):
    pass


class RendererFailedError(RuntimeError):
    pass


@dataclass(frozen=True)
class RendererResult:
    content: bytes
    metadata: dict[str, str]


def _post_renderer(
    content: bytes,
    path: str,
    output_format: str,
    content_type: str,
    renderer_url: str | None,
) -> RendererResult:
    if not renderer_url:
        raise RendererUnavailableError("score renderer is not configured")
    request = Request(
        f"{renderer_url.rstrip('/')}/{path}?format={output_format}",
        data=content,
        method="POST",
        headers={"Content-Type": content_type},
    )
    try:
        with urlopen(request, timeout=120) as response:
            headers = getattr(response, "headers", {})
            metadata = {
                key.lower().removeprefix("x-renderer-").replace("-", "_"): value
                for key, value in headers.items()
                if key.lower().startswith("x-renderer-")
            }
            return RendererResult(content=cast(bytes, response.read()), metadata=metadata)
    except HTTPError as error:
        if error.code in {429, 503}:
            raise RendererUnavailableError(
                f"score renderer is temporarily unavailable (HTTP {error.code})"
            ) from error
        raise RendererFailedError(f"renderer returned HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise RendererUnavailableError("score renderer is unavailable") from error


def convert_svg(
    svg: bytes, output_format: str, renderer_url: str | None
) -> RendererResult:
    return _post_renderer(svg, "render", output_format, "image/svg+xml", renderer_url)


def engrave_musicxml(
    musicxml: bytes, output_format: str, renderer_url: str | None
) -> RendererResult:
    return _post_renderer(
        musicxml,
        "engrave",
        output_format,
        "application/vnd.recordare.musicxml+xml",
        renderer_url,
    )
