import uuid


def test_response_carries_generated_request_id(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id
    # Should be a valid uuid4 when we didn't supply one ourselves.
    uuid.UUID(request_id)


def test_response_echoes_provided_request_id(client):
    provided = "test-request-id-123"
    response = client.get("/healthz", headers={"X-Request-ID": provided})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == provided


def test_security_headers_present_on_normal_response(client):
    response = client.get("/healthz")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_hsts_absent_when_cookies_not_secure(client):
    response = client.get("/healthz")
    assert "strict-transport-security" not in response.headers
