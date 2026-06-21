import { useState } from "react";

import { AnswerCardView } from "./AnswerCardView";
import { Sheet } from "./Sheet";
import { SparkIcon, UserIcon } from "./icons";
import {
  Launcher, Stage0, Stage1, Stage2, Stage3, Stage3Alt, Stage4,
} from "./Stages";
import { api } from "./api";
import type { AnswerCard, BillLineIn, InsuranceSituation, ProblemType } from "./types";

type Step =
  | "closed" | "launcher" | "stage0" | "stage1" | "stage2"
  | "stage3" | "stage3alt" | "stage4" | "card" | "info";

const SEED_NOTE = "Want me to look at this ambulance claim? I can explain it, check it for errors, or help you appeal a denial.";

export function SamApp() {
  const [step, setStep] = useState<Step>("closed");
  const [caseId, setCaseId] = useState<number | null>(null);
  const [intent, setIntent] = useState<ProblemType>("explain");
  const [provider, setProvider] = useState("");
  const [card, setCard] = useState<AnswerCard | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stage4Error, setStage4Error] = useState<string | null>(null);
  const [info, setInfo] = useState<{ title: string; body: string }>({ title: "", body: "" });

  const reset = () => {
    setStep("closed"); setCaseId(null); setCard(null); setError(null); setStage4Error(null);
  };

  // wrap an async action with busy + error handling
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };

  const openSam = () => run(async () => {
    const r = await api.createCase("claims", "ambulance_claim");
    setCaseId(r.case.case_id);
    setStep("launcher");
  });

  const pickIntent = (pt: ProblemType) => { setIntent(pt); setStep("stage0"); };

  const continue0 = (pt: ProblemType) => run(async () => {
    await api.stage0(caseId!, pt); setIntent(pt); setStep("stage1");
  });

  const continue1 = (ins: InsuranceSituation, plan?: string) => run(async () => {
    const r = await api.stage1(caseId!, ins, plan);
    if (r.routed_to_handoff) { showInfo("Routed to a human advocate", r.message ?? ""); return; }
    setStep("stage2");
  });

  const continue2 = (payload: Record<string, unknown>) => run(async () => {
    setProvider((payload.provider_name as string) || "");
    const r = await api.stage2(caseId!, payload);
    if (r.next_stage === "analysis") { await runFlow("flow1"); }
    else if (r.next_stage === "stage3_lines") setStep("stage3");
    else if (r.next_stage === "stage4_ambulance") setStep("stage4");
  });

  const check3 = (lines: BillLineIn[]) => run(async () => {
    await api.stage3(caseId!, lines); await runFlow("flow2");
  });

  const review4 = (payload: Record<string, unknown>) => run(async () => {
    setStage4Error(null);
    const r = await api.stage4(caseId!, payload);
    if (r.routed_to_handoff) { showInfo("Air ambulance — handed off", r.message ?? ""); return; }
    if (r.needs_clarification) { setStage4Error(r.message ?? "Please check the transport code."); return; }
    await runFlow("flow3");
  });

  const generate3alt = () => run(async () => {
    await api.stage3alt(caseId!);
    showInfo("Itemized bill requested",
      "We'll request the itemized bill and resume the error check the moment it arrives. Your case is saved.");
  });

  const runFlow = async (which: "flow1" | "flow2" | "flow3") => {
    const r = which === "flow1" ? await api.flow1(caseId!)
      : which === "flow2" ? await api.flow2(caseId!) : await api.flow3(caseId!);
    setCard(r.card); setStep("card");
  };

  const onCardPrimary = () => {
    if (!card) return;
    if (card.flow === "flow1_explain") { run(async () => { await api.acceptCheckpoint(caseId!); setStep("stage3"); }); return; }
    if ((card.next_action || "").toLowerCase().includes("human")) { onEscalate(); return; }
    if (card.flow === "flow2_error") {
      showInfo("Correction request prepared",
        "We've drafted a correction request for the flagged lines. An advocate reviews it before anything is sent.");
    } else {
      showInfo("Appeal letter prepared",
        "Your appeal package is drafted. Appeal letters are reviewed by our team before they're finalized and sent.");
    }
  };

  const onEscalate = () => run(async () => {
    await api.handoff(caseId!);
    showInfo("A human advocate will reach out",
      "Your case has been handed to an in-house advocate who will follow up with you.");
  });

  const showInfo = (title: string, body: string) => { setInfo({ title, body }); setStep("info"); };

  return (
    <div className="sam-root">
      <HostClaims onOpen={openSam} />

      {step === "launcher" && <Launcher seedNote={SEED_NOTE} onPick={pickIntent} onClose={reset} />}
      {step === "stage0" && <Stage0 initial={intent} onContinue={continue0} onClose={reset} busy={busy} />}
      {step === "stage1" && <Stage1 onContinue={continue1} onClose={reset} busy={busy} />}
      {step === "stage2" && (
        <Stage2 onContinue={continue2} onClose={reset} busy={busy}
          ctaLabel={intent === "explain" ? "Explain my bill" : intent === "denial_appeal" ? "Continue" : "Next"} />
      )}
      {step === "stage3" && <Stage3 onCheck={check3} onNoBill={() => setStep("stage3alt")} onClose={reset} busy={busy} />}
      {step === "stage3alt" && (
        <Stage3Alt provider={provider} onGenerate={generate3alt} onManual={() => setStep("stage3")}
          onClose={reset} busy={busy} />
      )}
      {step === "stage4" && <Stage4 onReview={review4} onClose={reset} busy={busy} error={stage4Error} />}
      {step === "card" && card && (
        <Sheet subtitle={flowLabel(card.flow)} tall onClose={reset}>
          {error && <div className="sam-error">{error}</div>}
          <AnswerCardView card={card} onPrimary={onCardPrimary} onEscalate={onEscalate} />
        </Sheet>
      )}
      {step === "info" && (
        <Sheet subtitle="SAM" onClose={reset}
          foot={<button className="pill purple" onClick={reset}>Done</button>}>
          <div className="handoff-wrap">
            <div className="big"><UserIcon /></div>
            <h2 className="ac-headline" style={{ textAlign: "center" }}>{info.title}</h2>
            <p style={{ color: "var(--masa-harbor)", fontSize: 13, lineHeight: 1.5 }}>{info.body}</p>
          </div>
        </Sheet>
      )}

      {error && step !== "card" && step !== "closed" && (
        <div className="dim"><div className="sheet mid"><div className="sheet-body">
          <div className="sam-error">{error}</div>
          <button className="pill ghost" onClick={reset}>Close</button>
        </div></div></div>
      )}
    </div>
  );
}

function flowLabel(flow: string): string {
  return flow === "flow1_explain" ? "Flow 1 · Bill explanation"
    : flow === "flow2_error" ? "Flow 2 · Error & overcharge check"
    : "Flow 3 · Ambulance appeal";
}

// --- Frame 1: host Claims screen with the contextual FAB -------------------
function HostClaims({ onOpen }: { onOpen: () => void }) {
  return (
    <>
      <div className="app-head">
        <div className="row">
          <img className="mark" src="/mark-white.svg" alt="MASA" />
          <UserIcon />
        </div>
        <div className="app-title">Claims</div>
      </div>
      <div className="app-body">
        <div className="lbl">What to know</div>
        <div className="tint"><h4>Should I file?</h4>
          <p>You have travel coverage enabled. Learn what to do in an emergency.</p></div>
        <button className="pill purple" style={{ margin: "4px 0 16px" }}>File a new claim</button>
        <div className="lbl">Open claims</div>
        <div className="host-card"><div><h4>Air transport claim</h4>
          <p>Submitted 02/24 · #1234 · In progress</p></div><span className="chev">›</span></div>
      </div>
      <div className="ctx-bubble">Need help with claim <b>#1234</b>? I can read it and check for issues.</div>
      <button className="fab" onClick={onOpen}>
        <span className="ring"><SparkIcon size={18} /></span><span className="ft">SAM</span>
      </button>
    </>
  );
}
