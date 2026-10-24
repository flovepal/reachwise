# Reachwise backend

The server behind the Reachwise website, which it also serves. Students sign in with
Google, connect Gmail with an app password, add professors, upload their CV and
documents. The site gives them one prompt to paste, with their documents, into any free
AI (ChatGPT, Gemini, Claude, Copilot…). They paste the answer back and the site splits it
into email 1, 2 and 3. The server then sends them slowly from the student's own Gmail,
reads replies, sorts them, and offers reminders after 5 days.

Runs on your lab machine (Python 3.10+), stores data in MongoDB Atlas, and is
reached from the internet through a tunnel.

```
 student's browser ──HTTPS──► tunnel ──► lab machine: uvicorn (website + API)
                                                         │      │        │
                                              MongoDB Atlas   Claude   student's Gmail
                                              (data + files)   API     (SMTP send, IMAP read)
```

---

## 1. Set up on the lab machine

```bash
cd profmail/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.keys          # paste the two printed lines into .env
```

Then fill in the rest of `.env` with the steps below.

## 2. MongoDB Atlas (free)

1. Create a free account at mongodb.com/atlas and create a free **M0** cluster.
2. **Database Access** → add a database user (username + strong password).
3. **Network Access** → add the lab machine's public IP. If the lab's IP changes,
   use `0.0.0.0/0`. That is safer than it sounds because the user/password is still
   required, but a fixed IP is better.
4. **Connect → Drivers** → copy the connection string into `MONGODB_URI`, with
   your password in place of `<password>`.

Uploaded CVs and letters are stored in the same database (GridFS). The free tier's
512 MB holds roughly 1,000+ students' documents.

## 3. Google sign-in

In console.cloud.google.com (one project for the app):

1. **OAuth consent screen**: External, app name Reachwise, your email. Scopes:
   only `openid`, `email` and `profile`. These are basic scopes, so **no Google
   security review is needed**. Publish the app (Testing mode only allows 100 test users).
2. **Credentials → Create OAuth client ID**:
   * **Web application**. Authorized JavaScript origin: your `PUBLIC_URL`.
     Authorized redirect URI: `<PUBLIC_URL>/auth/google/callback`.
     Put its ID and secret in `GOOGLE_WEB_CLIENT_ID` / `GOOGLE_WEB_CLIENT_SECRET`.

Gmail itself is reached with the student's **app password** (IMAP/SMTP), not
Google OAuth. That avoids Google's paid security assessment for Gmail permissions.

## 4. Claude API key (optional)

Not needed. Students write their emails with any AI they like, for free. Without a
key, replies are sorted with keyword rules. If you later want smarter sorting, put a
key from console.anthropic.com in `ANTHROPIC_API_KEY`. It is used once per reply with
the small Haiku model, so it costs very little.

The base templates students start from (one set per goal) and the prompt they copy
are in `app/prompts.py`. Edit them there to change the wording for everyone.

## 5. Run it

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000 for the website and http://127.0.0.1:8000/docs for the API. Keep `--workers 1`: the
send queue and reminders run inside the server process.

To keep it running after reboots, edit `profmail.service` (user + folder) and
follow the commands at the top of that file.

## 6. Put it on the internet (HTTPS)

Google sign-in requires HTTPS, and university networks usually block
incoming connections. A tunnel solves both. The lab machine connects *out*, so
no port has to be opened.

**Option A: Cloudflare Tunnel (recommended, needs a domain on Cloudflare, ~US$10/year)**
```bash
# install cloudflared (see developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads)
cloudflared tunnel login
cloudflared tunnel create profmail
cloudflared tunnel route dns profmail api.yourdomain.com
cloudflared tunnel run --url http://127.0.0.1:8000 profmail
# then: sudo cloudflared service install   (keeps it running)
```
Set `PUBLIC_URL=https://api.yourdomain.com`.

**Option B: no domain yet.** `cloudflared tunnel --url http://127.0.0.1:8000`
gives a free `*.trycloudflare.com` address instantly, but it **changes every
restart**. Fine for testing, not for a released app. ngrok's free plan includes one
fixed domain if you want a stable free address.

Ask your lab/IT whether running a public service from the lab machine is allowed.

## 7. Tests

```bash
pytest -q
```
The tests use an in-memory database and a fake Gmail, so they send nothing.
`DEV_LOGIN=true` adds `POST /auth/dev` for local testing. Never enable it on the
internet.

---

## API overview (what the website calls)

All calls except sign-in need `Authorization: Bearer <token>`.

| Step | Calls |
|---|---|
| Sign in | `GET /auth/google/start?return_to=<site>` → Google → back to the site with `?token=` |
| Connect Gmail | `POST /gmail {app_password}`. Tests sending and reading before saving. `GET /me` shows setup progress. |
| Professors | `POST /professors/import/preview` (file) checks without saving → `POST /professors/import`. One at a time: `POST/PUT/DELETE /professors[/id]`. `GET /professors/export`. Old send log: `POST /professors/import-history` |
| Documents | `POST /documents` (file, kind = cv \| recommendation \| internship_report \| offer_letter \| loi \| proposal \| other), `PATCH /documents/{id} {attach}` |
| Goal & details | `PUT /profile {goal: teep\|iipp\|admission, details:{...}}` |
| Three emails | `GET /templates/prompt?include_text=` (prompt to copy into any AI) → `POST /templates/parse {text}` (splits the AI's answer, repairs placeholders, warns about leftovers) → `PUT /templates` (blocks unfilled [brackets]). `GET /templates/basic` for hand-writing. Placeholders: `{professor}`, `{research_in}`, `{research_area}`, `{university}` |
| Send first emails | `POST /send/initial` → `GET /emails/queue`, `POST /emails/pause\|resume\|cancel\|retry` |
| Analyse replies | `POST /replies/analyse` → poll `GET /replies/summary`. `GET /replies`, `GET /replies/{id}`, `GET /replies/no-reply` |
| Unsure replies | `GET /replies?status=possible` → `POST /replies/{id}/confirm {professor_id or null}`. Fix a category: `POST /replies/{id}/label` |
| Reminders | `GET /reminders` (eligible / upcoming / removed) → `POST /professors/{id}/reminders {skip}` to remove or put back → `POST /send/reminders` |
| Other | `GET /notifications`, `DELETE /auth/account` |

## How replies are recognised

Every email sent gets a unique Message-ID. On "Analyse replies" the server
searches the student's Gmail **All Mail and Spam** only for mail involving
professors on their list:

1. **Same thread**: the reply's In-Reply-To/References contain our Message-ID.
2. **New thread, professor's address**: any mail *from* that professor's address
   after the first email counts as a reply, whatever its subject.
3. **Different address** (e.g. their personal Gmail) with subject "Re: <our subject>":
   listed as *possible*; the student confirms who it was from.
4. **Bounces**: delivery-failure notices are matched to the address in them.
5. **Out-of-office** replies don't count. Those professors still get reminders.
6. **The student already wrote back from Gmail**: no reminder is suggested.

Right before each reminder goes out, the server checks that professor's mail
once more. If the inbox can't be read at that moment, the reminder waits instead of
going out.

## Before inviting students

* Write a short privacy note: app passwords are stored encrypted, and only mail
  involving the student's listed professors is read. `DELETE /auth/account` removes
  everything for a student.
* Try the whole flow yourself first with a small list (e.g. 3 friends' addresses).
