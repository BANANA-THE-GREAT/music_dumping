from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, tostring


def musicxml(measure_count: int) -> bytes:
    score = Element("score-partwise", version="4.0")
    part_list = SubElement(score, "part-list")
    score_part = SubElement(part_list, "score-part", id="P1")
    SubElement(score_part, "part-name").text = "Benchmark"
    part = SubElement(score, "part", id="P1")
    for measure_index in range(measure_count):
        measure = SubElement(part, "measure", number=str(measure_index + 1))
        if measure_index == 0:
            attributes = SubElement(measure, "attributes")
            SubElement(attributes, "divisions").text = "24"
            time_signature = SubElement(attributes, "time")
            SubElement(time_signature, "beats").text = "4"
            SubElement(time_signature, "beat-type").text = "4"
            clef = SubElement(attributes, "clef")
            SubElement(clef, "sign").text = "G"
            SubElement(clef, "line").text = "2"
        for beat in range(4):
            note = SubElement(measure, "note", id=f"note-{measure_index}-{beat}")
            pitch = SubElement(note, "pitch")
            SubElement(pitch, "step").text = ("C", "D", "E", "G")[beat]
            SubElement(pitch, "octave").text = "4"
            SubElement(note, "duration").text = "24"
            SubElement(note, "type").text = "quarter"
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(score)


def memory_bytes() -> int | None:
    path = Path("/sys/fs/cgroup/memory.current")
    return int(path.read_text()) if path.exists() else None


def request_render(url: str, source: bytes, output_format: str) -> dict[str, object]:
    request = Request(
        f"{url.rstrip('/')}/engrave?format={output_format}",
        data=source,
        method="POST",
        headers={"Content-Type": "application/vnd.recordare.musicxml+xml"},
    )
    memory_before = memory_bytes()
    started = time.perf_counter()
    with urlopen(request, timeout=600) as response:
        content = response.read()
        headers = dict(response.headers.items())
    elapsed = time.perf_counter() - started
    memory_after = memory_bytes()
    expected_prefix = {
        "svg": (b"<?xml", b"<svg"),
        "png": (b"\x89PNG",),
        "pdf": (b"%PDF",),
    }[output_format]
    if not content.startswith(expected_prefix):
        raise RuntimeError(f"invalid {output_format} output")
    return {
        "format": output_format,
        "seconds": round(elapsed, 3),
        "bytes": len(content),
        "page_count": int(headers.get("X-Renderer-Page-Count", "1")),
        "memory_before_bytes": memory_before,
        "memory_after_bytes": memory_after,
        "memory_delta_bytes": (
            memory_after - memory_before
            if memory_before is not None and memory_after is not None
            else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    parser.add_argument("--target-pages", default="1,10,50")
    parser.add_argument("--formats", default="svg,png,pdf")
    parser.add_argument("--measures-per-page", type=int, default=12)
    args = parser.parse_args()
    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    results: list[dict[str, object]] = []
    for target in (int(item) for item in args.target_pages.split(",")):
        measure_count = max(1, target * args.measures_per_page)
        source = musicxml(measure_count)
        for output_format in formats:
            result = request_render(args.url, source, output_format)
            result.update({"target_pages": target, "measures": measure_count})
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    print(json.dumps({"results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
