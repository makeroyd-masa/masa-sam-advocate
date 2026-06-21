import type { ReactNode } from "react";
import { SparkIcon } from "./icons";

// The bottom-sheet shell: dim backdrop, handle, SAM header, scrollable body,
// optional sticky footer. mid (~78%) for light stages, tall (~94%) for heavy
// entry and answer cards (PRD §1.3 surface behavior).
export function Sheet(props: {
  subtitle: string;
  tall?: boolean;
  onClose: () => void;
  children: ReactNode;
  foot?: ReactNode;
  title?: string;
}) {
  const { subtitle, tall, onClose, children, foot, title = "SAM" } = props;
  return (
    <>
      <div className="dim" onClick={onClose} />
      <div className={`sheet ${tall ? "tall" : "mid"}`} role="dialog" aria-modal="true">
        <div className="handle" />
        <div className="sheet-head">
          <div className="sam-badge"><SparkIcon /></div>
          <div className="sam-id">
            <div className="n">{title}</div>
            <div className="r">{subtitle}</div>
          </div>
          <button className="x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="sheet-body">{children}</div>
        {foot && <div className="sheet-foot">{foot}</div>}
      </div>
    </>
  );
}
