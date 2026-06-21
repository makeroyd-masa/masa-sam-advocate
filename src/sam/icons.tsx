// Small inline SVG icon set (stroke = currentColor) used across SAM surfaces.
import type { JSX } from "react";

type P = { size?: number };
const svg = (children: JSX.Element, size = 22) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={2}
       strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);

export const SparkIcon = ({ size }: P) =>
  <svg viewBox="0 0 24 24" width={size ?? 21} height={size ?? 21} fill="none" stroke="#fff" strokeWidth={2}>
    <path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z" /><circle cx="18" cy="17" r="2.4" />
  </svg>;
export const ListIcon = ({ size }: P) => svg(<><path d="M4 5h16M4 12h16M4 19h10" /></>, size);
export const SearchIcon = ({ size }: P) => svg(<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></>, size);
export const ShieldIcon = ({ size }: P) => svg(<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />, size);
export const GridIcon = ({ size }: P) => svg(<><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M9 9h6v6H9z" /></>, size);
export const UserIcon = ({ size }: P) => svg(<><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></>, size);
export const InfoIcon = ({ size }: P) => svg(<><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></>, size);
export const CheckIcon = ({ size }: P) =>
  <svg viewBox="0 0 24 24" width={size ?? 11} height={size ?? 11} fill="currentColor"><path d="M9 16.2l-3.5-3.5L4 14.2 9 19l11-11-1.5-1.5z" /></svg>;
