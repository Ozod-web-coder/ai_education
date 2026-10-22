import { BookOpen, CalendarDays, Copy, Phone, Send } from "lucide-react";
import { formatDate, initials } from "../format";
import StatusPill from "./StatusPill";

export default function LeadCard({ lead, onOpen }) {
  return (
    <button className="card lead-card" onClick={() => onOpen(lead.id)}>
      <span className="avatar" aria-hidden="true">
        {initials(lead.name)}
      </span>
      <span className="lead-main">
        <span className="lead-top">
          <span className="lead-name">{lead.name || "Без имени"}</span>
          <StatusPill status={lead.status} label={lead.status_display} />
        </span>
        <span className="lead-line">
          <Phone size={14} aria-hidden="true" />
          {lead.phone || "Телефон не указан"}
        </span>
        <span className="lead-line">
          <Send size={14} aria-hidden="true" />
          {lead.telegram_username ? `@${lead.telegram_username}` : "Без username"}
        </span>
        <span className="lead-meta">
          <span className="chip-soft">
            <BookOpen size={13} aria-hidden="true" />
            {lead.course || "Курс не выбран"}
          </span>
          <span className="lead-date">
            <CalendarDays size={13} aria-hidden="true" />
            {formatDate(lead.created_at)}
          </span>
          {lead.duplicate_count > 0 && (
            <span className="chip-warn" title="Этот человек уже оставлял заявку">
              <Copy size={13} aria-hidden="true" />
              Повтор
            </span>
          )}
        </span>
      </span>
    </button>
  );
}
