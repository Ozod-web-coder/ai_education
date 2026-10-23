import { Loader2 } from "lucide-react";

/** Линейная иллюстрация в стиле референса: чёрный контур и оранжевый акцент. */
export function Illustration() {
  return (
    <svg className="illustration" viewBox="0 0 160 120" fill="none" aria-hidden="true">
      <path d="M12 108h136" stroke="#111" strokeWidth="2.5" strokeLinecap="round" />
      <rect x="46" y="14" width="68" height="86" rx="10" fill="#fff" stroke="#111" strokeWidth="2.5" />
      <rect x="64" y="8" width="32" height="14" rx="6" fill="#fff" stroke="#111" strokeWidth="2.5" />
      <circle cx="64" cy="46" r="6" fill="#F26A0F" />
      <path d="M78 46h22M58 66h42M58 80h30" stroke="#111" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M122 28l2.5 6 6 2.5-6 2.5-2.5 6-2.5-6-6-2.5 6-2.5z" fill="#F26A0F" />
    </svg>
  );
}

export function Splash({ text = "Загружаем…" }) {
  return (
    <div className="screen-center" role="status">
      <Loader2 className="spin" size={28} color="#F26A0F" />
      <p className="muted">{text}</p>
    </div>
  );
}

export function Message({ title, text, action, onAction }) {
  return (
    <div className="screen-center">
      <Illustration />
      <h2 className="message-title">{title}</h2>
      <p className="muted message-text">{text}</p>
      {action && (
        <button className="btn btn-dark" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}
