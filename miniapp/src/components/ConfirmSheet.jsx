import { useEffect } from "react";

/** Нижняя шторка подтверждения опасного действия. */
export default function ConfirmSheet({ title, text, confirmLabel, busy, onConfirm, onCancel }) {
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="sheet-backdrop" onClick={onCancel}>
      <div className="sheet" role="alertdialog" aria-modal="true" aria-labelledby="sheet-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="sheet-title" className="sheet-title">
          {title}
        </h2>
        <p className="muted">{text}</p>
        <div className="sheet-actions">
          <button className="btn btn-outline" onClick={onCancel} disabled={busy} autoFocus>
            Отмена
          </button>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? "Удаляем…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
