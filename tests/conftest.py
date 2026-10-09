import os
import re
import tempfile

import pytest

# Use a throwaway database and known login. Must be set before the app is imported.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["ENV"] = "test"
os.environ["ADMIN_USERNAME"] = "admin"

from app.logic import hash_password  # noqa: E402

os.environ["ADMIN_PASSWORD_HASH"] = hash_password("test-pass")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


def csrf_from(html):
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match, "no CSRF token on page"
    return match.group(1)


@pytest.fixture
def auth(client):
    token = csrf_from(client.get("/login").text)
    response = client.post("/login", data={"username": "admin", "password": "test-pass", "csrf": token},
                           follow_redirects=False)
    assert response.status_code == 303
    return client
