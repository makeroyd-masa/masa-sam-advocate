import { SamApp } from "./sam/SamApp";
import "./styles/sam.css";

// SAM is surfaced over the host MASA app surface (Claims) via a persistent FAB —
// no dedicated page (PRD §1.3). The whole experience lives in SamApp.
export default function App() {
  return <SamApp />;
}
