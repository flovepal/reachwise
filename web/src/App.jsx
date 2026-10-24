import React, { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken, when } from "./api.js";
import { AppCtx, Brand, Spinner, useToast } from "./ui.jsx";
import SignIn from "./pages/SignIn.jsx";
import Gmail from "./pages/Gmail.jsx";
import Professors from "./pages/Professors.jsx";
import Profile from "./pages/Profile.jsx";
import Emails from "./pages/Emails.jsx";
import Send from "./pages/Send.jsx";
import Replies from "./pages/Replies.jsx";
import Reminders from "./pages/Reminders.jsx";

const SETUP = [
  { key: "gmail", label: "Connect Gmail", done: (s) => s.gmail },
  { key: "professors", label: "Professors", done: (s) => s.professors > 0 },
  { key: "profile", label: "Documents and goal", done: (s) => s.cv && s.goal },
  { key: "emails", label: "Your three emails", done: (s) => s.templates },
  { key: "send", label: "Send first emails", done: (s) => s.sent > 0 },
];
const AFTER = [
  { key: "replies", label: "Replies" },
  { key: "reminders", label: "Reminders" },
];
const PAGES = { gmail: Gmail, professors: Professors, profile: Profile, emails: Emails, send: Send, replies: Replies, reminders: Reminders };

function readHash() {
  const k = window.location.hash.replace(/^#\/?/, "");
  return PAGES[k] ? k : null;
}

export default function App() {
  const [toast, toastEl] = useToast();
  const [signedIn, setSignedIn] = useState(() => {
    // Coming back from Google sign-in: /?token=...
    const params = new URLSearchParams(window.location.search);
    if (params.get("token")) {
      setToken(params.get("token"));
      window.history.replaceState(null, "", window.location.pathname + window.location.hash);
    }
    return !!getToken();
  });
  const [signInError, setSignInError] = useState(() => new URLSearchParams(window.location.search).get("error"));
  // Coming back from Google: /?code=...&state=...  -> swap the code for a session
  const [exchanging, setExchanging] = useState(() => new URLSearchParams(window.location.search).has("code"));
  useEffect(() => {
    if (!exchanging) return;
    const params = new URLSearchParams(window.location.search);
    window.history.replaceState(null, "", window.location.pathname + window.location.hash);
    api("/auth/google/exchange", { method: "POST", body: { code: params.get("code"), state: params.get("state") || "" } })
      .then((r) => { setToken(r.token); setSignedIn(true); })
      .catch((e) => { setSignInError("exchange"); toast(e.message, true); })
      .finally(() => setExchanging(false));
  }, [exchanging, toast]);
  const [config, setConfig] = useState(null);
  const [me, setMe] = useState(null);
  const [page, setPageState] = useState(readHash);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => { api("/config").then(setConfig).catch(() => setConfig({ offline: true })); }, []);

  const refreshMe = useCallback(async () => {
    try { const m = await api("/me"); setMe(m); return m; } catch { return null; }
  }, []);

  useEffect(() => { if (signedIn) refreshMe(); }, [signedIn, refreshMe]);

  // Pick the starting page once (next unfinished step, or Replies after sending), then stay on it
  useEffect(() => {
    if (!me || page) return;
    const firstOpen = SETUP.find((x) => !x.done(me.setup));
    const start = me.setup.sent > 0 ? "replies" : firstOpen ? firstOpen.key : "send";
    window.history.replaceState(null, "", `#/${start}`);
    setPageState(start);
  }, [me, page]);

  useEffect(() => {
    const out = () => { setSignedIn(false); setMe(null); };
    const hash = () => setPageState(readHash());
    window.addEventListener("profmail:signed-out", out);
    window.addEventListener("hashchange", hash);
    return () => { window.removeEventListener("profmail:signed-out", out); window.removeEventListener("hashchange", hash); };
  }, []);

  const go = useCallback((key) => {
    window.location.hash = `/${key}`;
    setPageState(key);
    setMenuOpen(false);
    window.scrollTo(0, 0);
  }, []);

  if (exchanging) {
    return <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}><Spinner /></div>;
  }
  if (!signedIn) {
    return (
      <AppCtx.Provider value={{ toast, config }}>
        <SignIn config={config} error={signInError} onSignedIn={() => setSignedIn(true)} />
        {toastEl}
      </AppCtx.Provider>
    );
  }
  if (!me) {
    return <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}><Spinner /></div>;
  }

  const s = me.setup;
  const current = page || "gmail";
  const Page = PAGES[current];
  const signOut = () => { setToken(null); setSignedIn(false); setMe(null); window.location.hash = ""; };

  return (
    <AppCtx.Provider value={{ toast, config, me, refreshMe, go }}>
      <div className="shell">
        <nav className={`side ${menuOpen ? "open" : ""}`} aria-label="Main">
          <Brand />
          <div className="nav-group">Set up once</div>
          {SETUP.map((x, i) => (
            <button key={x.key} className={`nav-item ${current === x.key ? "active" : ""} ${x.done(s) ? "done" : ""}`}
              onClick={() => go(x.key)} aria-current={current === x.key ? "page" : undefined}>
              <span className="step-dot">{x.done(s) ? "✓" : i + 1}</span>{x.label}
            </button>
          ))}
          <div className="nav-group">After sending</div>
          {AFTER.map((x) => (
            <button key={x.key} className={`nav-item ${current === x.key ? "active" : ""}`} onClick={() => go(x.key)}
              aria-current={current === x.key ? "page" : undefined}>
              <span className="step-dot" aria-hidden="true">{x.key === "replies" ? "↩" : "↻"}</span>{x.label}
            </button>
          ))}
          <div className="side-foot">
            <div className="who">{me.name}</div>
            <div className="muted small" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{me.email}</div>
            <button className="btn ghost small" style={{ marginTop: 8, paddingLeft: 0 }} onClick={signOut}>Sign out</button>
          </div>
        </nav>
        <div className="main">
          <header className="topbar">
            <Brand className="brand mobile-brand" />
            <Notifications />
          </header>
          <main className="content" onClick={() => menuOpen && setMenuOpen(false)}>
            <Page key={current} />
          </main>
        </div>
        {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />}
        <BottomNav current={current} go={go} openMenu={() => setMenuOpen(true)} />
      </div>
      {toastEl}
    </AppCtx.Provider>
  );
}

const ICONS = {
  professors: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M21 19v-1a4 4 0 0 0-3-3.9M15.5 3.1a3.5 3.5 0 0 1 0 6.8",
  emails: "M4 5h16v14H4zM4 6l8 7 8-7",
  send: "M21 3 10 14M21 3l-7 18-4-7-7-4z",
  replies: "M9 14 4 9l5-5M4 9h10a6 6 0 0 1 6 6v4",
  more: "M4 6h16M4 12h16M4 18h16",
};
const BOTTOM = [["professors", "Professors"], ["emails", "Emails"], ["send", "Send"], ["replies", "Replies"]];

function BottomNav({ current, go, openMenu }) {
  const icon = (k) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[k]} /></svg>
  );
  return (
    <nav className="bottom-nav" aria-label="Quick">
      {BOTTOM.map(([k, label]) => (
        <button key={k} className={current === k ? "on" : ""} onClick={() => go(k)} aria-current={current === k ? "page" : undefined}>{icon(k)}{label}</button>
      ))}
      <button onClick={openMenu}>{icon("more")}More</button>
    </nav>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const load = useCallback(() => api("/notifications").then(setItems).catch(() => {}), []);
  useEffect(() => { load(); const id = setInterval(load, 60000); return () => clearInterval(id); }, [load]);
  const unread = items.filter((n) => !n.read).length;
  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && unread) { await api("/notifications/read", { method: "POST" }).catch(() => {}); setTimeout(load, 4000); }
  };
  return (
    <div className="bell">
      <button className="btn ghost" onClick={toggle} aria-expanded={open} aria-label={`Notifications, ${unread} unread`}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0" /></svg>
        {unread > 0 && <span className="count">{unread}</span>}
      </button>
      {open && (
        <div className="dropdown">
          {items.length === 0 && <div className="item muted">Nothing yet. You'll see updates about sending and reminders here.</div>}
          {items.map((n) => (
            <div key={n.id} className={`item ${n.read ? "" : "unread"}`}>
              <div style={{ fontWeight: 600 }}>{n.title}</div>
              <div>{n.body}</div>
              <div className="muted small">{when(n.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
