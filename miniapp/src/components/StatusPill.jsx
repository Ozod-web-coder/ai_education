import { STATUS_LABELS } from "../constants";

export default function StatusPill({ status, label }) {
  return <span className={`pill pill-${status}`}>{label || STATUS_LABELS[status] || status}</span>;
}
