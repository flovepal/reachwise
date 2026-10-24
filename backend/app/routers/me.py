"""The signed-in student: profile, goal/details, Gmail connection, setup progress."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import GOALS, get_db, iso, utcnow
from ..mail import smtp
from ..security import current_user, encrypt
from ..services import templates

router = APIRouter(tags=["me"])


def user_out(user: dict) -> dict:
    db = get_db()
    g = user.get("gmail") or {}
    uid = user["_id"]
    return {
        "id": str(uid), "email": user.get("email"), "name": user.get("name"), "picture": user.get("picture", ""),
        "gmail": {"connected": bool(g.get("app_password_enc")), "address": g.get("address", ""),
                  "display_name": g.get("display_name", ""), "verified_at": iso(g.get("verified_at"))},
        "goal": user.get("goal"), "details": user.get("details") or {},
        "setup": {
            "gmail": bool(g.get("app_password_enc")),
            "professors": db.professors.count_documents({"user_id": uid}),
            "cv": db.documents.count_documents({"user_id": uid, "kind": "cv"}) > 0,
            "goal": bool(user.get("goal")),
            "templates": bool(templates.get(user)),
            "sent": db.emails.count_documents({"user_id": uid, "status": "sent"}),
        },
        "last_analysed_at": iso(user.get("last_analysed_at")),
    }


@router.get("/me")
def me(user=Depends(current_user)):
    return user_out(user)


class GmailIn(BaseModel):
    app_password: str = Field(min_length=8)
    address: str = ""          # defaults to the Google sign-in email
    display_name: str = ""
    smtp_host: str = "smtp.gmail.com"
    imap_host: str = "imap.gmail.com"


@router.post("/gmail")
def connect_gmail(body: GmailIn, user=Depends(current_user)):
    address = (body.address or user["email"]).strip().lower()
    password = body.app_password.replace(" ", "").strip()
    account = smtp.Account(address=address, password=password, display_name=body.display_name or user.get("name", ""),
                           smtp_host=body.smtp_host, imap_host=body.imap_host)
    try:
        smtp.test_login(account)
    except smtp.MailLoginError as e:
        raise HTTPException(400, str(e))
    get_db().users.update_one({"_id": user["_id"]}, {"$set": {"gmail": {
        "address": address, "app_password_enc": encrypt(password), "display_name": account.display_name,
        "smtp_host": body.smtp_host, "imap_host": body.imap_host, "verified_at": utcnow()},
        "sending_paused": False}})
    return user_out(get_db().users.find_one({"_id": user["_id"]}))


@router.delete("/gmail")
def disconnect_gmail(user=Depends(current_user)):
    get_db().users.update_one({"_id": user["_id"]}, {"$unset": {"gmail": ""}, "$set": {"sending_paused": True}})
    return user_out(get_db().users.find_one({"_id": user["_id"]}))


class Details(BaseModel):
    full_name: str = ""
    degree: str = ""              # for admission: Master's / PhD
    start_date: str = ""
    end_date: str = ""
    scholarship: str = ""
    current_location: str = ""
    phone: str = ""
    linkedin: str = ""
    plans: str = ""               # what they are planning, in their words
    instructions: str = ""        # extra writing instructions
    signature: str = ""


class ProfileIn(BaseModel):
    goal: str
    details: Details = Details()


@router.put("/profile")
def set_profile(body: ProfileIn, user=Depends(current_user)):
    if body.goal not in GOALS:
        raise HTTPException(400, f"Goal must be one of: {', '.join(GOALS)}")
    get_db().users.update_one({"_id": user["_id"]},
                              {"$set": {"goal": body.goal, "details": body.details.model_dump()}})
    return user_out(get_db().users.find_one({"_id": user["_id"]}))
