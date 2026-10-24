import React, { useEffect, useRef, useState } from "react";
import { api, download } from "../api.js";
import { PageHead, Spinner, useAction, useApp } from "../ui.jsx";

const VERSIONS = "ABC";
const REMINDERS = [
  { key: "reminder1_body", name: "Email 2", when: "Reminder, 5 days later, only to professors who haven't replied" },
  { key: "reminder2_body", name: "Email 3", when: "Last reminder, 5 days after email 2, same rule" },
];
const HELP = {
  "{professor}": "Professor + surname",
  "{research_in}": "“ in <research area>”, or nothing if unknown",
  "{research_area}": "the research area",
  "{university}": "the university",
};
const AIS = [
  ["ChatGPT", "https://chatgpt.com/"],
  ["Gemini", "https://gemini.google.com/"],
  ["Claude", "https://claude.ai/new"],
  ["Copilot", "https://copilot.microsoft.com/"],
  ["DeepSeek", "https://chat.deepseek.com/"],
];
const KIND_NAME = { cv: "CV", recommendation: "Recommendation letter", internship_report: "Internship report",
  offer_letter: "Offer letter", loi: "Letter of interest", proposal: "Research proposal", other: "Other document" };

export default function Emails() {
  const { me, refreshMe, go } = useApp();
  const [saved, setSaved] = useState(undefined);
  const [t, setT] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [dirty, setDirty] = useState(false);
  const editorRef = useRef();

  useEffect(() => { api("/templates").then((r) => { setSaved(r.templates); setT(r.templates); }); }, []);

  const notReady = !me.setup.cv || !me.setup.goal;
  const load = (templates, w = []) => {
    setT(templates); setWarnings(w); setDirty(true);
    requestAnimationFrame(() => editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  if (saved === undefined) return <Spinner />;

  return (
    <>
      <PageHead title="Your three emails">
        Write these once. Email 1 has three versions that take turns (professor 1 gets A, professor 2 gets B,
        professor 3 gets C, and so on), so Gmail doesn't see the same message going to everyone. Each professor's
        name and research area are filled in for you. Use any free AI to write them from your documents.
      </PageHead>

      {notReady ? (
        <div className="note warn">
          Upload your CV and choose your goal first.{" "}
          <button className="btn small" onClick={() => go("profile")}>Go to documents and goal</button>
        </div>
      ) : (
        <>
          <PromptStep />
          <PasteStep onParsed={load} />
        </>
      )}

      {t && (
        <div ref={editorRef}>
          <Editor t={t} setT={(x) => { setT(x); setDirty(true); }} warnings={warnings} dirty={dirty}
            onSaved={(x) => { setSaved(x); setT(x); setDirty(false); setWarnings([]); refreshMe(); }} />
        </div>
      )}

      {!notReady && !t && (
        <p className="muted small" style={{ marginTop: 16 }}>
          Prefer to write them yourself?{" "}
          <BasicButton onLoad={(x) => load(x, ["Fill in or delete every part in [square brackets], then save."])} />
        </p>
      )}
    </>
  );
}

function BasicButton({ onLoad, label = "Start from the blank templates" }) {
  const [busy, run] = useAction();
  const get = async () => { const r = await run(() => api("/templates/basic")); if (r) onLoad(r.templates); };
  return <button className="btn small" onClick={get} disabled={busy}>{label}</button>;
}

function PromptStep() {
  const [includeText, setIncludeText] = useState(false);
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const boxRef = useRef();

  useEffect(() => {
    setCopied(false);
    api(`/templates/prompt?include_text=${includeText}`).then((r) => { setData(r); setError(""); }).catch((e) => setError(e.message));
  }, [includeText]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.prompt);
    } catch {
      boxRef.current?.select();
      document.execCommand("copy");
    }
    setCopied(true);
  };

  return (
    <div className="panel stack">
      <h2>Step 1. Give this prompt and your documents to any AI</h2>
      {error && <div className="note bad">{error}</div>}
      {data && (
        <>
          <ol className="steps">
            <li><div>
              <b>Copy the prompt.</b>
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn primary" onClick={copy}>{copied ? "Copied" : "Copy prompt"}</button>
                <span className="muted small">{data.characters.toLocaleString()} characters</span>
              </div>
            </div></li>
            <li><div>
              <b>Open an AI chat</b> (a free account is enough):{" "}
              {AIS.map(([name, url], i) => (
                <React.Fragment key={name}>{i > 0 && ", "}<a href={url} target="_blank" rel="noreferrer">{name}</a></React.Fragment>
              ))}.
            </div></li>
            <li><div>
              <b>{includeText ? "Paste the prompt and send it." : "Attach these files, paste the prompt, and send it:"}</b>
              {!includeText && (
                <ul className="small" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {data.files.map((f) => (
                    <li key={f.id}>{KIND_NAME[f.kind]}: {f.filename}{" "}
                      <button className="btn ghost small" onClick={() => download(`/documents/${f.id}/file`, f.filename)}>Download</button>
                    </li>
                  ))}
                </ul>
              )}
            </div></li>
            <li><div><b>Copy the AI's whole answer</b> (most AIs show a copy button on the code block) and paste it in step 2 below.</div></li>
          </ol>
          <label className="check">
            <input type="checkbox" checked={includeText} onChange={(e) => setIncludeText(e.target.checked)} />
            My AI can't take file uploads: put the text of my documents inside the prompt instead
          </label>
          {includeText && data.unreadable.length > 0 && (
            <div className="note warn">No text could be read from {data.unreadable.join(", ")} (it may be a scanned image), so it isn't
              in the prompt. Attach that file to the AI chat yourself, or describe it in “Your plans” on the documents page.</div>
          )}
          <details>
            <summary className="small" style={{ cursor: "pointer" }}>See the prompt</summary>
            <textarea ref={boxRef} readOnly value={data.prompt} style={{ marginTop: 8, minHeight: 220, fontSize: "0.85rem" }} aria-label="Prompt" />
          </details>
        </>
      )}
    </div>
  );
}

function PasteStep({ onParsed }) {
  const [text, setText] = useState("");
  const [busy, run] = useAction();
  const [error, setError] = useState("");
  const parse = async () => {
    setError("");
    const r = await run(async () => {
      try { return await api("/templates/parse", { method: "POST", body: { text } }); }
      catch (e) { setError(e.message); throw e; }
    });
    if (r) onParsed(r.templates, r.warnings);
  };
  return (
    <div className="panel stack" style={{ marginTop: 16 }}>
      <h2>Step 2. Paste the AI's answer</h2>
      <textarea value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 160, fontSize: "0.9rem" }}
        placeholder={"@@@ SUBJECT A @@@\n...\n@@@ EMAIL 1A @@@\n...\n@@@ SUBJECT B @@@\n...\n@@@ EMAIL 1B @@@\n...\n(and C, then EMAIL 2, EMAIL 3)\n@@@ END @@@"} aria-label="The AI's answer" />
      {error && <div className="note bad">{error}</div>}
      <div className="row">
        <button className="btn primary" onClick={parse} disabled={busy || text.trim().length < 20}>Split into emails</button>
        <span className="muted small">Nothing is saved until you review the emails and press Save.</span>
      </div>
    </div>
  );
}

// A tab is "v0".."v2" (a version of email 1) or a reminder key
function Editor({ t, setT, warnings, dirty, onSaved }) {
  const { go } = useApp();
  const [tab, setTab] = useState("v0");
  const [busy, run] = useAction();
  const areaRef = useRef();
  const vi = tab.startsWith("v") ? Number(tab.slice(1)) : null;
  const versions = t.initial || [];
  const text = vi !== null ? versions[vi]?.body || "" : t[tab] || "";

  const setVersion = (i, patch) => setT({ ...t, initial: versions.map((v, j) => (j === i ? { ...v, ...patch } : v)) });
  const setText = (v) => (vi !== null ? setVersion(vi, { body: v }) : setT({ ...t, [tab]: v }));
  const addVersion = () => {
    const base = versions[versions.length - 1] || { subject: "", body: "" };
    setT({ ...t, initial: [...versions, { ...base }] });
    setTab(`v${versions.length}`);
  };
  const removeVersion = (i) => {
    if (versions.length <= 1 || !window.confirm(`Delete version ${VERSIONS[i]} of email 1?`)) return;
    setT({ ...t, initial: versions.filter((_, j) => j !== i) });
    setTab("v0");
  };
  const save = async () => { const r = await run(() => api("/templates", { method: "PUT", body: t }), "Emails saved"); if (r) onSaved(r.templates); };
  const insert = (ph) => {
    const el = areaRef.current;
    if (!el) return;
    const s = el.selectionStart ?? text.length;
    const e = el.selectionEnd ?? s;
    setText(text.slice(0, s) + ph + text.slice(e));
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = s + ph.length; });
  };
  const brackets = (txt) => /\[[^\]\n]{3,}\]/.test(txt || "");
  const when = vi !== null
    ? `Sent when you press Send.${versions.length > 1 ? ` Professors ${turns(vi, versions.length)} … in your sending order get version ${VERSIONS[vi]}.` : " Add a second or third version to lower the chance of landing in spam."}`
    : REMINDERS.find((x) => x.key === tab).when;

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <div className="panel-head">
        <h2>Step 3. Check and save</h2>
      </div>
      {warnings.length > 0 && <div className="stack" style={{ marginBottom: 14 }}>{warnings.map((w) => <div key={w} className="note warn">{w}</div>)}</div>}
      <div className="seg" role="tablist" style={{ marginBottom: 6 }}>
        {versions.map((v, i) => (
          <button key={i} role="tab" aria-selected={tab === `v${i}`} className={tab === `v${i}` ? "on" : ""} onClick={() => setTab(`v${i}`)}>
            Email 1{versions.length > 1 ? VERSIONS[i] : ""}{brackets(v.body) || !v.subject.trim() ? " •" : ""}
          </button>
        ))}
        {versions.length < 3 && <button type="button" onClick={addVersion} title="Add another version of email 1">+ Version</button>}
        {REMINDERS.map((x) => (
          <button key={x.key} role="tab" aria-selected={tab === x.key} className={tab === x.key ? "on" : ""} onClick={() => setTab(x.key)}>
            {x.name}{brackets(t[x.key]) ? " •" : ""}
          </button>
        ))}
      </div>
      <div className="row" style={{ marginBottom: 14 }}>
        <p className="muted small" style={{ flex: 1, minWidth: 220 }}>{when}</p>
        {vi !== null && versions.length > 1 && <button type="button" className="btn ghost small danger" onClick={() => removeVersion(vi)}>Delete version {VERSIONS[vi]}</button>}
      </div>
      <div className="editor">
        <div className="stack">
          {vi !== null ? (
            <label className="field">Subject{versions.length > 1 ? ` (version ${VERSIONS[vi]})` : ""}
              <input type="text" value={versions[vi]?.subject || ""} onChange={(e) => setVersion(vi, { subject: e.target.value })} />
            </label>
          ) : (
            <p className="small muted">Subject: “Re: ” + the subject that professor received (a reply in the same thread)</p>
          )}
          <label className="field">Email
            <textarea ref={areaRef} className="letter" value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <div>
            <p className="small muted" style={{ marginBottom: 6 }}>Click to insert. These are filled in for each professor:</p>
            <div className="chips">
              {Object.entries(HELP).map(([ph, d]) => (
                <button key={ph} type="button" className="chip" onClick={() => insert(ph)} title={d}>{ph}</button>
              ))}
            </div>
            <ul className="small muted" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {Object.entries(HELP).map(([ph, d]) => <li key={ph}><code>{ph}</code>: {d}</li>)}
            </ul>
          </div>
        </div>
        <Preview subject={vi !== null ? versions[vi]?.subject : versions[0]?.subject} body={text} reply={vi === null} />
      </div>
      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn primary" onClick={save} disabled={busy || !dirty}>Save emails</button>
        {dirty ? <span className="muted small">Not saved yet.</span> : <span className="muted small">Saved.</span>}
        <div className="spacer" />
        <button className="btn" onClick={() => go("send")} disabled={dirty}>Next: send</button>
      </div>
    </div>
  );
}

function turns(i, n) {
  return [0, 1, 2].map((k) => i + 1 + k * n).join(", ");
}

/** Fills placeholders in the browser so the preview works before saving. */
function fillLocal(text, p) {
  const area = (p.research_area || "").trim();
  const known = area && !["not specified", "n/a", "na", "-", "unknown"].includes(area.toLowerCase());
  const surname = (() => {
    const n = p.name.replace(/\(.*?\)/g, "").replace(/^(prof\.?|professor|dr\.?)\s+/i, "").trim().split(/\s+/);
    return n[n.length - 1] || p.name;
  })();
  return (text || "")
    .replaceAll("{professor}", `Professor ${surname}`)
    .replaceAll("{research_in}", known ? ` in ${area}` : "")
    .replaceAll("{research_area}", known ? area : "your research area")
    .replaceAll("{university}", p.university || "your university");
}

function Preview({ subject, body, reply }) {
  const [profs, setProfs] = useState([]);
  const [pid, setPid] = useState("");
  useEffect(() => { api("/professors").then(setProfs).catch(() => {}); }, []);
  const p = profs.find((x) => x.id === pid) || profs[0] || { name: "Prof. Example Chen", research_area: "Computer Vision" };
  const s = fillLocal(subject, p);
  return (
    <div className="preview-card">
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="small" style={{ fontWeight: 600 }}>Preview for</span>
        <select value={pid} onChange={(e) => setPid(e.target.value)} style={{ flex: 1, minWidth: 160 }} aria-label="Preview for professor">
          {profs.length === 0 && <option value="">An example professor</option>}
          {profs.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </div>
      <div className="preview-subject">{reply ? `Re: ${s.replace(/^(re:\s*)+/i, "")}` : s}</div>
      <div className="preview-letter">{fillLocal(body, p)}</div>
    </div>
  );
}
