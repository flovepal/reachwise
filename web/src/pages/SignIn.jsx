import React, { useState } from "react";
import { API_URL, api, setToken } from "../api.js";
import { BRAND } from "../brand.js";
import { Brand, Spinner, useApp } from "../ui.jsx";

const ERRORS = {
  cancelled: "Google sign-in was cancelled.",
  access_denied: "Google sign-in was cancelled.",
  google_token_exchange_failed: "Google sign-in didn't complete. Please try again.",
  exchange: "Google sign-in didn't complete. Please try again.",
};

export default function SignIn({ config, error, onSignedIn }) {
  const { toast } = useApp();
  const [email, setEmail] = useState("");
  const [going, setGoing] = useState(false);
  const offline = config && config.offline;

  // Google sends the student back to this page with ?code=..., handled in App.jsx
  const google = async () => {
    setGoing(true);
    try {
      const r = await api(`/auth/google/url?redirect_uri=${encodeURIComponent(`${window.location.origin}/`)}`);
      window.location.href = r.url;
    } catch (err) { toast(err.message, true); setGoing(false); }
  };

  const devLogin = async (e) => {
    e.preventDefault();
    try {
      const r = await api("/auth/dev", { method: "POST", body: { email } });
      setToken(r.token);
      onSignedIn();
    } catch (err) { toast(err.message, true); }
  };

  return (
    <div className="signin">
      <section className="signin-art">
        <Brand />
        <div>
          <h1>Email professors once. Follow up at the right time.</h1>
          <p>For students applying for TEEP, IIPP or graduate admission. Write your emails once, send them from
            your own Gmail, and see who replied before any reminder goes out.</p>
          <div className="flow" aria-label="How it works">
            <div><b>Day 0</b> Your first email goes to every professor on your list</div>
            <div><b>Day 5</b> Check replies, then send reminder 1 to those who haven't answered</div>
            <div><b>Day 10</b> Check again, then send the last reminder</div>
          </div>
        </div>
        <p className="small" style={{ color: "#9aa1c4" }}>Free while we test it with students.</p>
      </section>
      <section className="signin-form">
        <div className="signin-card">
          <h2>Sign in</h2>
          <p className="muted">Use the Google account you'll send emails from.</p>
          {error && <div className="note bad">{ERRORS[error] || `Sign-in failed (${error}).`}</div>}
          {offline && (
            <div className="note bad">
              The {BRAND.name} server isn't reachable right now{API_URL ? ` (${API_URL})` : ""}. If you run this site,
              check that the server and tunnel are running and that config.js has the right address.
            </div>
          )}
          <button type="button" className="google-btn" onClick={google} disabled={going}>
            {going ? <Spinner /> : null}
            <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.6 5.4 2.6 13.3l7.8 6C12.3 13.4 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 7l7.4 5.7c4.3-4 6.9-9.9 6.9-17.2z"/><path fill="#FBBC05" d="M10.4 28.7c-.5-1.4-.8-3-.8-4.7s.3-3.2.8-4.7l-7.8-6C.9 16.6 0 20.2 0 24s.9 7.4 2.6 10.7l7.8-6z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.3-8.5 2.3-6.3 0-11.7-3.9-13.6-9.4l-7.8 6C6.6 42.6 14.6 48 24 48z"/></svg>
            Continue with Google
          </button>
          <p className="muted small">We only see your name and email address from Google. Sending and reading
            replies uses a Gmail app password you'll create in the next step.</p>
          {config?.dev_login && (
            <form onSubmit={devLogin} className="stack" style={{ borderTop: "1px solid var(--line)", paddingTop: 16 }}>
              <label className="field">Test sign-in (development only)
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" />
              </label>
              <button className="btn" type="submit">Sign in without Google</button>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
