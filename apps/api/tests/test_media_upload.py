import io
import json
import os
import shutil
import subprocess
import uuid

import pytest
from conftest import add_product
from test_admin import admin_headers

from app.config import get_settings
from app.main import app
from app.models import AdminAuditLog, ProductImage


def _tiny_png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), color=(120, 200, 90)).save(buf, "PNG")
    return buf.getvalue()


def _noise_png(pixels: int) -> bytes:
    """A real (openable) PNG that won't compress small, for size-cap tests."""
    from PIL import Image

    buf = io.BytesIO()
    Image.frombytes("RGB", (pixels, pixels), os.urandom(pixels * pixels * 3)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def uploads_dir_override(tmp_path):
    settings = get_settings().model_copy(update={"uploads_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: settings
    yield tmp_path
    app.dependency_overrides.pop(get_settings, None)


def test_admin_can_upload_a_photo(client, db, uploads_dir_override):
    headers = admin_headers(client, db)
    product = add_product(db)

    response = client.post(
        f"/api/v1/admin/products/{product.id}/images/upload",
        headers=headers,
        files={"file": ("photo.png", _tiny_png(), "image/png")},
        data={"alt_text": "A cup of matcha", "caption": "Whisked fresh at pickup"},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["images"]) == 1
    image = body["images"][0]
    assert image["media_type"] == "image"
    assert image["url"].startswith("/uploads/")
    assert image["caption"] == "Whisked fresh at pickup"

    product_response = client.get(f"/api/v1/products/{product.slug}")
    assert product_response.status_code == 200
    public_image = product_response.json()["images"][0]
    assert public_image["caption"] == "Whisked fresh at pickup"

    stored = db.query(ProductImage).filter_by(id=uuid.UUID(image["id"])).one()
    assert stored.url == image["url"]
    saved_files = list(uploads_dir_override.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].suffix == ".jpg"

    log = db.query(AdminAuditLog).filter_by(action="product_image_added").one()
    assert log.entity_id == str(product.id)
    detail = json.loads(log.detail)
    assert detail["media_type"] == "image"
    assert detail["filename"] == "photo.png"


def test_admin_upload_requires_auth(client, db):
    product = add_product(db)
    response = client.post(
        f"/api/v1/admin/products/{product.id}/images/upload",
        files={"file": ("photo.png", _tiny_png(), "image/png")},
    )
    assert response.status_code == 401


def test_admin_upload_rejects_oversized_image(client, db, uploads_dir_override):
    headers = admin_headers(client, db)
    product = add_product(db)
    settings = get_settings().model_copy(
        update={"uploads_dir": str(uploads_dir_override), "max_image_upload_mb": 1}
    )
    app.dependency_overrides[get_settings] = lambda: settings

    response = client.post(
        f"/api/v1/admin/products/{product.id}/images/upload",
        headers=headers,
        # A real, decodable PNG of random noise -- comfortably over 1 MB.
        files={"file": ("big.png", _noise_png(900), "image/png")},
    )
    assert response.status_code == 422
    assert "MB" in response.json()["detail"]
    assert db.query(ProductImage).count() == 0


def test_admin_upload_rejects_unsupported_file(client, db, uploads_dir_override):
    headers = admin_headers(client, db)
    product = add_product(db)

    response = client.post(
        f"/api/v1/admin/products/{product.id}/images/upload",
        headers=headers,
        files={"file": ("notes.txt", os.urandom(2048), "text/plain")},
    )
    assert response.status_code == 422
    assert db.query(ProductImage).count() == 0


def _video_probe(path):
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(probe.stdout)["streams"][0]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_admin_can_upload_and_remux_an_h264_video(client, db, uploads_dir_override):
    """An already-h264 source should be remuxed losslessly, keeping the exact
    source resolution (no more downscaling to 720p) and codec."""
    headers = admin_headers(client, db)
    product = add_product(db)

    clip = uploads_dir_override / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=1280x960:rate=10",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(clip),
        ],
        check=True,
        capture_output=True,
    )
    source_probe = _video_probe(clip)
    assert source_probe["codec_name"] == "h264"

    response = client.post(
        f"/api/v1/admin/products/{product.id}/images/upload",
        headers=headers,
        files={"file": ("clip.mp4", clip.read_bytes(), "video/mp4")},
        data={"alt_text": "Pouring the drink"},
    )
    assert response.status_code == 201
    image = response.json()["images"][0]
    assert image["media_type"] == "video"
    assert image["url"].startswith("/uploads/")

    stored = uploads_dir_override / image["url"].removeprefix("/uploads/")
    stored_probe = _video_probe(stored)
    assert stored_probe["codec_name"] == "h264"
    # Remux path: resolution must exactly match the source -- no downscaling.
    assert stored_probe["width"] == source_probe["width"]
    assert stored_probe["height"] == source_probe["height"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_admin_upload_transcodes_non_h264_video_at_full_resolution(
    client, db, uploads_dir_override
):
    """A non-h264 source (e.g. HEVC) must still be transcoded for browser
    compatibility, but at full resolution rather than downscaled to 720p."""
    headers = admin_headers(client, db)
    product = add_product(db)

    clip = uploads_dir_override / "clip.mp4"
    encode = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=1280x960:rate=10",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx265",
            "-tag:v",
            "hvc1",
            str(clip),
        ],
        capture_output=True,
    )
    if encode.returncode != 0:
        pytest.skip("ffmpeg build has no libx265 encoder")
    source_probe = _video_probe(clip)
    assert source_probe["codec_name"] == "hevc"

    response = client.post(
        f"/api/v1/admin/products/{product.id}/images/upload",
        headers=headers,
        files={"file": ("clip.mp4", clip.read_bytes(), "video/mp4")},
        data={"alt_text": "Pouring the drink"},
    )
    assert response.status_code == 201
    image = response.json()["images"][0]
    assert image["media_type"] == "video"

    stored = uploads_dir_override / image["url"].removeprefix("/uploads/")
    stored_probe = _video_probe(stored)
    assert stored_probe["codec_name"] == "h264"
    assert stored_probe["width"] == source_probe["width"]
    assert stored_probe["height"] == source_probe["height"]
