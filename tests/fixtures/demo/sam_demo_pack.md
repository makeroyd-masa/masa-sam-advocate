# SAM demo pack

Curated, verified scenarios for a live walkthrough. Every code is a **real** code from `pilot.db`, so it resolves in the running app — these are genuine bills engineered to trigger a finding, not junk. Each card is traceable to a committed test fixture, so what you demo matches exactly what the engine is regression-tested against.

**To run:** open the app, tap **SAM** (bottom-right), and follow a card top to bottom.

## 1. Explain a denied bill (Flow 1)
- **In SAM:** *Understand my bill* → coverage *Medicare*.
- **Enter:** provider “Mercy General Hospital”, total billed **$1,240.00**, you owe **$1,240.00**, denial code **CARC 50**.
- **SAM shows:** the charge was denied as *not medically necessary* and that looks **appealable**; you owe **$1,240.00**; offers to check for errors / start an appeal.
- _verified fixture: demo_flow1_denied_001_

## 2. Find a billing error — unbundled lab panel (Flow 2)
- **In SAM:** *Check it for errors & overcharges* → coverage *Medicare*.
- **Enter lines:** **80053** ×1 @ $120.00 (comprehensive metabolic panel); **80048** ×1 @ $95.00 (basic metabolic panel).
- **SAM shows:** **$95.00** likely billing error — 80048 is bundled into 80053 (NCCI, never allowed together); ask to have it removed.
- _verified fixture: demo_flow2_unbundling_001_

## 3. Find a billing error — units over the daily cap (Flow 2)
- **In SAM:** *Check it for errors & overcharges* → *Medicare*.
- **Enter line:** **80053** ×**3** @ $120.00.
- **SAM shows:** **$80.00** likely error — Medicare's daily maximum for 80053 is 1 unit; the 2 excess units can be questioned.
- _verified fixture: demo_flow2_mue_001_

## 4. Flag an overcharge — ×-Medicare leverage (Flow 2)
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter line:** **99214** ×1 @ **$761.94**, place of service **11 (office)**.
- **SAM shows:** this line is **≈6.0× the Medicare benchmark** ($126.99) — a strong basis to negotiate a reduction (framed as leverage, not “owed”).
- _verified fixture: demo_flow2_overcharge_001_

## 5. The full error + overcharge card (Flow 2, two tiers)
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **80053** @ $120.00; **80048** @ $95.00; **99214** @ $761.94 (POS 11).
- **SAM shows two honest tiers:** **$95.00 recoverable error** (unbundling) **and ≈6.0× over benchmark** (negotiation leverage).
- _verified fixture: demo_flow2_two_tier_001_

## 6. Build a ground-ambulance appeal (Flow 3)
- **In SAM:** *Appeal a denied ambulance claim* → coverage *Medicare*.
- **Enter:** transport **A0429** (BLS-emergency), denial **CARC 50**, emergency **yes**, **12** loaded miles, state **CA**.
- **SAM shows:** Medicare reasonable amount **≈ $607.16** (base $497.36 + 12 mi × $9.15); appeal **Level 1 — Redetermination** with deadline; ground-ambulance honesty note (not NSA).
- _verified fixture: demo_flow3_ground_001_

## 7. Air ambulance routes to a human advocate (Flow 3 guardrail)
- **In SAM:** *Appeal a denied ambulance claim* → enter transport **A0430** (fixed-wing air).
- **SAM shows:** air ambulance is handled differently and may involve federal protections — it hands off to a **human advocate** and makes no automated surprise-billing claims.
- _verified fixture: demo_flow3_air_001_
