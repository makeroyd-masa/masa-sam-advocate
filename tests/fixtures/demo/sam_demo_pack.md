# SAM demo pack

Verified scenarios for a live walkthrough — **2–3 variants per core scenario** so you can vary the data run to run and it never looks like you're just echoing the form's example hints. Every code is a **real** `pilot.db` code, so it resolves in the running app; each case is a committed test fixture, so what you demo matches exactly what the engine is regression-tested against.

**To run:** open the app, tap **SAM** (bottom-right), pick any variant, and follow it top to bottom. Self-pay is used for overcharge cases (so the leverage call-to-action is actionable).

## 1. Flow 1 — Explain a denied bill

**1.1 Denied as not medically necessary**
- **In SAM:** *Understand my bill* → coverage *Medicare*.
- **Enter:** provider “Cedar Park Family Clinic”, total billed **$610.00**, you owe **$610.00**, denial **CARC 50**.
- **SAM shows:** you owe **$610.00**; the denial looks **appealable**, with the reason in plain English and a next step.
- _fixture demo_flow1_denied_001_

**1.2 Denied for missing prior authorization**
- **In SAM:** *Understand my bill* → coverage *Medicare Advantage*.
- **Enter:** provider “Riverside Medical Center”, total billed **$2,480.00**, you owe **$2,480.00**, denial **CARC 197**.
- **SAM shows:** you owe **$2,480.00**; the denial looks **appealable**, with the reason in plain English and a next step.
- _fixture demo_flow1_denied_002_

**1.3 Denied on a national coverage policy (NCD)**
- **In SAM:** *Understand my bill* → coverage *Medicare*.
- **Enter:** provider “St. Luke's Regional”, total billed **$940.00**, you owe **$940.00**, denial **RARC N386**.
- **SAM shows:** you owe **$940.00**; the denial looks **appealable**, with the reason in plain English and a next step.
- _fixture demo_flow1_denied_003_

## 2. Flow 1 — Cost-share check (does your share add up?)

**2.1 Hospital share that doesn't add up**
- **In SAM:** *Understand my bill* → coverage *Employer plan*.
- **Enter:** provider “Orlando Health Medical Center”, then the cost-share split from your EOB.
- **SAM shows:** the parts of your share (copay $100.00 + deductible $200.38 + coinsurance $1,125.07 = **$1,425.45**) don't add up to the **$1,485.45** you owe — worth a closer look.
- _fixture demo_costshare_001_

**2.2 Coinsurance that doesn't match the plan rate**
- **In SAM:** *Understand my bill* → coverage *Commercial / ACA*.
- **Enter:** provider “Lakeside Imaging”, then the cost-share split from your EOB.
- **SAM shows:** the **$1,500.00** coinsurance doesn't match your 20% rate on the allowed amount — worth a closer look.
- _fixture demo_costshare_002_

**2.3 A not-covered charge to question**
- **In SAM:** *Understand my bill* → coverage *Employer plan*.
- **Enter:** provider “Summit Surgical Center”, then the cost-share split from your EOB.
- **SAM shows:** a **$180.00** not-covered amount — a coverage question to appeal, not a pricing issue.
- _fixture demo_costshare_003_

## 3. Flow 2 — Unbundling (one service includes another)

**3.1 Comprehensive + basic metabolic panel**
- **In SAM:** *Check it for errors & overcharges* → coverage *Employer plan*.
- **Enter lines:** **80053** ×1 @ $118.00; **80048** ×1 @ $92.00.
- **SAM shows:** **$92.00** recoverable billing error.
- _fixture demo_flow2_unbundling_001_

**3.2 Lipid panel + standalone cholesterol**
- **In SAM:** *Check it for errors & overcharges* → coverage *Employer plan*.
- **Enter lines:** **80061** ×1 @ $86.00; **82465** ×1 @ $44.00.
- **SAM shows:** **$44.00** recoverable billing error.
- _fixture demo_flow2_unbundling_002_

**3.3 CBC with differential + CBC**
- **In SAM:** *Check it for errors & overcharges* → coverage *Employer plan*.
- **Enter lines:** **85025** ×1 @ $38.00; **85027** ×1 @ $22.00.
- **SAM shows:** **$22.00** recoverable billing error.
- _fixture demo_flow2_unbundling_003_

## 4. Flow 2 — Quantity over the daily cap

**4.1 Lipid panel billed 3× (daily max 1)**
- **In SAM:** *Check it for errors & overcharges* → coverage *Employer plan*.
- **Enter lines:** **80061** ×3 @ $120.00.
- **SAM shows:** **$80.00** recoverable billing error.
- _fixture demo_flow2_mue_001_

**4.2 CBC billed 4× (daily max 2)**
- **In SAM:** *Check it for errors & overcharges* → coverage *Employer plan*.
- **Enter lines:** **85025** ×4 @ $120.00.
- **SAM shows:** **$60.00** recoverable billing error.
- _fixture demo_flow2_mue_002_

**4.3 Blood draw billed 5× (daily max 2)**
- **In SAM:** *Check it for errors & overcharges* → coverage *Employer plan*.
- **Enter lines:** **36415** ×5 @ $70.00.
- **SAM shows:** **$42.00** recoverable billing error.
- _fixture demo_flow2_mue_003_

## 5. Flow 2 — Overcharge vs Medicare (negotiation leverage)

**5.1 Level-5 office visit at ~6× Medicare**
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **99215** ×1 @ $1,068.42 (POS 11).
- **SAM shows:** a line at **≈6.0× the Medicare benchmark** ($178.07).
- _fixture demo_flow2_overcharge_001_

**5.2 New-patient visit at ~4× Medicare**
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **99204** ×1 @ $661.16 (POS 11).
- **SAM shows:** a line at **≈4.0× the Medicare benchmark** ($165.29).
- _fixture demo_flow2_overcharge_002_

**5.3 Lesion removal at ~5.5× Medicare**
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **17000** ×1 @ $370.59 (POS 11).
- **SAM shows:** a line at **≈5.5× the Medicare benchmark** ($67.38).
- _fixture demo_flow2_overcharge_003_

## 6. Flow 2 — Error + overcharge together (two-tier card)

**6.1 Unbundled labs + a ~6× office visit**
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **80053** ×1 @ $118.00; **80048** ×1 @ $92.00; **99215** ×1 @ $1,068.42 (POS 11).
- **SAM shows:** **$92.00** recoverable billing error and a line at **≈6.0× the Medicare benchmark** ($178.07).
- _fixture demo_flow2_two_tier_001_

**6.2 Unbundled lipid panel + a ~4.5× visit**
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **80061** ×1 @ $86.00; **82465** ×1 @ $44.00; **99204** ×1 @ $743.80 (POS 11).
- **SAM shows:** **$44.00** recoverable billing error and a line at **≈4.5× the Medicare benchmark** ($165.29).
- _fixture demo_flow2_two_tier_002_

**6.3 Unbundled CBC + a ~5.5× procedure**
- **In SAM:** *Check it for errors & overcharges* → coverage *Self-pay*.
- **Enter lines:** **85025** ×1 @ $38.00; **85027** ×1 @ $22.00; **17000** ×1 @ $370.59 (POS 11).
- **SAM shows:** **$22.00** recoverable billing error and a line at **≈5.5× the Medicare benchmark** ($67.38).
- _fixture demo_flow2_two_tier_003_

## 7. Flow 3 — Ground ambulance appeal

**7.1 ALS1-emergency, Texas, 18 mi (Medicare)**
- **In SAM:** *Appeal a denied ambulance claim* → coverage *Medicare*.
- **Enter:** transport **A0427**, denial **CARC 50**, emergency **yes**, **18** loaded miles, state **TX**.
- **SAM shows:** Medicare reasonable amount **≈ $705.93** (base $541.23 + 18 mi × $9.15); appeal **Redetermination** (NCD 10.1 binding); ground-ambulance honesty note.
- _fixture demo_flow3_ground_001_

**7.2 ALS2, New York, 9 mi (Medicare Advantage)**
- **In SAM:** *Appeal a denied ambulance claim* → coverage *Medicare Advantage*.
- **Enter:** transport **A0433**, denial **CARC 197**, emergency **yes**, **9** loaded miles, state **NY**.
- **SAM shows:** Medicare reasonable amount **≈ $955.82** (base $873.47 + 9 mi × $9.15); appeal **MA Equivalent Process** (NCD 10.1 binding); ground-ambulance honesty note.
- _fixture demo_flow3_ground_002_

**7.3 Specialty care transport, Florida, 25 mi (Commercial)**
- **In SAM:** *Appeal a denied ambulance claim* → coverage *Commercial / ACA*.
- **Enter:** transport **A0434**, denial **CARC 40**, emergency **yes**, **25** loaded miles, state **FL**.
- **SAM shows:** Medicare reasonable amount **≈ $1,152.27** (base $923.52 + 25 mi × $9.15); appeal **Internal Appeal** (NCD 10.1 persuasive); ground-ambulance honesty note.
- _fixture demo_flow3_ground_003_

## 8. Flow 3 — Air ambulance (routes to a human)

**8.1 Rotary-wing air transport**
- **In SAM:** *Appeal a denied ambulance claim* → enter transport **A0431**.
- **SAM shows:** air ambulance is handled differently — it routes to a **human advocate** and makes no automated surprise-billing (NSA) claims.
- _fixture demo_flow3_air_001_

**8.2 Fixed-wing air mileage**
- **In SAM:** *Appeal a denied ambulance claim* → enter transport **A0435**.
- **SAM shows:** air ambulance is handled differently — it routes to a **human advocate** and makes no automated surprise-billing (NSA) claims.
- _fixture demo_flow3_air_002_

**8.3 Fixed-wing air transport**
- **In SAM:** *Appeal a denied ambulance claim* → enter transport **A0430**.
- **SAM shows:** air ambulance is handled differently — it routes to a **human advocate** and makes no automated surprise-billing (NSA) claims.
- _fixture demo_flow3_air_003_
