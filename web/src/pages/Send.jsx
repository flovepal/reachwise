import React, { useCallback, useEffect, useState } from "react";
import { api, when } from "../api.js";
import { KIND_NAMES, PageHead, Spinner, useAction, useApp, usePoll } from "../ui.jsx";

export default function Send() {
  const { me, refreshMe, go, config } = useApp();
  const [profs, setProfs] = useState(null);
  const [docs, setDocs] = useState([]);
  const [queue, setQueue] = useState(null);
  const [failed, setFailed] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, run] = useAction();

  const load = useCallback(async () => {
    const [p, d, q, f] = await Promise.all([
      api("/professors"), api("/documents"), api("/emails/queue"), api("/emails?status=failed"),
    ]).catch(() => [[], [], null, []]);
    setProfs(p); setDocs(d); setQueue(q); setFailed(f);
  }, []);
  useEffect(() => { load(); }, [load]);
  usePoll(() => { load(); refreshMe(); }, 10000, !!queue && (queue.queued > 0));

  if (!profs || !queue) return <Spinner />;

  const fresh = profs.filter((p) => p.status === "new");
  const attached = docs.filter((d) => d.attach);
  const missing = [
    !me.setup.gmail && ["Connect Gmail", "gmail"],
    !me.setup.professors && ["Add professors", "professors"],
    !(me.setup.cv && me.setup.goal) && ["Upload your CV and choose a goal", "profile"],
    !me.setup.templates && ["Write your three emails", "emails"],
  ].filter(Boolean);
  const gap = config?.gap_seconds || [70, 120];
  const minutes = Math.round((fresh.length * (gap[0] + gap[1])) / 2 / 60);

  const send = async () => {
    if (!window.confirm(`Send your first email to ${fresh.length} professor${fresh.length === 1 ? "" : "s"} from ${me.gmail.address}?`)) return;
    const r = await run(() => api("/send/initial", { method: "POST", body: {} }));
    if (r) { setResult(r); load(); refreshMe(); }
  };
  const act = async (path, ok) => { await run(() => api(path, { method: "POST" }), ok); load(); };
  const done = queue.sent_last_24h;
  const total = done + queue.queued;

  return (
    <>
      <PageHead title="Send your first emails">
        Each professor gets your first email from your own Gmail. After that, come back in {config?.reminder_after_days || 5} days
        to check replies and send reminders.
      </PageHead>

      {missing.length > 0 && (
        <div className="panel stack">
          <h2>Before you can send</h2>
          {missing.map(([text, key]) => (
            <div key={key} className="row"><span>{text}</span><div className="spacer" /><button className="btn small" onClick={() => go(key)}>Open</button></div>
          ))}
        </div>
      )}

      {queue.queued > 0 && (
        <div className="panel stack">
          <div className="panel-head" style={{ marginBottom: 0 }}>
            <h2>{queue.paused ? "Sending paused" : "Sending now"}</h2>
            <span className="muted small">{done} of {total} sent</span>
          </div>
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
            <div style={{ width: `${total ? (100 * done) / total : 0}%` }} />
          </div>
          <p className="small">
            {queue.paused ? "Nothing more will go out until you resume." :
              <>Next email around {when(queue.next_at)}. The last one should go out around {when(queue.finish_at)}.</>}
          </p>
          <p className="muted small">{queue.explanation}</p>
          <div className="row">
            {queue.paused
              ? <button className="btn primary" onClick={() => act("/emails/resume", "Sending resumed")} disabled={busy}>Resume sending</button>
              : <button className="btn" onClick={() => act("/emails/pause", "Sending paused")} disabled={busy}>Pause</button>}
            <button className="btn danger" disabled={busy} onClick={() => window.confirm("Cancel every email that hasn't gone out yet?") && act("/emails/cancel", "Cancelled")}>Cancel the rest</button>
          </div>
        </div>
      )}

      {result && queue.queued === 0 && done > 0 && (
        <div className="note good" style={{ marginBottom: 16 }}>All {done} emails have been sent. We'll remind you when it's time to check replies.</div>
      )}

      {missing.length === 0 && fresh.length > 0 && queue.queued === 0 && (
        <div className="panel stack">
          <h2>Ready to send to {fresh.length} professor{fresh.length === 1 ? "" : "s"}</h2>
          <div className="grid2">
            <div><div className="muted small">From</div>{me.gmail.display_name} &lt;{me.gmail.address}&gt;</div>
            <div><div className="muted small">Attached</div>{attached.length ? attached.map((d) => d.filename).join(", ") : "Nothing"}</div>
          </div>
          <div className="note">
            <b>Why it takes a while:</b> emails go out one at a time, about {gap[1] < 60 ? `${gap[0]}–${gap[1]} seconds` : `${Math.max(1, Math.round(gap[0] / 60))}–${Math.round(gap[1] / 60)} minutes`} apart,
            at most {queue.daily_cap} a day. Sending slowly from your own account looks like normal email, so it's
            much less likely to be marked as spam. For {fresh.length} professors that's about {minutes < 90 ? `${minutes} minutes` : `${Math.round(minutes / 60)} hours`}.
            You can close this page; sending continues.
          </div>
          <div className="row">
            <button className="btn primary big" onClick={send} disabled={busy}>Send first emails</button>
            <button className="btn" onClick={() => go("emails")}>Check the email again</button>
          </div>
        </div>
      )}

      {missing.length === 0 && fresh.length === 0 && queue.queued === 0 && (
        <div className="panel stack">
          <h2>Everyone on your list has been emailed</h2>
          <p className="muted">Add more professors to send to them, or go to Replies to see who answered.</p>
          <div className="row"><button className="btn primary" onClick={() => go("replies")}>See replies</button>
            <button className="btn" onClick={() => go("professors")}>Add professors</button></div>
        </div>
      )}

      {failed.length > 0 && (
        <div className="panel stack" style={{ marginTop: 16 }}>
          <div className="panel-head" style={{ marginBottom: 0 }}>
            <h2>{failed.length} email{failed.length === 1 ? "" : "s"} didn't send</h2>
            <button className="btn small" onClick={() => act("/emails/retry", "Queued again")} disabled={busy}>Try again</button>
          </div>
          <div className="table-wrap"><table><tbody>
            {failed.map((e) => (
              <tr key={e.id}><td>{e.professor?.name}<div className="sub">{KIND_NAMES[e.kind]}</div></td><td className="small">{e.error}</td></tr>
            ))}
          </tbody></table></div>
        </div>
      )}
    </>
  );
}
