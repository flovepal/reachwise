"""Background work: worker threads for slow tasks and the repeating scheduler."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .db import get_db, utcnow
from .notify import notify
from .services import reminders, sending

log = logging.getLogger("profmail.jobs")
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="profmail")
scheduler = BackgroundScheduler(timezone="UTC")


def submit(fn, *args, **kwargs):
    """Run in a worker thread; errors are logged, not lost."""
    def wrapped():
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception("Background task %s failed", getattr(fn, "__name__", fn))
    return executor.submit(wrapped)


def nudge_students() -> int:
    """'It's been 5 days': remind students to analyse replies and send reminders."""
    db = get_db()
    now = utcnow()
    sent = 0
    for user in db.users.find({"gmail.app_password_enc": {"$exists": True}, "deleted": {"$ne": True}}):
        st = reminders.state(user)
        if not st["eligible"] or not st["analysis_needed"]:
            continue
        last = user.get("last_nudged_at")
        if last and now - last < timedelta(days=3):
            continue
        n = len(st["eligible"])
        notify(user, f"It's been {settings.reminder_after_days} days",
               f"{n} professor{'s have' if n != 1 else ' has'} not replied yet. Open the app, tap "
               "Analyse replies, and send reminders to those who haven't answered.", "nudge", email=True)
        db.users.update_one({"_id": user["_id"]}, {"$set": {"last_nudged_at": now}})
        sent += 1
    return sent


def start() -> None:
    if scheduler.running:
        return
    sending.recover_interrupted()
    scheduler.add_job(sending.dispatch_due, "interval", seconds=10, id="dispatch", max_instances=1, coalesce=True)
    scheduler.add_job(sending.recover_interrupted, "interval", minutes=10, id="recover", max_instances=1)
    scheduler.add_job(nudge_students, "interval", minutes=settings.nudge_check_minutes, id="nudge",
                      max_instances=1, coalesce=True, next_run_time=utcnow() + timedelta(minutes=1))
    scheduler.start()
    log.info("Background jobs started")


def stop() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
