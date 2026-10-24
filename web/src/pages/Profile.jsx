import React, { useEffect, useState } from "react";
import { api, download } from "../api.js";
import { PageHead, Spinner, useAction, useApp } from "../ui.jsx";

const KINDS = [
  { id: "recommendation", name: "Recommendation letter" },
  { id: "internship_report", name: "Internship report" },
  { id: "offer_letter", name: "Offer letter" },
  { id: "loi", name: "Letter of interest" },
  { id: "proposal", name: "Research proposal" },
  { id: "other", name: "Other document" },
];
const KIND_NAME = { cv: "CV", ...Object.fromEntries(KINDS.map((k) => [k.id, k.name])) };
const GOALS = [
  { id: "teep", name: "TEEP internship", hint: "A research internship in a Taiwanese university lab through TEEP." },
  { id: "iipp", name: "IIPP internship", hint: "A research internship through the International Internship Pilot Program." },
  { id: "admission", name: "Admission", hint: "A Master's or PhD place under the professor's supervision." },
];

export default function Profile() {
  const { me, refreshMe, go } = useApp();
  const [docs, setDocs] = useState(null);
  const load = () => api("/documents").then(setDocs).catch(() => setDocs([]));
  useEffect(() => { load(); }, []);
  const cv = docs?.find((d) => d.kind === "cv");
  const others = docs?.filter((d) => d.kind !== "cv") || [];

  return (
    <>
      <PageHead title="Documents and goal">
        Upload your CV and any recommendation letter, internship report or offer letter. They're attached to your
        first email, and you'll give them to an AI to personalise your three emails. Only the CV and goal are required.
      </PageHead>
      <Upload kind="cv" title="Your CV" existing={cv} onDone={() => { load(); refreshMe(); }} />
      <OtherDocs docs={others} onChange={load} />
      <GoalForm me={me} onSaved={refreshMe} />
      <div className="row" style={{ marginTop: 16 }}>
        <div className="spacer" />
        <button className="btn" onClick={() => go("emails")} disabled={!me.setup.cv || !me.setup.goal}>Next: your three emails</button>
      </div>
    </>
  );
}

function Upload({ kind, title, existing, onDone }) {
  const [busy, run] = useAction();
  const [warning, setWarning] = useState("");
  const pick = async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    form.append("kind", kind);
    const r = await run(() => api("/documents", { method: "POST", form }), `${KIND_NAME[kind]} uploaded`);
    if (r) { setWarning(r.warning || ""); onDone(); }
  };
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        {existing && <span className="tag positive">Attached to your first email</span>}
      </div>
      {existing ? (
        <div className="row">
          <div><b>{existing.filename}</b><div className="muted small">{(existing.size / 1024).toFixed(0)} KB</div></div>
          <div className="spacer" />
          <button className="btn small" onClick={() => download(`/documents/${existing.id}/file`, existing.filename)}>Download</button>
          <label className="btn small">{busy ? <Spinner /> : "Replace"}<input type="file" accept=".pdf,.docx,.txt" hidden onChange={pick} /></label>
        </div>
      ) : (
        <div className="stack">
          <p className="muted small">PDF or Word, up to 10 MB.</p>
          <label className="btn primary" style={{ width: "fit-content" }}>{busy ? <><Spinner /> Uploading…</> : "Upload CV"}
            <input type="file" accept=".pdf,.docx,.txt" hidden onChange={pick} /></label>
        </div>
      )}
      {warning && <div className="note warn" style={{ marginTop: 12 }}>{warning}</div>}
    </div>
  );
}

function OtherDocs({ docs, onChange }) {
  const [kind, setKind] = useState("recommendation");
  const [busy, run] = useAction();
  const pick = async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    form.append("kind", kind);
    if (await run(() => api("/documents", { method: "POST", form }), "Uploaded")) onChange();
  };
  const toggle = async (d) => { await run(() => api(`/documents/${d.id}`, { method: "PATCH", body: { attach: !d.attach } })); onChange(); };
  const remove = async (d) => {
    if (!window.confirm(`Delete ${d.filename}?`)) return;
    await run(() => api(`/documents/${d.id}`, { method: "DELETE" }), "Deleted");
    onChange();
  };
  return (
    <div className="panel">
      <h2 style={{ marginBottom: 6 }}>Other documents <span className="muted small">(optional)</span></h2>
      <p className="muted small" style={{ marginBottom: 14 }}>Recommendation letter, internship report, offer letter and
        so on. Untick “Attach” for anything you want the AI to read but don't want sent to professors.</p>
      {docs.length > 0 && (
        <div className="table-wrap" style={{ marginBottom: 14 }}>
          <table><tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td><b>{d.filename}</b><div className="sub">{KIND_NAME[d.kind]}</div></td>
                <td><label className="check"><input type="checkbox" checked={d.attach} onChange={() => toggle(d)} disabled={busy} /> Attach</label></td>
                <td style={{ textAlign: "right" }}><button className="btn ghost small danger" onClick={() => remove(d)}>Delete</button></td>
              </tr>
            ))}
          </tbody></table>
        </div>
      )}
      <div className="row">
        <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: "auto" }} aria-label="Document type">
          {KINDS.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
        </select>
        <label className="btn">{busy ? <Spinner /> : "Upload"}<input type="file" accept=".pdf,.docx,.txt" hidden onChange={pick} /></label>
      </div>
    </div>
  );
}

function GoalForm({ me, onSaved }) {
  const [goal, setGoal] = useState(me.goal || "");
  const [d, setD] = useState({ full_name: me.name, ...me.details });
  const [busy, run] = useAction();
  const set = (k) => (e) => setD({ ...d, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    if (!goal) return;
    if (await run(() => api("/profile", { method: "PUT", body: { goal, details: d } }), "Saved")) onSaved();
  };
  return (
    <form className="panel stack" onSubmit={save}>
      <h2>What are you applying for?</h2>
      <div className="grid2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }} role="radiogroup" aria-label="Goal">
        {GOALS.map((g) => (
          <label key={g.id} className="panel" style={{ cursor: "pointer", margin: 0, padding: 14, borderColor: goal === g.id ? "var(--primary)" : undefined, background: goal === g.id ? "var(--primary-wash)" : undefined }}>
            <span className="check"><input type="radio" name="goal" checked={goal === g.id} onChange={() => setGoal(g.id)} /> <b>{g.name}</b></span>
            <span className="muted small" style={{ display: "block", marginTop: 4 }}>{g.hint}</span>
          </label>
        ))}
      </div>
      <h3 style={{ marginTop: 8 }}>Details <span className="muted small">(optional; leave empty for a general email)</span></h3>
      <div className="grid2">
        <label className="field">Full name<input type="text" value={d.full_name || ""} onChange={set("full_name")} /></label>
        {goal === "admission" && <label className="field">Degree<input type="text" value={d.degree || ""} onChange={set("degree")} placeholder="Master's or PhD" /></label>}
        <label className="field">Start date<input type="text" value={d.start_date || ""} onChange={set("start_date")} placeholder="e.g. February 2027" /></label>
        <label className="field">End date<input type="text" value={d.end_date || ""} onChange={set("end_date")} placeholder="e.g. July 2027" /></label>
        <label className="field">Where you are now<input type="text" value={d.current_location || ""} onChange={set("current_location")} placeholder="e.g. Chennai, India" /></label>
        {goal === "admission" && <label className="field">Scholarships you're applying for<input type="text" value={d.scholarship || ""} onChange={set("scholarship")} /></label>}
        <label className="field">Phone<input type="text" value={d.phone || ""} onChange={set("phone")} /></label>
        <label className="field">LinkedIn<input type="text" value={d.linkedin || ""} onChange={set("linkedin")} /></label>
      </div>
      <label className="field">Your plans, in your own words
        <span className="hint">What you want to research or learn, and why. This goes into the prompt for the AI.</span>
        <textarea value={d.plans || ""} onChange={set("plans")} />
      </label>
      <label className="field">Signature <span className="hint">Leave empty to use “Sincerely,” with your name, phone and LinkedIn.</span>
        <textarea value={d.signature || ""} onChange={set("signature")} style={{ minHeight: 70 }} />
      </label>
      <div className="row"><button className="btn primary" type="submit" disabled={busy || !goal}>Save</button>
        {!goal && <span className="muted small">Choose a goal first.</span>}</div>
    </form>
  );
}
