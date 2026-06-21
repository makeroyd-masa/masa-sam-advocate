import type { JSX } from "react";
import { useState } from "react";

import { Sheet } from "./Sheet";
import {
  GridIcon, ListIcon, SearchIcon, ShieldIcon, UserIcon, CheckIcon, InfoIcon,
} from "./icons";
import type { BillLineIn, InsuranceSituation, ProblemType } from "./types";

// dollars text → integer cents (null if blank/unparseable)
function toCents(s: string): number | null {
  const n = parseFloat((s || "").replace(/[$,\s]/g, ""));
  return Number.isFinite(n) ? Math.round(n * 100) : null;
}

// client-side code-type chip (mirrors app/codes.detect_code_type, best-effort)
function detect(code: string): string | null {
  const s = (code || "").trim().toUpperCase();
  if (/^[A-V]\d{4}$/.test(s)) return "HCPCS";
  if (/^\d{4}[FTUM]$/.test(s)) return "CPT";
  if (/^\d{5}$/.test(s)) return "CPT";
  return null;
}

const INTENTS: { pt: ProblemType; icon: JSX.Element; h: string; p: string }[] = [
  { pt: "explain", icon: <ListIcon />, h: "Understand my bill", p: "I'll explain the codes and the bottom line" },
  { pt: "error_overcharge", icon: <SearchIcon />, h: "Check it for errors & overcharges", p: "A line-by-line audit for money to dispute" },
  { pt: "denial_appeal", icon: <ShieldIcon />, h: "Appeal a denied ambulance claim", p: "Build an appeal grounded in coverage rules" },
];

// --- Frame 2: capability launcher -----------------------------------------
export function Launcher({ seedNote, onPick, onClose }:
  { seedNote?: string; onPick: (pt: ProblemType) => void; onClose: () => void }) {
  return (
    <Sheet subtitle="Your medical bill advocate" onClose={onClose}>
      {seedNote && (
        <div className="launch-ctx">
          <div className="e">From your claim</div>
          <div className="m">{seedNote}</div>
        </div>
      )}
      {INTENTS.map((it) => (
        <button className="cap-act" key={it.pt} onClick={() => onPick(it.pt)}>
          <span className="ic">{it.icon}</span>
          <div className="tx"><h5>{it.h}</h5><p>{it.p}</p></div>
          <span className="chev">›</span>
        </button>
      ))}
      <button className="cap-act" disabled>
        <span className="ic"><GridIcon /></span>
        <div className="tx"><h5>Check if you're covered</h5><p>Coverage questions</p></div>
        <span className="soon">Soon</span>
      </button>
      <button className="cap-act" disabled>
        <span className="ic"><UserIcon /></span>
        <div className="tx"><h5>Talk to a human advocate</h5><p>Hand off your case</p></div>
        <span className="soon">Soon</span>
      </button>
    </Sheet>
  );
}

// --- Frame 3: Stage 0 intent ----------------------------------------------
export function Stage0({ initial, onContinue, onClose, busy }:
  { initial?: ProblemType; onContinue: (pt: ProblemType) => void; onClose: () => void; busy: boolean }) {
  const [sel, setSel] = useState<ProblemType>(initial ?? "explain");
  return (
    <Sheet subtitle={`Step 1 of ${sel === "explain" ? 3 : 4}`} onClose={onClose}
      foot={<button className="pill purple" disabled={busy} onClick={() => onContinue(sel)}>Continue</button>}>
      <div className="sam-msg">Hi — I'll help you sort out this bill. <b>What would you like to do first?</b></div>
      {INTENTS.map((it) => (
        <button className={`choice ${sel === it.pt ? "sel" : ""}`} key={it.pt} onClick={() => setSel(it.pt)}>
          <span className="ic">{it.icon}</span>
          <div className="tx"><h5>{it.h}</h5><p>{it.p}</p></div>
          <span className="radio" />
        </button>
      ))}
    </Sheet>
  );
}

// --- Frame 4: Stage 1 insurance -------------------------------------------
const SITUATIONS: { v: InsuranceSituation; label: string }[] = [
  { v: "medicare_ffs", label: "Medicare" },
  { v: "medicare_advantage", label: "Medicare Advantage" },
  { v: "commercial_aca", label: "Commercial / ACA" },
  { v: "employer_erisa", label: "Employer plan" },
  { v: "medicaid", label: "Medicaid" },
  { v: "self_pay", label: "Self-pay" },
];
export function Stage1({ onContinue, onClose, busy, total }:
  { onContinue: (ins: InsuranceSituation, plan?: string) => void; onClose: () => void;
    busy: boolean; total: number }) {
  const [sel, setSel] = useState<InsuranceSituation>("medicare_ffs");
  const [plan, setPlan] = useState("");
  return (
    <Sheet subtitle={`Step 2 of ${total}`} onClose={onClose}
      foot={<button className="pill purple" disabled={busy} onClick={() => onContinue(sel, plan || undefined)}>Continue</button>}>
      <p className="q">How are you covered for this bill?</p>
      <div className="opt-grid">
        {SITUATIONS.map((s) => (
          <button className={`opt ${sel === s.v ? "sel" : ""}`} key={s.v} onClick={() => setSel(s.v)}>{s.label}</button>
        ))}
      </div>
      <div className="fld" style={{ marginTop: 16 }}>
        <label>Plan or member ID <span style={{ color: "var(--masa-harbor)", fontWeight: 400 }}>(optional)</span></label>
        <input className="input" value={plan} onChange={(e) => setPlan(e.target.value)}
          placeholder="If it's handy — I can pull plan terms" />
      </div>
      <p className="hint">This decides which rules and appeal pathways apply. Medicaid and self-pay take different routes.</p>
    </Sheet>
  );
}

// --- Frame 5: Stage 2 bill-level ------------------------------------------
export function Stage2({ onContinue, onClose, busy, ctaLabel, total }:
  { onContinue: (p: Record<string, unknown>) => void; onClose: () => void; busy: boolean;
    ctaLabel: string; total: number }) {
  const [f, setF] = useState({ provider: "", dos: "", billed: "", paid: "", owe: "", denial: "" });
  const up = (k: string, v: string) => setF((p) => ({ ...p, [k]: v }));
  const submit = () => onContinue({
    provider_name: f.provider || null,
    date_of_service_start: f.dos || null,
    total_billed_cents: toCents(f.billed),
    total_plan_paid_cents: toCents(f.paid),
    patient_responsibility_cents: toCents(f.owe),
    denial_codes: f.denial ? [f.denial] : [],
  });
  return (
    <Sheet subtitle={`Step 3 of ${total}`} onClose={onClose}
      foot={<button className="pill purple" disabled={busy} onClick={submit}>{ctaLabel}</button>}>
      <p className="q">Tell me about the bill</p>
      <div className="fld"><label>Provider</label>
        <input className="input" value={f.provider} onChange={(e) => up("provider", e.target.value)} placeholder="e.g. Mercy General Hospital" /></div>
      <div className="two">
        <div className="fld"><label>Date of service</label><input className="input" value={f.dos} onChange={(e) => up("dos", e.target.value)} placeholder="2026-03-04" /></div>
        <div className="fld"><label>Total billed</label><input className="input" value={f.billed} onChange={(e) => up("billed", e.target.value)} placeholder="$1,240.00" /></div>
      </div>
      <div className="two">
        <div className="fld"><label>Plan paid</label><input className="input" value={f.paid} onChange={(e) => up("paid", e.target.value)} placeholder="$0.00" /></div>
        <div className="fld"><label>You owe</label><input className="input" value={f.owe} onChange={(e) => up("owe", e.target.value)} placeholder="$1,240.00" /></div>
      </div>
      <div className="fld"><label>Any denial codes you can read? <span style={{ color: "var(--masa-harbor)", fontWeight: 400 }}>(optional)</span></label>
        <input className="input" value={f.denial} onChange={(e) => up("denial", e.target.value)} placeholder="e.g. CARC 50" /></div>
      <p className="hint">A denial code helps me route you to the right next step automatically.</p>
    </Sheet>
  );
}

// --- Frame 6: Stage 3 line-item (near-full) -------------------------------
type LineForm = { raw_code: string; units: string; billed: string; modifier: string; pos: string };
const blank: LineForm = { raw_code: "", units: "1", billed: "", modifier: "", pos: "" };
export function Stage3({ onCheck, onNoBill, onClose, busy }:
  { onCheck: (lines: BillLineIn[]) => void; onNoBill: () => void; onClose: () => void; busy: boolean }) {
  const [lines, setLines] = useState<LineForm[]>([{ ...blank }]);
  const up = (i: number, k: keyof LineForm, v: string) =>
    setLines((p) => p.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const submit = () => onCheck(lines.filter((l) => l.raw_code.trim()).map((l) => ({
    raw_code: l.raw_code.trim(),
    units: parseInt(l.units) || null,
    billed_charge_cents: toCents(l.billed),
    modifier: l.modifier || null,
    encounter_pos: l.pos.split(/\s|·/)[0] || null,
  })));
  return (
    <Sheet subtitle="Step 4 of 4 · one line at a time — partial is fine" tall onClose={onClose}
      title="Add your bill lines"
      foot={<button className="pill purple" disabled={busy} onClick={submit}>Check for errors & overcharges</button>}>
      {lines.map((l, i) => {
        const d = detect(l.raw_code);
        return (
          <div className="lineblk" key={i}>
            <div className="top"><b>Line {i + 1}</b>
              {d && <span className="detect"><CheckIcon /> {d} detected</span>}</div>
            <div className="fld"><input className="input" value={l.raw_code} onChange={(e) => up(i, "raw_code", e.target.value)} placeholder="Code (e.g. 99214)" /></div>
            <div className="two">
              <div className="fld"><label>Units</label><input className="input" value={l.units} onChange={(e) => up(i, "units", e.target.value)} /></div>
              <div className="fld"><label>Billed charge</label><input className="input" value={l.billed} onChange={(e) => up(i, "billed", e.target.value)} placeholder="$0.00" /></div>
            </div>
            <div className="two">
              <div className="fld"><label>Modifier</label><input className="input" value={l.modifier} onChange={(e) => up(i, "modifier", e.target.value)} placeholder="—" /></div>
              <div className="fld"><label>Place of service</label><input className="input" value={l.pos} onChange={(e) => up(i, "pos", e.target.value)} placeholder="11 · Office" /></div>
            </div>
          </div>
        );
      })}
      <button className="addline" onClick={() => setLines((p) => [...p, { ...blank }])}>＋ Add another line</button>
      <p className="hint">No itemized bill in front of you? <span className="link" onClick={onNoBill}>I can request one</span> instead.</p>
    </Sheet>
  );
}

// --- Frame 7: Stage 3-alt no-codes ----------------------------------------
export function Stage3Alt({ provider, onGenerate, onManual, onClose, busy }:
  { provider: string; onGenerate: () => void; onManual: () => void; onClose: () => void; busy: boolean }) {
  return (
    <Sheet subtitle="No itemized bill yet" onClose={onClose}
      foot={<>
        <button className="pill purple" disabled={busy} onClick={onGenerate}>Generate the request letter</button>
        <button className="escal" onClick={onManual}>Skip — I'll add lines manually</button>
      </>}>
      <div className="sam-msg">To audit a bill I need the itemized lines — most first bills only show a summary.
        <b> I'll write the provider a request for the itemized bill</b>, then pick this back up the moment it arrives.</div>
      <div className="recon" style={{ background: "var(--horizon-05)" }}>
        <div className="rr"><span>Sent to</span><b>{provider || "Your provider"}</b></div>
        <div className="rr"><span>Requesting</span><b>Itemized statement (CPT/HCPCS)</b></div>
      </div>
      <p className="hint">You'll get a notification when it's time to resume the error check. Nothing is lost — your case is saved.</p>
    </Sheet>
  );
}

// --- Frame 8: Stage 4 ambulance (near-full) -------------------------------
export function Stage4({ onReview, onClose, busy, error }:
  { onReview: (p: Record<string, unknown>) => void; onClose: () => void; busy: boolean; error?: string | null }) {
  const [f, setF] = useState({ code: "", mod: "", denial: "", date: "", origin: "", dest: "", miles: "", state: "" });
  const [emerg, setEmerg] = useState(true);
  const up = (k: string, v: string) => setF((p) => ({ ...p, [k]: v }));
  const submit = () => onReview({
    transport_hcpcs: f.code.trim(),
    transport_modifier: f.mod || null,
    denial_code: f.denial || null,
    denial_letter_date: f.date || null,
    is_emergency: emerg,
    origin: f.origin || null,
    destination: f.dest || null,
    loaded_miles: f.miles ? parseFloat(f.miles) : null,
    state: f.state || null,
  });
  return (
    <Sheet subtitle="Step 4 of 4 · for the appeal & dollar estimate" tall onClose={onClose}
      title="Your ambulance claim"
      foot={<button className="pill purple" disabled={busy} onClick={submit}>Review my appeal</button>}>
      {error && <div className="sam-error">{error}</div>}
      <div className="two">
        <div className="fld"><label>Transport code</label><input className="input" value={f.code} onChange={(e) => up("code", e.target.value)} placeholder="A0429" /></div>
        <div className="fld"><label>Modifier</label><input className="input" value={f.mod} onChange={(e) => up("mod", e.target.value)} placeholder="RH" /></div>
      </div>
      <div className="two">
        <div className="fld"><label>Denial code</label><input className="input" value={f.denial} onChange={(e) => up("denial", e.target.value)} placeholder="CARC 50" /></div>
        <div className="fld"><label>Denial letter date</label><input className="input" value={f.date} onChange={(e) => up("date", e.target.value)} placeholder="2026-03-20" /></div>
      </div>
      <div className="togrow"><span>Was it an emergency?</span>
        <button className={`toggle ${emerg ? "on" : ""}`} onClick={() => setEmerg((v) => !v)} aria-label="Emergency" /></div>
      <div className="two">
        <div className="fld"><label>Picked up at</label><input className="input" value={f.origin} onChange={(e) => up("origin", e.target.value)} placeholder="Origin" /></div>
        <div className="fld"><label>Taken to</label><input className="input" value={f.dest} onChange={(e) => up("dest", e.target.value)} placeholder="Destination" /></div>
      </div>
      <div className="two">
        <div className="fld"><label>Loaded miles <span style={{ color: "var(--masa-harbor)", fontWeight: 400 }}>(optional)</span></label>
          <input className="input" value={f.miles} onChange={(e) => up("miles", e.target.value)} placeholder="12" /></div>
        <div className="fld"><label>State</label><input className="input" value={f.state} onChange={(e) => up("state", e.target.value)} placeholder="CA" /></div>
      </div>
      <div className="honesty"><InfoIcon />
        <p>Loaded miles are the miles you were actually carried — often on the bill or run sheet. With it I give the full Medicare amount; without it, a floor.</p></div>
    </Sheet>
  );
}
