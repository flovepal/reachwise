import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies API calls to the backend on :8000.
// `npm run build` writes the site into ../backend/web, which the backend serves at "/".
// On Netlify, OUT_DIR=dist (see ../netlify.toml) builds it into web/dist instead.
const api = ["/auth", "/me", "/gmail", "/profile", "/professors", "/documents", "/templates", "/send",
  "/emails", "/replies", "/reminders", "/notifications", "/devices", "/config", "/health"];

export default defineConfig({
  plugins: [react()],
  build: { outDir: process.env.OUT_DIR || "../backend/web", emptyOutDir: true },
  server: { proxy: Object.fromEntries(api.map((p) => [p, "http://127.0.0.1:8000"])) },
});
