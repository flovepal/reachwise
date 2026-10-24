# Working on Reachwise

```
Desktop\reachwise\
  development\   branch "dev"   <- you edit here. Live for students right now.
  production\    branch "main"  <- switched on later, with your domain + Cloudflare.
```

GitHub keeps both branches. The Netlify site follows `dev` and rebuilds by itself on every push. Later,
the Vercel site will follow `main`. Both use the same MongoDB database.

## Making a change

1. Open `Desktop\reachwise\development` in VS Code and make the change.
2. **Website change** (anything in `web\`): commit and push (VS Code Source Control → Commit → Sync).
   Netlify rebuilds in about a minute.
3. **Server change** (anything in `backend\`): commit and push the same way, then restart the server:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\backend\windows\restart_server.ps1
   ```
4. New Python packages in `requirements.txt`? Run `backend\windows\update.ps1` instead. It installs them and restarts.

When Claude sends you changes, they go into this folder. You review them in VS Code, then push.

## Releasing to production (once production is switched on)

```powershell
cd Desktop\reachwise\development
powershell -ExecutionPolicy Bypass -File .\release_to_production.ps1
```
It shows what will go out, copies `dev` to `main` on GitHub (Vercel rebuilds the production site), and offers
to update and restart the production server.

## Trying a risky database change

The development and production sites share one database. Before changing how data is stored, make a copy
and test against the copy:
```powershell
cd Desktop\reachwise\development\backend
.venv\Scripts\python -m tools.copy_database reachwise_test
```
Then set `MONGODB_DB=reachwise_test` in `backend\.env` and restart the server. Set it back when you're done.

## One-time: connect Netlify to GitHub

1. app.netlify.com → your site → **Site configuration → Build & deploy → Continuous deployment → Link repository**.
2. Choose GitHub → `reachwise`. Branch to deploy: **dev**. Netlify reads the build settings from `netlify.toml`.
3. Deploy. From now on every push to `dev` updates the site, so there's nothing to drag and drop.

## Later: production on Vercel (when the domain is ready)

1. vercel.com → Add New → Project → import `reachwise`.
2. **Root Directory:** `web`. **Production Branch:** `main` (Settings → Git).
3. Environment variable `VITE_API_URL` = your production API address (for example `https://api.yourdomain.com`).
4. Add the Vercel/domain address to Google OAuth (origin + redirect URI with `/`) and to `ALLOWED_RETURN_ORIGINS`
   in `production\backend\.env`.
5. Production runs on port 8001 (`backend\windows\settings.local.bat`), so it never clashes with development.

## Never uploaded to GitHub

`backend\.env` (passwords and keys), `ngrok.yml`, `settings.local.bat`, `.venv`, logs. The `.gitignore`
file controls this. The repo is private.
