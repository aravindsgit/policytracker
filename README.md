# Policy Tracker

Small web app for tracking clients and their insurance policies, with a renewals view and CSV export.
Use invented data only unless you have proper security, backups and approval for real client data.

## Run locally
    python -m venv .venv            # then activate it (see the guide)
    pip install -r requirements-dev.txt
    python seed.py                  # invented sample data
    uvicorn app.main:app --reload   # http://127.0.0.1:8000  (local login: admin / admin)

## Test
    pytest -q
    ruff check .

## Deploy (Render + Neon)
1. Create a Neon project and copy its connection string.
2. Run `python make_hash.py` and keep the printed ADMIN_PASSWORD_HASH line.
3. On Render choose New > Blueprint (uses render.yaml), connect this repo, and enter
   DATABASE_URL, ADMIN_USERNAME and ADMIN_PASSWORD_HASH when asked.
4. Open https://<your-service>.onrender.com/health, then log in.
