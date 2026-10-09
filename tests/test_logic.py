from datetime import date, timedelta
from decimal import Decimal

from app.logic import (
    hash_password, is_due, policies_to_csv, validate_client, validate_policy, verify_password,
)

TODAY = date(2026, 10, 9)


def good_policy(**changes):
    form = {"policy_number": "POL-1", "type": "Health", "insurer": "Acme", "premium": "1250.5",
            "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "active", "notes": ""}
    form.update(changes)
    return form


def test_valid_policy_is_cleaned():
    clean, errors = validate_policy(good_policy())
    assert errors == {}
    assert clean["premium"] == Decimal("1250.50")
    assert clean["end_date"] == date(2026, 12, 31)


def test_end_date_must_follow_start_date():
    _, errors = validate_policy(good_policy(end_date="2026-01-01"))
    assert errors["end_date"] == "End date must be after the start date."


def test_bad_premium_values_are_rejected():
    for bad in ("", "0", "-5", "abc", "NaN", "Infinity"):
        _, errors = validate_policy(good_policy(premium=bad))
        assert "premium" in errors, bad


def test_status_and_required_fields():
    _, errors = validate_policy(good_policy(status="pending", insurer="  "))
    assert "status" in errors and "insurer" in errors


def test_client_validation():
    assert validate_client({"name": "Asha Rao", "email": "a@b.com"})[1] == {}
    assert "name" in validate_client({"name": " "})[1]
    for bad in ("nope", "a@b", "@b.com", "a b@c.com"):
        assert "email" in validate_client({"name": "X", "email": bad})[1], bad


def test_renewal_window_boundaries():
    assert is_due(TODAY, "active", TODAY)
    assert is_due(TODAY + timedelta(days=30), "active", TODAY)
    assert not is_due(TODAY + timedelta(days=31), "active", TODAY)
    assert not is_due(TODAY - timedelta(days=1), "active", TODAY)
    assert not is_due(TODAY + timedelta(days=5), "cancelled", TODAY)


def test_csv_escapes_and_blocks_formula_injection():
    text = policies_to_csv([('=HYPERLINK("x")', "P,1", "Health", 'Ac"me', Decimal("10.00"),
                             date(2026, 1, 1), date(2026, 12, 31), "active")])
    lines = text.splitlines()
    assert lines[0].startswith("Client,Policy number")
    assert "'=HYPERLINK" in text and '"P,1"' in text and '"Ac""me"' in text


def test_password_hashing():
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "garbage")
