"""Policy Tracker: server-rendered pages with one admin login."""
import hmac
import os
import secrets
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, selectinload
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .logic import (
    RENEWAL_DAYS, STATUSES, hash_password, policies_to_csv,
    validate_client, validate_policy, verify_password,
)
from .models import Client, Policy, SessionLocal, init_db

BASE = Path(__file__).parent
ENV = os.getenv("ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
if ENV == "production" and not (SECRET_KEY and ADMIN_PASSWORD_HASH):
    raise RuntimeError("Set SECRET_KEY and ADMIN_PASSWORD_HASH before running in production.")
SECRET_KEY = SECRET_KEY or "dev-only-secret"
ADMIN_PASSWORD_HASH = ADMIN_PASSWORD_HASH or hash_password("admin")  # local development only

app = FastAPI(title="Policy Tracker")
app.add_middleware(
    SessionMiddleware, secret_key=SECRET_KEY, same_site="lax",
    https_only=(ENV == "production"), max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
init_db()


class LoginRequired(Exception):
    pass


def get_db():
    with SessionLocal() as db:
        yield db


def require_login(request: Request):
    if not request.session.get("user"):
        raise LoginRequired()


def csrf_token(request: Request):
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(16)
    return token


async def csrf_form(request: Request) -> dict:
    """Read a submitted form and reject it if its token does not match the session."""
    form = dict(await request.form())
    expected = request.session.get("csrf", "")
    if not expected or not hmac.compare_digest(str(form.get("csrf", "")), expected):
        raise HTTPException(403, "This form expired. Reload the page and try again.")
    return form


def render(request: Request, name: str, status_code: int = 200, **context):
    context.update(
        csrf=csrf_token(request), user=request.session.get("user"),
        flash=request.session.pop("flash", None),
    )
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def flash(request: Request, message: str):
    request.session["flash"] = message


def redirect(url: str):
    return RedirectResponse(url, status_code=303)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc: LoginRequired):
    return redirect("/login")


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    message = "Page not found." if exc.status_code == 404 else str(exc.detail)
    return render(request, "error.html", status_code=exc.status_code, message=message)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "database unavailable"}, status_code=503)
    return {"status": "ok"}


@app.get("/login")
def login_form(request: Request):
    if request.session.get("user"):
        return redirect("/clients")
    return render(request, "login.html", error=None)


@app.post("/login")
def login(request: Request, form: dict = Depends(csrf_form)):
    username, password = str(form.get("username", "")), str(form.get("password", ""))
    user_ok = hmac.compare_digest(username.encode(), ADMIN_USERNAME.encode())
    if verify_password(password, ADMIN_PASSWORD_HASH) and user_ok:
        request.session.clear()
        request.session["user"] = username
        return redirect("/clients")
    return render(request, "login.html", status_code=401, error="Incorrect username or password.")


@app.post("/logout")
def logout(request: Request, form: dict = Depends(csrf_form)):
    request.session.clear()
    return redirect("/login")


private = APIRouter(dependencies=[Depends(require_login)])


def get_client(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found.")
    return client


def get_policy(db: Session, policy_id: int) -> Policy:
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found.")
    return policy


def policy_values(p: Policy) -> dict:
    return {
        "policy_number": p.policy_number, "type": p.type, "insurer": p.insurer,
        "premium": f"{p.premium:.2f}", "start_date": p.start_date.isoformat(),
        "end_date": p.end_date.isoformat(), "status": p.status, "notes": p.notes,
    }


def duplicate_number(db: Session, number: str, own_id=None) -> bool:
    found = db.scalar(select(Policy.id).where(Policy.policy_number == number))
    return found is not None and found != own_id


def filtered_policies(db: Session, status: str, insurer: str, ptype: str):
    stmt = (select(Policy).join(Client).options(selectinload(Policy.client))
            .order_by(Policy.end_date, Client.name))
    if status in STATUSES:
        stmt = stmt.where(Policy.status == status)
    if insurer.strip():
        stmt = stmt.where(Policy.insurer.ilike(f"%{insurer.strip()}%"))
    if ptype.strip():
        stmt = stmt.where(Policy.type.ilike(f"%{ptype.strip()}%"))
    return db.scalars(stmt).all()


@private.get("/")
def home():
    return redirect("/clients")


@private.get("/clients")
def clients(request: Request, q: str = "", db: Session = Depends(get_db)):
    stmt = select(Client).options(selectinload(Client.policies)).order_by(Client.name)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Client.name.ilike(like), Client.email.ilike(like)))
    return render(request, "clients.html", clients=db.scalars(stmt).all(), q=q)


@private.get("/clients/new")
def client_new(request: Request):
    return render(request, "client_form.html", title="New client", values={}, errors={})


@private.post("/clients/new")
def client_create(request: Request, form: dict = Depends(csrf_form), db: Session = Depends(get_db)):
    clean, errors = validate_client(form)
    if errors:
        return render(request, "client_form.html", status_code=422, title="New client", values=form, errors=errors)
    client = Client(**clean)
    db.add(client)
    db.commit()
    flash(request, "Client saved.")
    return redirect(f"/clients/{client.id}")


@private.get("/clients/{client_id}")
def client_detail(request: Request, client_id: int, db: Session = Depends(get_db)):
    return render(request, "client_detail.html", client=get_client(db, client_id))


@private.get("/clients/{client_id}/edit")
def client_edit(request: Request, client_id: int, db: Session = Depends(get_db)):
    c = get_client(db, client_id)
    values = {"name": c.name, "email": c.email, "phone": c.phone}
    return render(request, "client_form.html", title="Edit client", values=values, errors={})


@private.post("/clients/{client_id}/edit")
def client_update(request: Request, client_id: int, form: dict = Depends(csrf_form), db: Session = Depends(get_db)):
    c = get_client(db, client_id)
    clean, errors = validate_client(form)
    if errors:
        return render(request, "client_form.html", status_code=422, title="Edit client", values=form, errors=errors)
    c.name, c.email, c.phone = clean["name"], clean["email"], clean["phone"]
    db.commit()
    flash(request, "Client saved.")
    return redirect(f"/clients/{c.id}")


@private.post("/clients/{client_id}/delete")
def client_delete(request: Request, client_id: int, form: dict = Depends(csrf_form), db: Session = Depends(get_db)):
    db.delete(get_client(db, client_id))
    db.commit()
    flash(request, "Client and their policies deleted.")
    return redirect("/clients")


@private.get("/clients/{client_id}/policies/new")
def policy_new(request: Request, client_id: int, db: Session = Depends(get_db)):
    return render(request, "policy_form.html", title="Add policy", client=get_client(db, client_id),
                  values={"status": "active"}, errors={}, statuses=STATUSES)


@private.post("/clients/{client_id}/policies/new")
def policy_create(request: Request, client_id: int, form: dict = Depends(csrf_form), db: Session = Depends(get_db)):
    client = get_client(db, client_id)
    clean, errors = validate_policy(form)
    if "policy_number" not in errors and duplicate_number(db, clean["policy_number"]):
        errors["policy_number"] = "A policy with this number already exists."
    if errors:
        return render(request, "policy_form.html", status_code=422, title="Add policy", client=client,
                      values=form, errors=errors, statuses=STATUSES)
    db.add(Policy(client_id=client.id, **clean))
    db.commit()
    flash(request, "Policy saved.")
    return redirect(f"/clients/{client.id}")


@private.get("/policies")
def policies(request: Request, status: str = "", insurer: str = "", ptype: str = Query("", alias="type"),
             db: Session = Depends(get_db)):
    query = urlencode({k: v for k, v in {"status": status, "insurer": insurer, "type": ptype}.items() if v})
    return render(request, "policies.html", policies=filtered_policies(db, status, insurer, ptype),
                  status=status, insurer=insurer, ptype=ptype, statuses=STATUSES, query=query)


@private.get("/policies.csv")
def policies_csv(status: str = "", insurer: str = "", ptype: str = Query("", alias="type"),
                 db: Session = Depends(get_db)):
    rows = [(p.client.name, p.policy_number, p.type, p.insurer, p.premium, p.start_date, p.end_date, p.status)
            for p in filtered_policies(db, status, insurer, ptype)]
    return Response(policies_to_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="policies.csv"'})


@private.get("/policies/{policy_id}/edit")
def policy_edit(request: Request, policy_id: int, db: Session = Depends(get_db)):
    p = get_policy(db, policy_id)
    return render(request, "policy_form.html", title="Edit policy", client=p.client,
                  values=policy_values(p), errors={}, statuses=STATUSES)


@private.post("/policies/{policy_id}/edit")
def policy_update(request: Request, policy_id: int, form: dict = Depends(csrf_form), db: Session = Depends(get_db)):
    p = get_policy(db, policy_id)
    clean, errors = validate_policy(form)
    if "policy_number" not in errors and duplicate_number(db, clean["policy_number"], own_id=p.id):
        errors["policy_number"] = "A policy with this number already exists."
    if errors:
        return render(request, "policy_form.html", status_code=422, title="Edit policy", client=p.client,
                      values=form, errors=errors, statuses=STATUSES)
    for key, value in clean.items():
        setattr(p, key, value)
    db.commit()
    flash(request, "Policy saved.")
    return redirect(f"/clients/{p.client_id}")


@private.post("/policies/{policy_id}/delete")
def policy_delete(request: Request, policy_id: int, form: dict = Depends(csrf_form), db: Session = Depends(get_db)):
    p = get_policy(db, policy_id)
    client_id = p.client_id
    db.delete(p)
    db.commit()
    flash(request, "Policy deleted.")
    return redirect(f"/clients/{client_id}")


@private.get("/renewals")
def renewals(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    stmt = (select(Policy).join(Client).options(selectinload(Policy.client))
            .where(Policy.status == "active", Policy.end_date >= today,
                   Policy.end_date <= today + timedelta(days=RENEWAL_DAYS))
            .order_by(Policy.end_date, Client.name))
    return render(request, "renewals.html", policies=db.scalars(stmt).all(), today=today, days=RENEWAL_DAYS)


app.include_router(private)
