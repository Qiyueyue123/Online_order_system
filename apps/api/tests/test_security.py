def test_registration_sets_opaque_http_only_session(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "shopper@example.com", "password": "long-password", "name": "Shopper"},
    )
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["csrf_token"]


def test_admin_stock_requires_authentication(client):
    response = client.patch(
        "/api/v1/admin/variants/00000000-0000-0000-0000-000000000000/stock",
        json={"stock_on_hand": 4, "reason": "stock count"},
    )
    assert response.status_code == 401
