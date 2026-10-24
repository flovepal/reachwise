"""Sign in with Google.

Two ways, both ending with our own session token:
  * POST /auth/google with a Google ID token (Android / any app that has one)
  * GET  /auth/google/start -> Google -> /auth/google/callback -> back to the app
    with ?token=... (website and desktop apps)
"""
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..config import settings
from ..db import fs, get_db, utcnow
from ..security import current_user, make_token, read_token
from .me import user_out

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"


def verify_google_id_token(token: str) -> dict:
    """Check a Google ID token and return its claims. Replaced in tests."""
    from google.auth.transport import requests as grequests
    from google.oauth2 import id_token
    try:
        claims = id_token.verify_oauth2_token(token, grequests.Request())
    except ValueError as e:
        raise HTTPException(401, f"Google sign-in failed: {e}")
    if claims.get("aud") not in settings.client_ids:
        raise HTTPException(401, "This Google sign-in was not made for this app")
    if not claims.get("email_verified"):
        raise HTTPException(401, "Your Google email is not verified")
    return claims


def upsert_user(sub: str, email: str, name: str, picture: str = "") -> dict:
    db = get_db()
    now = utcnow()
    db.users.update_one(
        {"google_sub": sub},
        {"$set": {"email": email.lower(), "name": name, "picture": picture, "last_login_at": now},
         "$setOnInsert": {"created_at": now, "goal": None, "details": {}}},
        upsert=True)
    return db.users.find_one({"google_sub": sub})


def session_response(user: dict) -> dict:
    return {"token": make_token(str(user["_id"])), "user": user_out(user)}


class GoogleIn(BaseModel):
    id_token: str


@router.post("/google")
def google_sign_in(body: GoogleIn):
    c = verify_google_id_token(body.id_token)
    user = upsert_user(c["sub"], c["email"], c.get("name") or c["email"].split("@")[0], c.get("picture", ""))
    return session_response(user)


def _allowed_return(url: str) -> bool:
    p = urlparse(url)
    if p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1"):
        return True  # desktop app's temporary local listener
    origin = f"{p.scheme}://{p.netloc}"
    # The website is served by this same server, so its own address is always allowed
    return origin == settings.public_url.rstrip("/") or (p.scheme == "https" and origin in settings.return_origins)


@router.get("/google/start")
def google_start(return_to: str):
    if not _allowed_return(return_to):
        raise HTTPException(400, "This return address is not allowed")
    if not settings.google_web_client_id:
        raise HTTPException(503, "Google sign-in is not configured on the server yet")
    state = make_token("oauth", purpose="oauth_state", minutes=10, return_to=return_to)
    params = {"client_id": settings.google_web_client_id, "response_type": "code",
              "scope": "openid email profile", "redirect_uri": f"{settings.public_url}/auth/google/callback",
              "state": state, "prompt": "select_account"}
    return RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}")


@router.get("/google/callback")
def google_callback(code: str = "", state: str = "", error: str = ""):
    data = read_token(state, purpose="oauth_state")
    return_to = data["return_to"]
    sep = "&" if "?" in return_to else "?"
    if error or not code:
        return RedirectResponse(f"{return_to}{sep}{urlencode({'error': error or 'cancelled'})}")
    r = httpx.post(GOOGLE_TOKEN, data={
        "code": code, "client_id": settings.google_web_client_id,
        "client_secret": settings.google_web_client_secret,
        "redirect_uri": f"{settings.public_url}/auth/google/callback", "grant_type": "authorization_code"},
        timeout=20)
    if r.status_code != 200:
        return RedirectResponse(f"{return_to}{sep}{urlencode({'error': 'google_token_exchange_failed'})}")
    c = verify_google_id_token(r.json()["id_token"])
    user = upsert_user(c["sub"], c["email"], c.get("name") or c["email"], c.get("picture", ""))
    return RedirectResponse(f"{return_to}{sep}{urlencode({'token': make_token(str(user['_id']))})}")


# ---- Sign-in where Google returns straight to the website ---------------------
# The browser never visits this server's address directly, which matters with
# ngrok's free plan (it shows a warning page to browsers) and keeps things simple.

@router.get("/google/url")
def google_url(redirect_uri: str):
    """Google sign-in address. Google sends the student back to `redirect_uri` (the website)
    with ?code=...&state=..., and the website passes those to POST /auth/google/exchange."""
    if not _allowed_return(redirect_uri):
        raise HTTPException(400, "This website address is not allowed to sign in. Add it to ALLOWED_RETURN_ORIGINS.")
    if not settings.google_web_client_id:
        raise HTTPException(503, "Google sign-in is not configured on the server yet")
    state = make_token("oauth", purpose="oauth_state", minutes=10, redirect_uri=redirect_uri)
    params = {"client_id": settings.google_web_client_id, "response_type": "code",
              "scope": "openid email profile", "redirect_uri": redirect_uri,
              "state": state, "prompt": "select_account"}
    return {"url": f"{GOOGLE_AUTH}?{urlencode(params)}"}


class ExchangeIn(BaseModel):
    code: str
    state: str


@router.post("/google/exchange")
def google_exchange(body: ExchangeIn):
    data = read_token(body.state, purpose="oauth_state")
    redirect_uri = data.get("redirect_uri")
    if not redirect_uri:
        raise HTTPException(400, "Sign-in link is invalid. Please try again.")
    r = httpx.post(GOOGLE_TOKEN, data={
        "code": body.code, "client_id": settings.google_web_client_id,
        "client_secret": settings.google_web_client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=20)
    if r.status_code != 200:
        detail = ""
        try:
            detail = r.json().get("error_description") or r.json().get("error") or ""
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(401, f"Google sign-in didn't complete{': ' + detail if detail else ''}. Please try again.")
    c = verify_google_id_token(r.json()["id_token"])
    user = upsert_user(c["sub"], c["email"], c.get("name") or c["email"].split("@")[0], c.get("picture", ""))
    return session_response(user)


class DevIn(BaseModel):
    email: str
    name: str = ""


@router.post("/dev")
def dev_sign_in(body: DevIn):
    """Testing only (DEV_LOGIN=true)."""
    if not settings.dev_login:
        raise HTTPException(404, "Not found")
    user = upsert_user(f"dev:{body.email.lower()}", body.email, body.name or body.email.split("@")[0])
    return session_response(user)


@router.delete("/account")
def delete_account(user=Depends(current_user)):
    """Delete the student and everything stored for them (required by app stores)."""
    db = get_db()
    uid = user["_id"]
    for d in db.documents.find({"user_id": uid}):
        try:
            fs().delete(d["gridfs_id"])
        except Exception:  # noqa: BLE001
            pass
    for coll in ("documents", "professors", "emails", "replies", "notifications"):
        db[coll].delete_many({"user_id": uid})
    db.users.delete_one({"_id": uid})
    return {"deleted": True}
