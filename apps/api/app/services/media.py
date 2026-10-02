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
MAX_VIDEO_DURATION_SECONDS = 90
FFMPEG_TIMEOUT_SECONDS = 600
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
    # below once we know what we're looking at. Videos use their hard reject
    # cap here (not the compression threshold), since anything between the
    # threshold and the hard cap is accepted and compressed, not rejected.
    combined_cap_mb = max(settings.max_image_upload_mb, settings.max_video_upload_hard_mb)
    combined_cap_bytes = combined_cap_mb * 1024 * 1024

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = _stream_to_tempfile(upload, combined_cap_bytes, Path(tmp_dir))
        kind = _detect_kind(tmp_path)
        if kind is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, _UNSUPPORTED_MESSAGE)

        if kind == "image":
            cap_mb = settings.max_image_upload_mb
            if tmp_path.stat().st_size > cap_mb * 1024 * 1024:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"That photo is larger than {cap_mb} MB -- try a smaller file.",
                )
            filename = _process_image(tmp_path, uploads_dir)
        else:
            hard_cap_mb = settings.max_video_upload_hard_mb
            if tmp_path.stat().st_size > hard_cap_mb * 1024 * 1024:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"That video is larger than {hard_cap_mb} MB -- trim or export a smaller file.",
                )
            compress = tmp_path.stat().st_size > settings.max_video_upload_mb * 1024 * 1024
            filename = _process_video(tmp_path, uploads_dir, compress=compress)

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


def _probe_streams(tmp_path: Path) -> list[dict] | None:
    """Runs ffprobe once and returns the raw stream list, or None on failure."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(tmp_path)],
            capture_output=True,
            timeout=30,
            text=True,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if probe.returncode != 0:
        return None
    try:
        data = json.loads(probe.stdout)
    except json.JSONDecodeError:
        return None
    return data.get("streams", [])


def _has_video_stream(tmp_path: Path) -> bool:
    streams = _probe_streams(tmp_path)
    if streams is None:
        return False
    return any(stream.get("codec_type") == "video" for stream in streams)


def _stream_codecs(tmp_path: Path) -> tuple[str | None, str | None]:
    """Returns (video_codec_name, audio_codec_name) for the first video and
    audio streams found, or None for either that's absent/unreadable."""
    streams = _probe_streams(tmp_path) or []
    video_codec = next(
        (s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None
    )
    audio_codec = next(
        (s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None
    )
    return video_codec, audio_codec


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


def _process_video(tmp_path: Path, dest_dir: Path, compress: bool = False) -> str:
    duration = _video_duration(tmp_path)
    if duration is None or duration > MAX_VIDEO_DURATION_SECONDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Videos can be at most 90 seconds long -- trim it and try again.",
        )

    filename = f"{secrets.token_hex(8)}.mp4"
    dest = dest_dir / filename
    video_codec, audio_codec = _stream_codecs(tmp_path)

    if compress:
        # Over the compression threshold: always transcode (even if already
        # h264) to actually shrink the file, rather than remuxing it as-is.
        # crf 21 is near-transparent for real-world footage and reliably
        # shrinks phone videos well under the threshold; original resolution
        # is kept since crf-based quality scaling makes a downscale
        # unnecessary for a size win.
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    elif video_codec == "h264":
        # Already browser-playable: remux into an mp4 container losslessly
        # instead of re-encoding, so uploaded quality is preserved exactly.
        # Audio is copied as-is when it's already aac; anything else (e.g.
        # some phones ship mp3 or pcm in an h264 clip) needs a quick audio-only
        # transcode since the container/codec pairing must be mp4-compatible.
        audio_args = ["-c:a", "copy"] if audio_codec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_path),
            "-c:v",
            "copy",
            *audio_args,
            "-movflags",
            "+faststart",
            str(dest),
        ]
    else:
        # Non-h264 sources (HEVC from iPhones, VP9, etc.) aren't reliably
        # playable in browsers, so a transcode is unavoidable here -- but we
        # keep the original resolution (no more downscaling to 720p) and use
        # crf 18, which is "visually lossless" (indistinguishable from the
        # source to the eye) rather than the old, visibly-compressed crf 26.
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(dest),
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT_SECONDS)
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
