import hashlib
import shutil
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import Settings


class UploadTooLargeError(Exception):
    pass


def remove_project_files(settings: Settings, object_key: str, job_id: str) -> None:
    root = settings.data_dir.resolve()
    source = (root / object_key).resolve()
    work = (root / "work" / job_id).resolve()
    if root not in source.parents or root not in work.parents:
        raise ValueError("Refusing to remove files outside the data directory")
    source.unlink(missing_ok=True)
    shutil.rmtree(work, ignore_errors=True)
    for directory in (source.parent, source.parent.parent):
        with suppress(OSError):
            directory.rmdir()


async def save_upload(file: UploadFile, settings: Settings) -> tuple[str, int, str]:
    upload_id = str(uuid4())
    suffix = Path(file.filename or "audio.bin").suffix.lower()
    object_key = f"uploads/{upload_id}/source{suffix}"
    target = settings.data_dir / object_key
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UploadTooLargeError
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return object_key, size, digest.hexdigest()
