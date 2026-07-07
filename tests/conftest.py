import re
import secrets
import sys
from pathlib import Path

from flask.testing import FlaskClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CSRF_FIELD_PATTERN = re.compile(
    rb'name="_csrf_token" type="hidden" value="([^"]+)"'
)


def extract_csrf_token(html_bytes):
    """Pull the CSRF token out of a rendered page's hidden form field."""
    match = CSRF_FIELD_PATTERN.search(html_bytes)
    if not match:
        raise AssertionError("No CSRF token field found in response body.")
    return match.group(1).decode("utf-8")


class CsrfTestClient(FlaskClient):
    """Test client that transparently attaches a valid CSRF token to POSTs.

    Real CSRF enforcement is left switched on for the test app (see
    app/__init__.py), so every POST must carry a token that matches the one
    stored in the session. Rather than forcing every existing test to fetch
    a page and scrape the token by hand, this client writes a token directly
    into the session (the same session the app reads from) and attaches it
    to outgoing POST bodies. Pass csrf=False to opt out for a specific call
    (e.g. to test that missing/invalid tokens are rejected).
    """

    def get_csrf_token(self):
        with self.session_transaction() as session:
            token = session.get("_csrf_token")
            if not token:
                token = secrets.token_urlsafe(32)
                session["_csrf_token"] = token
            return token

    def post(self, *args, csrf=True, **kwargs):
        if csrf:
            data = kwargs.get("data")
            if data is None:
                data = {}
            else:
                data = dict(data)
            data.setdefault("_csrf_token", self.get_csrf_token())
            kwargs["data"] = data
        return super().post(*args, **kwargs)
