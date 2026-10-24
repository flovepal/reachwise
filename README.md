# Reachwise

A website for students emailing professors about TEEP / IIPP internships or graduate
admission. Free to run: no paid AI is needed, because students use any free AI to
personalise their emails.

**How a student uses it**

1. Sign in with Google.
2. Create a Gmail app password (the site walks them through it) and connect Gmail.
3. Import the professor list you give their department, or add professors one by one.
   The import is checked first: missing columns, invalid emails and duplicates are
   shown row by row.
4. Upload a CV (plus optional recommendation letter, internship report, offer letter),
   choose TEEP / IIPP / Admission, and add optional details.
5. **Three emails, written once with any free AI.** The site shows a ready-made prompt
   built from your base templates and the student's details. The student copies it into
   ChatGPT / Gemini / Claude / any AI along with their CV, recommendation letter, internship
   report and offer letter, then pastes the AI's answer back. The site splits it into email
   1, 2 and 3, fixes common AI slip-ups, and flags anything left in [brackets]. The student
   reviews and saves. Each professor's name and research area are filled in automatically.
6. Press **Send first emails**. They go out from the student's own Gmail about 1–2
   minutes apart (the site explains this keeps them out of spam).
7. After **5 days** the site (plus an email to the student) says it's time to tap
   **Analyse replies**. Replies are sorted into Positive / Negative / Other / Didn't
   arrive / No reply, with an "Open in Gmail to reply" button.
8. **Reminders** only go to professors who haven't replied. Anyone who answered, in the
   same thread or a separate email, is skipped automatically, and the student can
   remove anyone else by hand. They press **Send reminders**. 5 days later, the same for
   reminder 2.

```
profmail/
  backend/   FastAPI server: API + background sending; also serves the website
  web/       Website source (React). `npm run build` writes it into backend/web
  testdata/  Sample CV, professor list and old send log, used by the tests
  legacy/    The earlier single-user version, kept for reference
```

## Run it on the lab machine

Full setup (MongoDB Atlas, Google sign-in, Claude key, tunnel) is in
[backend/README.md](backend/README.md). Short version:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && python -m app.keys      # paste the two lines into .env, fill in the rest
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000. The built website is already included in `backend/web`,
so Node isn't needed on the lab machine.

## Start automatically after a restart

See `backend/windows/README.md`. One script (run once as administrator) registers the server and the ngrok
tunnel as start-up tasks, so they come back by themselves after a shutdown, power cut or Windows Update.

## Put the website on Netlify (https://profmail.netlify.app)

The website runs on Netlify; the server keeps running on the lab machine, reached
through **ngrok**. The website finds the server through one line in `config.js`.

1. **Fixed ngrok address.** In the ngrok dashboard (dashboard.ngrok.com) open
   **Domains** and copy your free static domain (e.g. `profmail-john.ngrok-free.app`;
   create it there if the list is empty). It never changes.
2. **Start the server** (window 1): `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`
3. **Start ngrok** (window 2): `ngrok http --url=profmail-john.ngrok-free.app 8000`
   (older ngrok versions: `--domain=` instead of `--url=`). Check
   `https://profmail-john.ngrok-free.app/health` shows `{"ok":true,...}`.
4. **Server settings** (`backend/.env`), then restart uvicorn:
   `PUBLIC_URL=https://profmail-john.ngrok-free.app` and
   `ALLOWED_RETURN_ORIGINS=https://profmail.netlify.app`.
5. **Google Cloud Console → Credentials → your Web client:**
   *Authorized JavaScript origins*: `https://profmail.netlify.app`;
   *Authorized redirect URIs*: `https://profmail.netlify.app/` (with the final slash).
   Google sends students straight back to the website, so the ngrok address isn't needed here.
6. **Website:** in the `profmail-site` folder, set
   `window.PROFMAIL_API_URL = "https://profmail-john.ngrok-free.app";` in `config.js`.
7. **Deploy:** Netlify → your *profmail* site → **Deploys** → drag the `profmail-site`
   folder onto the drop area.

Because the ngrok domain is fixed, steps 4–7 are done once. Afterwards, just keep
windows 1 and 2 running. The website sends a header that skips ngrok's free-plan
browser warning page, so students never see it.

A Cloudflare Tunnel works the same way: use its `https://` address wherever the ngrok
address appears above.

To rebuild the Netlify folder from source: `cd web && OUT_DIR=dist npm run build`
(the result is `web/dist`). If you connect the Netlify site to a Git repository
instead, `netlify.toml` tells Netlify how to build it; put the server address in
`web/public/config.js` before pushing.

## Design system

Colours, fonts and sizes live in `web/src/design/tokens.json` (and `tokens.css`). See `web/DESIGN.md`. The
same tokens are meant for the mobile web view and a future app.

## Changing the website

```bash
cd web
npm install
npm run dev      # http://localhost:5173, talks to the backend on :8000
npm run build    # updates backend/web
```

## Tests

```bash
cd backend && pytest -q
```
They use an in-memory database and a fake Gmail; nothing is sent.
