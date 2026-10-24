import React, { useState } from "react";
import { api, when } from "../api.js";
import { PageHead, Spinner, useAction, useApp } from "../ui.jsx";

export default function Gmail() {
  const { me, refreshMe, go } = useApp();
  const [address, setAddress] = useState(me.gmail.address || me.email);
  const [password, setPassword] = useState("");
  const [name, setName] = useState(me.gmail.display_name || me.name);
  const [busy, run] = useAction();
  const [error, setError] = useState("");

  const connect = async (e) => {
    e.preventDefault();
    setError("");
    const r = await run(async () => {
      try {
        return await api("/gmail", { method: "POST", body: { app_password: password, address, display_name: name } });
      } catch (err) { setError(err.message); throw err; }
    }, "Gmail connected");
    if (r) { setPassword(""); await refreshMe(); }
  };
  const disconnect = async () => {
    if (!window.confirm("Disconnect Gmail? Sending will stop until you connect again.")) return;
    await run(() => api("/gmail", { method: "DELETE" }), "Gmail disconnected");
    refreshMe();
  };

  return (
    <>
      <PageHead title="Connect your Gmail">
        Your emails are sent from your own Gmail, so replies come straight to your inbox. Reachwise needs a Gmail
        app password to send for you and to check which professors replied.
      </PageHead>

      {me.gmail.connected && (
        <div className="panel">
          <div className="row">
            <div>
              <h2>Connected: {me.gmail.address}</h2>
              <p className="muted small">Checked {when(me.gmail.verified_at)}. Emails will show as from “{me.gmail.display_name}”.</p>
            </div>
            <div className="spacer" />
            <button className="btn" onClick={() => go("professors")}>Next: professors</button>
            <button className="btn danger" onClick={disconnect} disabled={busy}>Disconnect</button>
          </div>
        </div>
      )}

      <div className="panel">
        <h2 style={{ marginBottom: 14 }}>How to create an app password</h2>
        <ol className="steps">
          <li><div><b>Turn on 2-Step Verification.</b> Open{" "}
            <a href="https://myaccount.google.com/signinoptions/twosv" target="_blank" rel="noreferrer">Google Account → 2-Step Verification</a>{" "}
            and switch it on. App passwords only appear after this is on.</div></li>
          <li><div><b>Open the app passwords page:</b>{" "}
            <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">myaccount.google.com/apppasswords</a>.
            Google may ask you to sign in again.</div></li>
          <li><div><b>Type a name</b> such as “Reachwise” and press <b>Create</b>.</div></li>
          <li><div><b>Copy the 16-letter password</b> Google shows (like <code>abcd efgh ijkl mnop</code>) and paste it
            below. Spaces don't matter. Google shows it only once.</div></li>
          <li><div><b>Nothing to change in Gmail settings.</b> Reading replies uses IMAP, which Gmail now keeps switched
            on for every account. Leave the IMAP options as they are.</div></li>
        </ol>
        <div className="note warn" style={{ marginTop: 16 }}>
          If the app passwords page says the setting isn't available, your account is managed by your college and
          app passwords are switched off. Use a personal Gmail account instead.
        </div>
      </div>

      <form className="panel stack" onSubmit={connect}>
        <h2>{me.gmail.connected ? "Change Gmail account or password" : "Enter your app password"}</h2>
        <div className="grid2">
          <label className="field">Gmail address
            <input type="email" required value={address} onChange={(e) => setAddress(e.target.value)} />
          </label>
          <label className="field">Your name as professors will see it
            <input type="text" required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        </div>
        <label className="field">App password
          <input type="password" required minLength={8} autoComplete="off" value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder="16 letters from Google" />
          <span className="hint">Stored encrypted. It's used only to send your emails and to read replies from professors on your list.</span>
        </label>
        {error && <div className="note bad">{error}</div>}
        <div className="row">
          <button className="btn primary" type="submit" disabled={busy}>{busy ? <><Spinner /> Checking with Gmail…</> : "Connect Gmail"}</button>
          <span className="muted small">We test sending and reading before saving.</span>
        </div>
      </form>
    </>
  );
}
