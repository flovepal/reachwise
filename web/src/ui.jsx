import { BRAND } from "./brand.js";
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

export function Logo() {
  // Mark: a line reaching from you (white dot) to the person you're writing to (saffron dot)
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="16" fill="var(--primary)" />
      <path d="M19 45C19 30 30 19 45 19" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
      <path d="M19 45C27 45 33 41 36 35" fill="none" stroke="#fff" strokeOpacity=".45" strokeWidth="4" strokeLinecap="round" />
      <circle cx="19" cy="45" r="6" fill="#fff" />
      <circle cx="45" cy="19" r="7" fill="var(--accent)" />
    </svg>
  );
}

export function Brand({ className = "brand" }) {
  return (
    <div className={className}>
      <Logo />
      <div><span className="name">{BRAND.name}</span><span className="module">{BRAND.module}</span></div>
    </div>
  );
}

export function PageHead({ title, children }) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </div>
  );
}

export function useToast() {
  const [toast, setToast] = useState(null);
  const timer = useRef();
  const show = useCallback((text, bad = false) => {
    clearTimeout(timer.current);
    setToast({ text, bad });
    timer.current = setTimeout(() => setToast(null), bad ? 6000 : 3500);
  }, []);
  const el = toast ? <div role="status" className={`toast ${toast.bad ? "bad" : ""}`}>{toast.text}</div> : null;
  return [show, el];
}

/** Run an async action with a busy flag and error toast. */
export function useAction() {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn, okText) => {
    setBusy(true);
    try {
      const r = await fn();
      if (okText) toast(okText);
      return r;
    } catch (e) {
      toast(e.message, true);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return [busy, run];
}

export function usePoll(fn, ms, active = true) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms, active]);
}

export function Spinner() {
  return <span className="spin" aria-hidden="true" />;
}

export const LABEL_NAMES = {
  interview: "Interview / meeting",
  interested: "Interested",
  needs_info: "Asked for more info",
  redirect: "Pointed elsewhere",
  rejection: "Declined",
  auto_reply: "Out of office",
  bounced: "Didn't arrive",
  other: "Other reply",
};

export const KIND_NAMES = { initial: "First email", reminder1: "Reminder 1", reminder2: "Reminder 2" };
