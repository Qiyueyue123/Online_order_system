"""Turns an admin-uploaded photo or video into a served, size-capped file.

Kind is detected from the uploaded bytes (Pillow for images, ffprobe for
videos) rather than trusting the filename or the browser's claimed
content-type, since either can lie about what's actually inside.
"""

import json
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import pillow_heif
from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps

from ..config import Settings

pillow_heif.register_heif_opener()
pillow_heif.register_avif_opener()

MAX_IMAGE_DIMENSION = 1600
MAX_VIDEO_HEIGHT = 720
MAX_VIDEO_DURATION_SECONDS = 90
_UNSUPPORTED_MESSAGE = (
    "That doesn't look like a supported photo or video -- try a JPEG, PNG, "
    "HEIC, MP4 or MOV file."
)


def save_product_media(upload: UploadFile, settings: Settings) -> tuple[str, str]:
    """Validate, resize/transcode, and persist an uploaded file.

    Returns (public_url, media_type) where public_url is a "/uploads/..."
    path and media_type is "image" or "video".
    """
    uploads_dir = Path(settings.uploads_dir)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    # Cap the streamed-to-disk size at the larger of the two limits so we
    # don't reject a valid video while still bailing out of a runaway upload
    # long before it fills the disk; the tighter per-kind cap is enforced
    # below once we know what we're looking at.
    combined_cap_mb = max(settings.max_image_upload_mb, settings.max_video_upload_mb)
    combined_cap_bytes = combined_cap_mb * 1024 * 1024

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = _stream_to_tempfile(upload, combined_cap_bytes, Path(tmp_dir))
        kind = _detect_kind(tmp_path)
        if kind is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _UNSUPPORTED_MESSAGE)

        cap_mb = settings.max_image_upload_mb if kind == "image" else settings.max_video_upload_mb
        if tmp_path.stat().st_size > cap_mb * 1024 * 1024:
            noun = "photo" if kind == "image" else "video"
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"That {noun} is larger than {cap_mb} MB -- try a smaller file.",
            )

        if kind == "image":
            filename = _process_image(tmp_path, uploads_dir)
        else:
            filename = _process_video(tmp_path, uploads_dir)

    return f"/uploads/{filename}", kind


def _stream_to_tempfile(upload: UploadFile, max_bytes: int, tmp_dir: Path) -> Path:
    """Copies the upload to disk in chunks, rejecting it as soon as it grows
    past max_bytes instead of buffering the whole thing in memory first."""
    dest = tmp_dir / "upload"
    total = 0
    upload.file.seek(0)
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file is too large.")
            out.write(chunk)
    return dest


def _detect_kind(tmp_path: Path) -> str | None:
    try:
        with Image.open(tmp_path) as img:
            img.load()
        return "image"
    except Exception:
        pass
    if _has_video_stream(tmp_path):
        return "video"
    return None


def _has_video_stream(tmp_path: Path) -> bool:
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(tmp_path)],
            capture_output=True,
            timeout=30,
            text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if probe.returncode != 0:
        return False
    try:
        data = json.loads(probe.stdout)
    except json.JSONDecodeError:
        return False
    return any(stream.get("codec_type") == "video" for stream in data.get("streams", []))


def _process_image(tmp_path: Path, dest_dir: Path) -> str:
    with Image.open(tmp_path) as img:
        if img.format == "GIF" and getattr(img, "is_animated", False):
            # Re-encoding would flatten the animation to a single frame, so
            # animated GIFs are kept exactly as uploaded.
            filename = f"{secrets.token_hex(8)}.gif"
            shutil.copyfile(tmp_path, dest_dir / filename)
            return filename

        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
        filename = f"{secrets.token_hex(8)}.jpg"
        img.save(dest_dir / filename, "JPEG", quality=85)
        return filename


def _process_video(tmp_path: Path, dest_dir: Path) -> str:
    duration = _video_duration(tmp_path)
    if duration is None or duration > MAX_VIDEO_DURATION_SECONDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Videos can be at most 90 seconds long -- trim it and try again.",
        )

    filename = f"{secrets.token_hex(8)}.mp4"
    dest = dest_dir / filename
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_path),
                # Scale to a max height of 720px, preserving aspect ratio;
                # the -2 keeps the computed width even, which libx264 requires.
                # The comma inside min(...) must be escaped -- ffmpeg's filter
                # graph syntax otherwise reads it as a filter separator.
                "-vf",
                f"scale=-2:min({MAX_VIDEO_HEIGHT}\\,ih)",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "26",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(dest),
            ],
            capture_output=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "We couldn't process that video -- try again."
        ) from exc

    if result.returncode != 0 or not dest.exists():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "We couldn't process that video -- try again."
        )
    return filename


def _video_duration(tmp_path: Path) -> float | None:
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=30,
            text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if probe.returncode != 0:
        return None
    try:
        return float(json.loads(probe.stdout)["format"]["duration"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
