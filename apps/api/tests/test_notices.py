from datetime import UTC, datetime, timedelta

from test_admin import admin_headers, customer_headers

from app.models import AdminAuditLog, Notice, User

NOTICE_BODY = {"title": "Closed Monday", "body": "We're closed for a private event on Monday."}


def create_notice(
    db, *, title="Old news", body="Something from before", active=True, created_at=None
):
    notice = Notice(title=title, body=body, active=active)
    db.add(notice)
    db.commit()
    if created_at is not None:
        # created_at has server-side (second-resolution) precision, so tests that
        # care about ordering need distinct timestamps set explicitly rather than
        # relying on insertion order within the same second.
        notice.created_at = created_at
        db.commit()
    db.refresh(notice)
    return notice


def test_public_notices_only_shows_active_newest_first(client, db):
    now = datetime.now(UTC)
    older = create_notice(
        db, title="First", body="First notice", created_at=now - timedelta(minutes=2)
    )
    hidden = create_notice(
        db,
        title="Hidden",
        body="Should not show",
        active=False,
        created_at=now - timedelta(minutes=1),
    )
    newer = create_notice(db, title="Second", body="Second notice", created_at=now)

    response = client.get("/api/v1/notices")
    assert response.status_code == 200
    body = response.json()
    titles = [item["title"] for item in body]
    assert titles == ["Second", "First"]
    assert hidden.title not in titles
    assert "active" not in body[0]
    assert body[0]["id"] == str(newer.id)
    assert body[1]["id"] == str(older.id)


def test_admin_routes_require_authentication(client):
    for method, path, kwargs in [
        ("GET", "/api/v1/admin/notices", {}),
        ("POST", "/api/v1/admin/notices", {"json": NOTICE_BODY}),
        (
            "PATCH",
            "/api/v1/admin/notices/00000000-0000-0000-0000-000000000000",
            {"json": {"active": False}},
        ),
        ("DELETE", "/api/v1/admin/notices/00000000-0000-0000-0000-000000000000", {}),
    ]:
        response = client.request(method, path, **kwargs)
        assert response.status_code == 401, path


def test_admin_routes_reject_customer_role(client):
    headers = customer_headers(client)
    response = client.post("/api/v1/admin/notices", json=NOTICE_BODY, headers=headers)
    assert response.status_code == 403


def test_admin_can_create_notice(client, db):
    headers = admin_headers(client, db)
    response = client.post("/api/v1/admin/notices", json=NOTICE_BODY, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Closed Monday"
    assert body["active"] is True

    admin = db.query(User).filter_by(email="admin@example.com").one()
    log = db.query(AdminAuditLog).filter_by(action="notice_created").one()
    assert log.actor_user_id == admin.id
    assert log.entity_type == "notice"


def test_admin_list_notices_includes_inactive(client, db):
    create_notice(db, title="Visible", active=True)
    create_notice(db, title="Hidden", active=False)
    headers = admin_headers(client, db)

    response = client.get("/api/v1/admin/notices", headers=headers)
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()}
    assert titles == {"Visible", "Hidden"}


def test_admin_can_update_and_hide_notice(client, db):
    notice = create_notice(db, title="Original", body="Original body")
    headers = admin_headers(client, db)

    response = client.patch(
        f"/api/v1/admin/notices/{notice.id}",
        json={"title": "Updated", "active": False},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated"
    assert body["body"] == "Original body"
    assert body["active"] is False

    log = db.query(AdminAuditLog).filter_by(action="notice_updated").one()
    assert log.entity_type == "notice"
    assert log.entity_id == str(notice.id)

    public = client.get("/api/v1/notices")
    assert notice.id.hex not in [item["id"].replace("-", "") for item in public.json()]


def test_admin_can_delete_notice(client, db):
    notice = create_notice(db)
    headers = admin_headers(client, db)

    response = client.delete(f"/api/v1/admin/notices/{notice.id}", headers=headers)
    assert response.status_code == 204
    assert db.get(Notice, notice.id) is None

    log = db.query(AdminAuditLog).filter_by(action="notice_deleted").one()
    assert log.entity_type == "notice"


def test_admin_notice_requires_nonempty_fields(client, db):
    headers = admin_headers(client, db)
    response = client.post(
        "/api/v1/admin/notices", json={"title": "", "body": "something"}, headers=headers
    )
    assert response.status_code == 422
