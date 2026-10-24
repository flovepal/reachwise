import React, { useEffect, useRef, useState } from "react";
import { api, download } from "../api.js";
import { LABEL_NAMES, PageHead, Spinner, useAction, useApp } from "../ui.jsx";

const EMPTY = { name: "", email: "", research_area: "", university: "", department: "", profile_url: "", notes: "" };
const STATUS = { new: "Not emailed", contacted: "Emailed", replied: "Replied", bounced: "Didn't arrive" };

export default function Professors() {
  const { refreshMe, go } = useApp();
  const [list, setList] = useState(null);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);   // null | "new" | professor
  const [busy, run] = useAction();

  const load = () => api("/professors").then(setList).catch(() => setList([]));
  useEffect(() => { load(); }, []);

  const remove = async (p) => {
    if (!window.confirm(`Remove ${p.name} from your list?`)) return;
    await run(() => api(`/professors/${p.id}`, { method: "DELETE" }), "Removed");
    load(); refreshMe();
  };

  const shown = (list || []).filter((p) => !q || `${p.name} ${p.email} ${p.research_area}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHead title="Your professors">
        Add the professors you want to write to. If your department shared a ready-made list, import it. You can
        also add or fix professors one at a time.
      </PageHead>

      <Importer onDone={() => { load(); refreshMe(); }} />

      {editing && (
        <ProfessorForm initial={editing === "new" ? EMPTY : editing}
          onCancel={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); refreshMe(); }} />
      )}

      <div className="panel">
        <div className="panel-head">
          <h2>{list ? `${list.length} professor${list.length === 1 ? "" : "s"}` : "Professors"}</h2>
          <div className="row">
            <button className="btn primary small" onClick={() => setEditing("new")}>Add a professor</button>
            {list?.length > 0 && <button className="btn small" onClick={() => download("/professors/export", "professors.csv")}>Download CSV</button>}
          </div>
        </div>
        {list === null && <Spinner />}
        {list?.length === 0 && <p className="muted">No professors yet. Import a file above or add one by hand.</p>}
        {list?.length > 0 && (
          <>
            <input type="text" placeholder="Search by name, email or research area" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 12 }} aria-label="Search professors" />
            <div className="table-wrap">
              <table>
                <thead><tr><th>Professor</th><th>Research area</th><th>Status</th><th aria-label="Actions" /></tr></thead>
                <tbody>
                  {shown.map((p) => (
                    <tr key={p.id}>
                      <td>{p.name}<div className="sub">{p.email}</div></td>
                      <td>{p.research_area || <span className="muted">Not given</span>}{p.university && <div className="sub">{p.university}</div>}</td>
                      <td>
                        <span className={`tag ${p.status === "replied" ? "blue" : p.status === "bounced" ? "problem" : ""}`}>
                          {p.status === "contacted" && p.reply_label === "auto_reply" ? LABEL_NAMES.auto_reply : STATUS[p.status] || p.status}
                        </span>
                      </td>
                      <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                        <button className="btn ghost small" onClick={() => setEditing(p)}>Edit</button>
                        <button className="btn ghost small danger" onClick={() => remove(p)} disabled={busy}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row" style={{ marginTop: 16 }}>
              <div className="spacer" />
              <button className="btn" onClick={() => go("profile")}>Next: documents and goal</button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function ProfessorForm({ initial, onCancel, onSaved }) {
  const [f, setF] = useState(initial);
  const [busy, run] = useAction();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, f[k] || ""]));
    const r = await run(() => initial.id
      ? api(`/professors/${initial.id}`, { method: "PUT", body })
      : api("/professors", { method: "POST", body }), initial.id ? "Saved" : "Professor added");
    if (r) onSaved();
  };
  return (
    <form className="panel stack" onSubmit={save}>
      <h2>{initial.id ? `Edit ${initial.name}` : "Add a professor"}</h2>
      <div className="grid2">
        <label className="field">Name<input type="text" required value={f.name} onChange={set("name")} placeholder="Pu-Jen Cheng" /></label>
        <label className="field">Email<input type="email" required value={f.email} onChange={set("email")} placeholder="name@university.edu" /></label>
      </div>
      <label className="field">Research area <span className="hint">Goes into your email as “your research in …”. Leave empty if you don't know it.</span>
        <input type="text" value={f.research_area} onChange={set("research_area")} placeholder="Computer Vision, Machine Learning" />
      </label>
      <div className="grid2">
        <label className="field">University<input type="text" value={f.university} onChange={set("university")} /></label>
        <label className="field">Department<input type="text" value={f.department} onChange={set("department")} /></label>
      </div>
      <label className="field">Profile page<input type="url" value={f.profile_url} onChange={set("profile_url")} placeholder="https://" /></label>
      <label className="field">Notes for yourself<textarea value={f.notes} onChange={set("notes")} style={{ minHeight: 60 }} /></label>
      <div className="row">
        <button className="btn primary" type="submit" disabled={busy}>{initial.id ? "Save changes" : "Add professor"}</button>
        <button className="btn" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function Importer({ onDone }) {
  const fileRef = useRef();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [update, setUpdate] = useState(false);
  const [busy, run] = useAction();

  const pick = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    const form = new FormData();
    form.append("file", f);
    const r = await run(() => api("/professors/import/preview", { method: "POST", form }));
    setPreview(r || null);
  };
  const save = async () => {
    const form = new FormData();
    form.append("file", file);
    form.append("update_existing", update ? "true" : "false");
    const r = await run(() => api("/professors/import", { method: "POST", form }));
    if (r) {
      setPreview({ ...preview, saved: r });
      onDone();
    }
  };
  const reset = () => { setFile(null); setPreview(null); if (fileRef.current) fileRef.current.value = ""; };

  const bad = preview?.rows?.filter((r) => r.errors.length) || [];
  const toAdd = (preview?.valid || 0) - (update ? 0 : preview?.already_in_list || 0);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Import a list</h2>
        <button className="btn ghost small" onClick={() => download("/professors/template", "professors_template.csv")}>Download a blank template</button>
      </div>
      {!preview && (
        <div className="stack">
          <p className="muted small">CSV or Excel. It needs <b>Professor</b> and <b>Email</b> columns. Research Area, University,
            Department, Profile URL and Notes are optional. Columns are matched by name, so their order doesn't matter.</p>
          <label className="btn" style={{ width: "fit-content" }}>
            {busy ? <><Spinner /> Checking…</> : "Choose a file"}
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm,.tsv,.txt" onChange={pick} hidden />
          </label>
        </div>
      )}
      {preview && preview.fatal && (
        <div className="stack">
          <div className="note bad">{preview.fatal}</div>
          <button className="btn" onClick={reset}>Choose another file</button>
        </div>
      )}
      {preview && !preview.fatal && !preview.saved && (
        <div className="stack">
          <p><b>{file?.name}</b>: {preview.valid} ready to import
            {bad.length > 0 && <>, <span style={{ color: "var(--danger)" }}>{bad.length} with problems</span></>}
            {preview.already_in_list > 0 && <>, {preview.already_in_list} already in your list</>}.</p>
          <p className="muted small">Columns found: {Object.entries(preview.columns).map(([k, v]) => `${k} → ${v.replace("_", " ")}`).join(", ")}</p>
          {preview.column_warnings.map((w) => <div key={w} className="note warn">{w}</div>)}
          {bad.length > 0 && (
            <>
              <p className="small">These rows will be skipped. Fix them in your file and import again, or add them by hand:</p>
              <div className="table-wrap" style={{ maxHeight: 260, overflowY: "auto" }}>
                <table>
                  <thead><tr><th>Row</th><th>Professor</th><th>Email</th><th>Problem</th></tr></thead>
                  <tbody>{bad.map((r) => (
                    <tr key={r.row} className="err"><td>{r.row}</td><td>{r.data.name}</td><td>{r.data.email}</td><td>{r.errors.join("; ")}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          )}
          {preview.already_in_list > 0 && (
            <label className="check"><input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} />
              Update the professors already in my list with details from this file</label>
          )}
          <div className="row">
            <button className="btn primary" onClick={save} disabled={busy || preview.valid === 0}>
              {update ? `Import ${preview.valid} professors` : `Import ${toAdd} new professor${toAdd === 1 ? "" : "s"}`}
            </button>
            <button className="btn" onClick={reset}>Cancel</button>
          </div>
        </div>
      )}
      {preview?.saved && (
        <div className="stack">
          <div className="note good">
            Imported {preview.saved.added} professor{preview.saved.added === 1 ? "" : "s"}
            {preview.saved.updated > 0 && `, updated ${preview.saved.updated}`}
            {preview.saved.skipped_existing > 0 && `, skipped ${preview.saved.skipped_existing} already in your list`}
            {preview.saved.invalid_rows.length > 0 && `, skipped ${preview.saved.invalid_rows.length} with problems`}.
          </div>
          <button className="btn" onClick={reset} style={{ width: "fit-content" }}>Import another file</button>
        </div>
      )}
    </div>
  );
}
