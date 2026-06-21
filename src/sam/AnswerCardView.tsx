import type { AnswerCard } from "./types";

// Renders the §7 answer card for any flow (frames 9–11). Two-tier num-split for
// Flow 2; single num-card for Flow 1 (you owe) / Flow 3 (reasonable amount).
export function AnswerCardView({
  card,
  onPrimary,
  onEscalate,
}: {
  card: AnswerCard;
  onPrimary: () => void;
  onEscalate: () => void;
}) {
  const isTwoTier = card.flow === "flow2_error" && (card.number_display || card.number2_display);

  return (
    <>
      {card.eyebrow && <span className="ac-eyebrow">{card.eyebrow}</span>}
      <h2 className="ac-headline">{card.headline}</h2>

      {isTwoTier ? (
        <div className="num-split">
          {card.number_display && (
            <div className="ns-err">
              <div className="k">LIKELY ERROR</div>
              <div className="v">{card.number_display}</div>
              <div className="s">{card.number_label}</div>
            </div>
          )}
          {card.number2_display && (
            <div className="ns-lev">
              <div className="k">OVER BENCHMARK</div>
              <div className="v">{card.number2_display}</div>
              <div className="s">{card.number2_label}</div>
            </div>
          )}
        </div>
      ) : (
        card.number_display && (
          <div className="num-card">
            <div className="k">{(card.number_label || "").toUpperCase()}</div>
            <div className="v">{card.number_display}</div>
          </div>
        )
      )}

      {card.reconciliation.length > 0 && (
        <div className="recon">
          {card.reconciliation.map((r, i) => (
            <div key={i} className={`rr ${r.is_total ? "tot" : ""}`}>
              <span>{r.label}</span>
              <b>{`$${(r.cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}</b>
            </div>
          ))}
        </div>
      )}

      {card.findings.length > 0 && (
        <div className="why">
          <h6>Why</h6>
          {card.findings.map((f, i) => (
            <div className="find" key={i}>
              <span className={`b ${f.tone}`} />
              <div className="c">
                <h6>{f.title}</h6>
                <p>{f.text}</p>
                {f.citation && (
                  <span className="cite">{f.citation.display_text || f.citation.source_ref}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {card.pathway && (
        <div className="pathway">
          <p className="pl">{card.pathway.label}</p>
          <p className="dl">{card.pathway.detail}</p>
          {card.pathway.caveat && <p className="caveat">{card.pathway.caveat}</p>}
        </div>
      )}

      {card.honesty_node && (
        <div className="honesty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" />
          </svg>
          <p>{card.honesty_node.text}</p>
        </div>
      )}

      <div className="sheet-foot" style={{ borderTop: "none", padding: "8px 0 0" }}>
        {card.next_action && (
          <button className="pill purple" onClick={onPrimary}>{card.next_action}</button>
        )}
        {card.framing_note && <div className="frame-note">{card.framing_note}</div>}
        {card.escalation_offered && (
          <button className="escal" onClick={onEscalate}>Talk to a human advocate →</button>
        )}
      </div>
    </>
  );
}
