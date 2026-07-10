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
        data={"alt_text": "A cup of matcha"},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["images"]) == 1
    image = body["images"][0]
    assert image["media_type"] == "image"
    assert image["url"].startswith("/uploads/")

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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_admin_can_upload_and_transcode_a_video(client, db, uploads_dir_override):
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
            "testsrc=duration=1:size=320x240:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
        capture_output=True,
    )

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
