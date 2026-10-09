from datetime import date, timedelta

import pytest

from tests.conftest import csrf_from


def post(client, path, data):
    """Submit a form with the CSRF token a logged-in browser would hold."""
    token = csrf_from(client.get("/clients").text)
    return client.post(path, data={**data, "csrf": token}, follow_redirects=False)


def policy_data(**changes):
    data = {"policy_number": "POL-001", "type": "Health", "insurer": "Acme Assurance", "premium": "1250.50",
            "start_date": (date.today() - timedelta(days=355)).isoformat(),
            "end_date": (date.today() + timedelta(days=10)).isoformat(), "status": "active", "notes": ""}
    data.update(changes)
    return data


def add_client(client, name="Asha Rao"):
    response = post(client, "/clients/new", {"name": name, "email": name.split()[0].lower() + "@example.com"})
    assert response.status_code == 303
    return int(response.headers["location"].rsplit("/", 1)[1])


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/clients", "/clients/new", "/policies", "/policies.csv", "/renewals"])
def test_pages_require_login(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_wrong_password_is_rejected(client):
    token = csrf_from(client.get("/login").text)
    response = client.post("/login", data={"username": "admin", "password": "nope", "csrf": token})
    assert response.status_code == 401 and "Incorrect username or password" in response.text


def test_post_without_csrf_token_is_rejected(auth):
    assert auth.post("/clients/new", data={"name": "X"}).status_code == 403


def test_client_and_policy_flow(auth):
    cid = add_client(auth)
    assert post(auth, f"/clients/{cid}/policies/new", policy_data()).status_code == 303
    assert "POL-001" in auth.get(f"/clients/{cid}").text
    assert "POL-001" in auth.get("/renewals").text
    csv_text = auth.get("/policies.csv").text
    assert csv_text.startswith("Client,Policy number") and "POL-001" in csv_text


def test_duplicate_policy_number_is_rejected(auth):
    cid = add_client(auth)
    post(auth, f"/clients/{cid}/policies/new", policy_data())
    response = post(auth, f"/clients/{cid}/policies/new", policy_data())
    assert response.status_code == 422 and "already exists" in response.text


def test_invalid_dates_show_an_error(auth):
    cid = add_client(auth)
    bad = policy_data(end_date=(date.today() - timedelta(days=400)).isoformat())
    response = post(auth, f"/clients/{cid}/policies/new", bad)
    assert response.status_code == 422 and "End date must be after the start date" in response.text


def test_far_future_policy_is_not_a_renewal(auth):
    cid = add_client(auth)
    far = policy_data(end_date=(date.today() + timedelta(days=90)).isoformat())
    post(auth, f"/clients/{cid}/policies/new", far)
    assert "POL-001" not in auth.get("/renewals").text


def test_client_search_and_status_filter(auth):
    cid = add_client(auth, "Asha Rao")
    add_client(auth, "Ravi Iyer")
    post(auth, f"/clients/{cid}/policies/new", policy_data(status="lapsed"))
    found = auth.get("/clients?q=Asha").text
    assert "Asha Rao" in found and "Ravi Iyer" not in found
    assert "POL-001" in auth.get("/policies?status=lapsed").text
    assert "POL-001" not in auth.get("/policies?status=active").text


def test_deleting_a_client_removes_their_policies(auth):
    cid = add_client(auth)
    post(auth, f"/clients/{cid}/policies/new", policy_data())
    assert post(auth, f"/clients/{cid}/delete", {}).status_code == 303
    assert "POL-001" not in auth.get("/policies.csv").text
