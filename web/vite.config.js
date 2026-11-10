import { readdirSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies API calls to the backend on :8000.
// `npm run build` writes the site into ../backend/web, which the backend serves at "/".
// On Netlify, OUT_DIR=dist (see ../netlify.toml) builds it into web/dist instead.
//
// Pages: "/" and the guides are plain HTML pages that Google can read; the app lives at /app/.
const api = ["/auth", "/me", "/gmail", "/profile", "/professors", "/documents", "/templates", "/send",
  "/emails", "/replies", "/reminders", "/notifications", "/devices", "/config", "/health"];

// The site's public address, used in canonical links, the sitemap and share previews.
// Netlify provides URL, Vercel provides VERCEL_PROJECT_PRODUCTION_URL. SITE_URL overrides both
// (set it once you have your own domain if the host doesn't use it as the primary address).
const SITE_URL = (process.env.SITE_URL || process.env.URL ||
  (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : "") ||
  "http://localhost:5173").replace(/\/+$/, "");

const skip = new Set(["node_modules", "dist", "src", "public", "app"]);
const guides = readdirSync(__dirname, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !skip.has(d.name) && existsSync(resolve(__dirname, d.name, "index.html")))
  .map((d) => d.name);

function seo() {
  return {
    name: "reachwise-seo",
    transformIndexHtml: (html) => html.replaceAll("__SITE_URL__", SITE_URL),
    generateBundle() {
      const pages = ["/", ...guides.map((g) => `/${g}/`)];
      const today = new Date().toISOString().slice(0, 10);
      this.emitFile({
        type: "asset", fileName: "sitemap.xml",
        source: `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${
          pages.map((p) => `  <url><loc>${SITE_URL}${p}</loc><lastmod>${today}</lastmod></url>`).join("\n")}\n</urlset>\n`,
      });
      this.emitFile({
        type: "asset", fileName: "robots.txt",
        source: ["User-agent: *", "Allow: /", "Disallow: /app/", "",
          "# AI search and assistants: allowed on purpose, so they can read and recommend the guides",
          ...["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "PerplexityBot", "Google-Extended"]
            .flatMap((b) => [`User-agent: ${b}`, "Allow: /", "Disallow: /app/"]),
          "", `Sitemap: ${SITE_URL}/sitemap.xml`, ""].join("\n"),
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), seo()],
  build: {
    outDir: process.env.OUT_DIR || "../backend/web",
    emptyOutDir: true,
    rollupOptions: {
      input: Object.fromEntries([
        ["home", resolve(__dirname, "index.html")],
        ["app", resolve(__dirname, "app/index.html")],
        ...guides.map((g) => [g, resolve(__dirname, g, "index.html")]),
      ]),
    },
  },
  server: { proxy: Object.fromEntries(api.map((p) => [p, "http://127.0.0.1:8000"])) },
});
