"""Create the value for ADMIN_PASSWORD_HASH: python make_hash.py"""
from getpass import getpass

from app.logic import hash_password

password = getpass("New admin password: ")
if len(password) < 12 or password != getpass("Repeat password: "):
    raise SystemExit("Use at least 12 characters, typed the same twice.")
print("\nADMIN_PASSWORD_HASH=" + hash_password(password))
