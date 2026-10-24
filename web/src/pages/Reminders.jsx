import React, { useCallback, useEffect, useState } from "react";
import { api, day, when } from "../api.js";
import { KIND_NAMES, PageHead, Spinner, useAction, useApp, usePoll } from "../ui.jsx";
import { AnalyseButton } from "./Replies.jsx";

export default function Reminders() {
  const { go, refreshMe } = useApp();
  const [st, setSt] = useState(null);
  const [summary, setSummary] = useState(null);
  const [queue, setQueue] = useState(null);
  const [busy, run] = useAction();

  const load = useCallback(async () => {
    const [s, sm, q] = await Promise.all([api("/reminders"), api("/replies/summary"), api("/emails/queue")]).catch(() => [null, null, null]);
    setSt(s); setSummary(sm); setQueue(q);
  }, []);
  useEffect(() => { load(); }, [load]);
  usePoll(load, 3000, summary?.analysis?.status === "running");

  if (!st) return <Spinner />;

  const skip = async (p, value) => {
    if (await run(() => api(`/professors/${p.professor_id}/reminders`, { method: "POST", body: { skip: value } }),
      value ? `${p.name} won't get reminders` : `${p.name} is back on the list`)) load();
  };
  const send = async () => {
    const n = st.eligible.length;
    if (!window.confirm(`Send a reminder to ${n} professor${n === 1 ? "" : "s"}? Each goes in the same thread as your earlier email.`)) return;
    if (await run(() => api("/send/reminders", { method: "POST", body: {} }), "Reminders are being sent")) { load(); refreshMe(); }
  };
  const byKind = (k) => st.eligible.filter((e) => e.kind === k).length;

  return (
    <>
      <PageHead title="Reminders">
        Reminders are offered {st.wait_days} days after your last email, only to professors who haven't replied.
        Anyone who answered (positively, negatively, or in a separate email) is left out automatically. You can remove
        anyone else yourself.
      </PageHead>

      {queue?.queued > 0 && (
        <div className="note" style={{ marginBottom: 16 }}>
          {queue.queued} email{queue.queued === 1 ? " is" : "s are"} waiting to go out; the last around {when(queue.finish_at)}.{" "}
          <button className="btn small" onClick={() => go("send")}>See progress</button>
        </div>
      )}

      {st.eligible.length > 0 && st.analysis_needed && (
        <div className="panel stack">
          <h2>First, check for replies</h2>
          <p className="muted">{st.eligible.length} professor{st.eligible.length === 1 ? " is" : "s are"} due for a reminder.
            Check your inbox now so nobody who already answered gets one.</p>
          <div><AnalyseButton summary={summary} onDone={load} /></div>
        </div>
      )}

      {st.eligible.length > 0 && !st.analysis_needed && (
        <div className="panel stack">
          <div className="panel-head" style={{ marginBottom: 0 }}>
            <h2>Ready: {st.eligible.length} reminder{st.eligible.length === 1 ? "" : "s"}</h2>
            <span className="muted small">Replies checked {when(st.last_analysed_at)}</span>
          </div>
          <p className="muted small">
            {byKind("reminder1") > 0 && `${byKind("reminder1")} will get Reminder 1. `}
            {byKind("reminder2") > 0 && `${byKind("reminder2")} will get Reminder 2. `}
            Right before each one goes out, we check that professor's mail once more.
          </p>
          <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
            <table>
              <thead><tr><th>Professor</th><th>Reminder</th><th>Last emailed</th><th aria-label="Remove" /></tr></thead>
              <tbody>{st.eligible.map((p) => (
                <tr key={p.professor_id}>
                  <td>{p.name}<div className="sub">{p.email}</div></td>
                  <td>{KIND_NAMES[p.kind]}</td>
                  <td className="small">{day(p.last_sent_at)}</td>
                  <td style={{ textAlign: "right" }}><button className="btn ghost small danger" onClick={() => skip(p, true)} disabled={busy}>Remove</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="row">
            <button className="btn primary big" onClick={send} disabled={busy}>Send {st.eligible.length} reminder{st.eligible.length === 1 ? "" : "s"}</button>
            <button className="btn" onClick={() => go("emails")}>Edit reminder text</button>
          </div>
        </div>
      )}

      {st.eligible.length === 0 && (
        <div className="panel stack">
          <h2>No reminders due right now</h2>
          <p className="muted">
            {st.upcoming.length > 0
              ? `The next ${st.upcoming.length === 1 ? "one opens" : "ones open"} on ${day(st.upcoming[0].due_at)}. We'll send you a notification and an email then.`
              : "Everyone has either replied or received both reminders."}
          </p>
        </div>
      )}

      {st.upcoming.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h2 style={{ marginBottom: 12 }}>Coming up</h2>
          <div className="table-wrap" style={{ maxHeight: 320, overflowY: "auto" }}><table>
            <thead><tr><th>Professor</th><th>Reminder</th><th>Opens on</th><th aria-label="Remove" /></tr></thead>
            <tbody>{st.upcoming.map((p) => (
              <tr key={p.professor_id}>
                <td>{p.name}<div className="sub">{p.email}</div></td><td>{KIND_NAMES[p.kind]}</td><td className="small">{day(p.due_at)}</td>
                <td style={{ textAlign: "right" }}><button className="btn ghost small danger" onClick={() => skip(p, true)} disabled={busy}>Remove</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        </div>
      )}

      {st.removed.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h2 style={{ marginBottom: 6 }}>Removed by you</h2>
          <p className="muted small" style={{ marginBottom: 12 }}>These professors won't get reminders.</p>
          <div className="table-wrap"><table><tbody>{st.removed.map((p) => (
            <tr key={p.professor_id}>
              <td>{p.name}<div className="sub">{p.email}</div></td>
              <td style={{ textAlign: "right" }}><button className="btn ghost small" onClick={() => skip(p, false)} disabled={busy}>Put back</button></td>
            </tr>
          ))}</tbody></table></div>
        </div>
      )}
    </>
  );
}
