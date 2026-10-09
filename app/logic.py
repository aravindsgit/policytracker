"""Rules that need no web or database code, so they are easy to test."""
import base64
import csv
import hashlib
import hmac
import io
import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

STATUSES = ("active", "lapsed", "cancelled")
RENEWAL_DAYS = 30
_CSV_RISKY = ("=", "+", "-", "@", "\t", "\r")


def _text(form, key):
    return str(form.get(key) or "").strip()


def validate_client(form):
    clean = {k: _text(form, k) for k in ("name", "email", "phone")}
    errors = {}
    if not clean["name"]:
        errors["name"] = "Enter the client's name."
    elif len(clean["name"]) > 120:
        errors["name"] = "Keep the name under 120 characters."
    email = clean["email"]
    if email:
        local, _, domain = email.partition("@")
        if len(email) > 200 or " " in email or not local or "." not in domain or "@" in domain:
            errors["email"] = "Enter a valid email address, for example name@example.com."
    if len(clean["phone"]) > 30:
        errors["phone"] = "Keep the phone number under 30 characters."
    return clean, errors


def validate_policy(form):
    errors = {}
    clean = {k: _text(form, k) for k in ("policy_number", "type", "insurer", "status", "notes")}
    for key, label in (("policy_number", "policy number"), ("type", "policy type"), ("insurer", "insurer")):
        if not clean[key]:
            errors[key] = f"Enter the {label}."
        elif len(clean[key]) > 100:
            errors[key] = f"Keep the {label} under 100 characters."
    if clean["status"] not in STATUSES:
        errors["status"] = "Choose active, lapsed or cancelled."
    if len(clean["notes"]) > 1000:
        errors["notes"] = "Keep notes under 1000 characters."
    try:
        premium = Decimal(_text(form, "premium"))
        if not premium.is_finite() or premium <= 0 or premium >= Decimal("10000000000"):
            raise InvalidOperation
        clean["premium"] = premium.quantize(Decimal("0.01"))
    except InvalidOperation:
        errors["premium"] = "Enter a premium greater than zero, for example 1250.50."
    for key in ("start_date", "end_date"):
        try:
            clean[key] = date.fromisoformat(_text(form, key))
        except ValueError:
            errors[key] = "Enter a valid date."
    if "start_date" not in errors and "end_date" not in errors and clean["end_date"] <= clean["start_date"]:
        errors["end_date"] = "End date must be after the start date."
    return clean, errors


def is_due(end_date, status, today=None, days=RENEWAL_DAYS):
    """True for active policies ending from today up to `days` days ahead."""
    today = today or date.today()
    return status == "active" and today <= end_date <= today + timedelta(days=days)


def _safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_CSV_RISKY) else text


def policies_to_csv(rows):
    """rows: (client, policy number, type, insurer, premium, start, end, status)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Client", "Policy number", "Type", "Insurer", "Premium", "Start date", "End date", "Status"])
    for row in rows:
        writer.writerow([_safe_cell(v) for v in row])
    return out.getvalue()


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt:" + base64.b64encode(salt).decode() + ":" + base64.b64encode(digest).decode()


def verify_password(password, stored):
    try:
        scheme, salt, digest = stored.split(":")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
