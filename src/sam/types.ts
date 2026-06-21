// Types mirroring the FastAPI responses (app/schemas.py, app/answer_card.py).

export type ProblemType = "explain" | "error_overcharge" | "denial_appeal";
export type InsuranceSituation =
  | "medicare_ffs" | "medicare_advantage" | "commercial_aca"
  | "employer_erisa" | "medicaid" | "self_pay";

export interface CaseState {
  case_id: number;
  member_ref: string;
  problem_type: string | null;
  insurance_situation: string | null;
  active_flow: string | null;
  current_stage: string;
  status: string;
  entry_point: string | null;
  seed_intent: string | null;
}

export interface StageResult {
  case: CaseState;
  next_stage: string;
  message: string | null;
  routed_to_handoff: boolean;
  needs_clarification: boolean;
  detail: Record<string, unknown> | null;
}

export interface Citation {
  source_type: string;
  source_ref: string;
  display_text: string | null;
}
export interface Finding {
  title: string;
  text: string;
  tone: "error" | "leverage" | "ok" | "neutral";
  citation: Citation | null;
}
export interface ReconRow { label: string; cents: number; is_total: boolean; }
export interface Pathway { label: string; detail: string; caveat: string | null; }
export interface HonestyNode { text: string; }

export interface AnswerCard {
  flow: string;
  headline: string;
  eyebrow: string | null;
  number_cents: number | null;
  number_label: string | null;
  number_display: string | null;
  number2_display: string | null;
  number2_label: string | null;
  reconciliation: ReconRow[];
  findings: Finding[];
  next_action: string | null;
  secondary_action: string | null;
  framing_note: string | null;
  honesty_node: HonestyNode | null;
  pathway: Pathway | null;
  escalation_offered: boolean;
  gated_content_note: string | null;
}

export interface FlowResult {
  card_id: number;
  card: AnswerCard;
  savings?: { recoverable_cents: number; leverage_line_count: number };
}

export interface BillLineIn {
  raw_code: string;
  units?: number | null;
  billed_charge_cents?: number | null;
  modifier?: string | null;
  encounter_pos?: string | null;
}
