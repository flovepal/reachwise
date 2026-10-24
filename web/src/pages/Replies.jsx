import React, { useCallback, useEffect, useState } from "react";
import { api, day, when } from "../api.js";
import { LABEL_NAMES, PageHead, Spinner, useAction, useApp, usePoll } from "../ui.jsx";

// Three tabs only: who replied, who hasn't, and whose email didn't arrive
const GROUPS = [
  { key: "replied", name: "Replied", match: (r) => ["positive", "negative", "other"].includes(r.group) },
  { key: "no_reply", name: "Not replied" },
  { key: "problem", name: "Didn't arrive", match: (r) => r.group === "problem" },
];

export function Stamps({ stats, summary }) {
  const n = (k) => stats?.[k]?.sent || 0;
  const live = n("reminder2") ? 2 : n("reminder1") ? 1 : 0;
  const items = [
    { t: "First email", c: n("initial"), d: n("initial") ? "sent" : "not sent yet" },
    { t: "Reminder 1", c: n("reminder1"), d: n("reminder1") ? "sent" : n("initial") ? "5 days after the first email" : "" },
    { t: "Reminder 2", c: n("reminder2"), d: n("reminder2") ? "sent" : n("reminder1") ? "5 days after reminder 1" : "" },
  ];
  return (
    <div className="stamps" aria-label="Your emails so far">
      {items.map((x, i) => (
        <div key={x.t} className={`stamp ${i === live && x.c ? "live" : ""}`}>
          {x.c > 0 && <span className="mark" aria-hidden="true">SENT</span>}
          <div className="n">{x.c}</div>
          <div className="t">{x.t}</div>
          <div className="d">{x.d}</div>
        </div>
      ))}
      {summary?.next_reminder_at && !summary.reminders_available && (
        <p className="muted small" style={{ gridColumn: "1 / -1", marginTop: 10 }}>Next reminders open on {day(summary.next_reminder_at)}.</p>
      )}
    </div>
  );
}

export function AnalyseButton({ summary, onDone, primary = true }) {
  const [busy, run] = useAction();
  const running = summary?.analysis?.status === "running";
  const start = async () => { if (await run(() => api("/replies/analyse", { method: "POST" }))) onDone(); };
  return (
    <button className={`btn ${primary ? "primary" : ""}`} onClick={start} disabled={busy || running}>
      {running ? <><Spinner /> Checking your inbox…</> : "Analyse replies"}
    </button>
  );
}

export default function Replies() {
  const { go } = useApp();
  const [summary, setSummary] = useState(null);
  const [stats, setStats] = useState(null);
  const [group, setGroup] = useState("replied");
  const [replies, setReplies] = useState(null);
  const [possible, setPossible] = useState([]);
  const [noReply, setNoReply] = useState([]);

  const load = useCallback(async () => {
    const [s, st, r, p, nr] = await Promise.all([
      api("/replies/summary"), api("/emails/stats"), api("/replies"), api("/replies?status=possible"), api("/replies/no-reply"),
    ]).catch(() => [null, null, [], [], []]);
    setSummary(s); setStats(st); setReplies(r); setPossible(p); setNoReply(nr);
  }, []);
  useEffect(() => { load(); }, [load]);
  const running = summary?.analysis?.status === "running";
  usePoll(load, 3000, running);

  if (!summary) return <Spinner />;
  const c = summary.counts;
  const sentAny = stats?.sent_total > 0;
  const tab = GROUPS.find((g) => g.key === group);
  const shown = tab.match ? (replies || []).filter(tab.match) : [];

  return (
    <>
      <PageHead title="Replies">
        Tap Analyse replies to check your Gmail, including Spam, for answers from your professors. Anyone who
        replied is left out of reminders. Read each reply and answer it in Gmail.
      </PageHead>

      <Stamps stats={stats} summary={summary} />

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="row">
          <div>
            <h2>{summary.last_analysed_at ? `Last checked ${when(summary.last_analysed_at)}` : "Not checked yet"}</h2>
            {summary.analysis?.status === "failed" && <p className="small" style={{ color: "var(--danger)" }}>Last check failed: {summary.analysis.error}</p>}
            {summary.analysis?.status === "done" && summary.analysis.skipped > 0 && (
              <p className="small" style={{ color: "var(--warning)" }}>
                {summary.analysis.skipped} email{summary.analysis.skipped === 1 ? "" : "s"} couldn't be read because Gmail was slow.
                Tap Analyse replies again to include {summary.analysis.skipped === 1 ? "it" : "them"}.
              </p>
            )}
            {!sentAny && <p className="muted small">Send your first emails, then come back here.</p>}
          </div>
          <div className="spacer" />
          <AnalyseButton summary={summary} onDone={load} />
        </div>
        {summary.reminders_available > 0 && (
          <div className="note" style={{ marginTop: 14 }}>
            <div className="row">
              <span>{summary.reminders_available} professor{summary.reminders_available === 1 ? " hasn't" : "s haven't"} replied in {5}+ days.</span>
              <div className="spacer" />
              <button className="btn small primary" onClick={() => go("reminders")}>Review reminders</button>
            </div>
          </div>
        )}
      </div>

      {possible.length > 0 && <Possible items={possible} onDone={load} />}

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="tabs" role="tablist">
          {GROUPS.map((g) => (
            <button key={g.key} role="tab" aria-selected={group === g.key} className={`tab ${group === g.key ? "on" : ""}`} onClick={() => setGroup(g.key)}>
              {g.name}<b>{c[g.key] || 0}</b>
            </button>
          ))}
        </div>
        {group === "replied" && c.needs_check > 0 && (
          <div className="note warn" style={{ marginBottom: 12 }}>
            {c.needs_check} {c.needs_check === 1 ? "reply was" : "replies were"} matched by the sender's name, not their
            email address. Please check {c.needs_check === 1 ? "it" : "them"} below.
          </div>
        )}
        {group === "no_reply" ? <NoReplyList rows={noReply} /> : (
          shown.length === 0
            ? <p className="muted">{summary.last_analysed_at ? "Nothing here." : "Tap Analyse replies to check your inbox."}</p>
            : shown.map((r) => <Reply key={r.id} r={r} onChange={load} />)
        )}
      </div>
    </>
  );
}

function Reply({ r, onChange }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, run] = useAction();
  const toggle = async () => {
    if (!open && !detail) setDetail(await api(`/replies/${r.id}`).catch(() => null));
    setOpen(!open);
  };
  const confirmName = async () => { if (await run(() => api(`/replies/${r.id}/checked`, { method: "POST" }), "Confirmed")) onChange(); };
  const notThem = async () => {
    if (!window.confirm(`Not from ${r.professor?.name}? They'll go back on the reminder list.`)) return;
    if (await run(() => api(`/replies/${r.id}/confirm`, { method: "POST", body: { professor_id: null } }), "Removed")) onChange();
  };
  return (
    <article className="reply" style={r.needs_check ? { borderColor: "var(--warning)" } : undefined}>
      {r.needs_check && (
        <div className="note warn" style={{ marginBottom: 10 }}>
          <div className="row">
            <span>Please check: this came from <b>{r.from_addr}</b>, matched to {r.professor?.name} by name.</span>
            <div className="spacer" />
            <button className="btn small" onClick={confirmName} disabled={busy}>Yes, it's from them</button>
            <button className="btn small danger" onClick={notThem} disabled={busy}>Not from them</button>
          </div>
        </div>
      )}
      <div className="row">
        <span className="who">{r.professor?.name || r.from_addr}</span>
        {r.label === "auto_reply" && <span className="tag">{LABEL_NAMES.auto_reply}</span>}
        <div className="spacer" />
        <span className="muted small">{when(r.received_at)}</span>
      </div>
      {r.in_spam && (
        <div className="note warn" style={{ margin: "8px 0" }}>
          This reply was in your <b>Spam</b> folder. Check there, open it and tap <b>Not spam</b> so their next email reaches your inbox.
        </div>
      )}
      <p className="summary">{r.summary}</p>
      <div className="row" style={{ marginTop: 10 }}>
        <a className="btn small primary" href={r.gmail_link} target="_blank" rel="noreferrer">Open in Gmail to reply</a>
        <button className="btn small" onClick={toggle} aria-expanded={open}>{open ? "Hide email" : "Read email"}</button>
      </div>
      {open && detail && <div className="letter-view"><b>{detail.subject}</b>{"\n\n"}{detail.body}</div>}
    </article>
  );
}

function Possible({ items, onDone }) {
  const [busy, run] = useAction();
  const [choice, setChoice] = useState({});
  const confirm = async (r, pid) => {
    if (await run(() => api(`/replies/${r.id}/confirm`, { method: "POST", body: { professor_id: pid } }), pid ? "Marked as replied" : "Ignored")) onDone();
  };
  return (
    <div className="panel stack" style={{ marginTop: 16 }}>
      <h2>Check {items.length === 1 ? "this reply" : `these ${items.length} replies`}</h2>
      <p className="muted small">These came from an address that isn't on your list, but look like answers to your email
        (for example from a professor's personal account). Tell us who sent each one.</p>
      {items.map((r) => (
        <div key={r.id} className="reply">
          <div className="row"><span className="who">{r.from_addr}</span><div className="spacer" /><span className="muted small">{when(r.received_at)}</span></div>
          <p className="summary"><b>{r.subject}</b>: {r.summary}</p>
          <div className="row" style={{ marginTop: 10 }}>
            <select value={choice[r.id] ?? (r.professor?.id || "")} onChange={(e) => setChoice({ ...choice, [r.id]: e.target.value })} style={{ width: "auto", flex: 1, minWidth: 180 }} aria-label="Which professor sent this">
              <option value="">Choose the professor…</option>
              {r.candidates.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.email})</option>)}
            </select>
            <button className="btn small primary" disabled={busy || !(choice[r.id] ?? r.professor?.id)} onClick={() => confirm(r, choice[r.id] ?? r.professor?.id)}>It's from them</button>
            <button className="btn small" disabled={busy} onClick={() => confirm(r, null)}>Not a reply</button>
            <a className="btn small ghost" href={r.gmail_link} target="_blank" rel="noreferrer">Open in Gmail</a>
          </div>
        </div>
      ))}
    </div>
  );
}

function NoReplyList({ rows }) {
  if (!rows.length) return <p className="muted">Nobody is waiting on a reply.</p>;
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Professor</th><th>Next reminder</th></tr></thead>
      <tbody>{rows.map((p) => (
        <tr key={p.id}>
          <td>{p.name}<div className="sub">{p.email}</div>{p.auto_reply && <span className="tag">Out of office</span>}</td>
          <td className="small">{p.next_reminder ? `${p.next_reminder === "reminder1" ? "Reminder 1" : "Reminder 2"}, from ${day(p.reminder_due_at)}` : <span className="muted">All reminders sent</span>}</td>
        </tr>
      ))}</tbody>
    </table></div>
  );
}
