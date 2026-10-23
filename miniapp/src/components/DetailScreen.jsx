import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  CalendarDays,
  Check,
  ChevronLeft,
  Phone,
  Send,
  Signal,
  Target,
  Trash2,
  TriangleAlert,
  UserRound,
  Users,
} from "lucide-react";
import { confirmLead, deleteLead, getLead, updateLead } from "../api";
import { STATUSES } from "../constants";
import { formatDate, formatDateTime, initials, telHref, tgHref } from "../format";
import { haptic, openLink } from "../telegram";
import ConfirmSheet from "./ConfirmSheet";
import Squiggle from "./Squiggle";
import StatusPill from "./StatusPill";
import { Message, Splash } from "./States";

const NOTIFY_REASONS = {
  no_telegram: "у ученика нет Telegram",
  blocked: "ученик заблокировал бота",
  no_bot: "у центра не задан токен бота",
  error: "Telegram не ответил",
};

/** Что показать администратору после «Отказался»: дошло ли сообщение ученику. */
function declineOutcome(data) {
  const note = data.student_notification;
  if (!note) return { text: "Статус обновлён", kind: "ok" };
  if (note.sent) return { text: "Статус обновлён, ученику отправлено уведомление", kind: "ok" };
  const reason = NOTIFY_REASONS[note.reason] || "ошибка отправки";
  return { text: `Статус обновлён, но ученика не удалось уведомить: ${reason}. Позвоните ему.`, kind: "warn" };
}

function Tile({ icon: Icon, label, children, href, onClick }) {
  const body = (
    <>
      <span className="tile-icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{children}</span>
    </>
  );
  if (href) return <a className="tile tile-link" href={href}>{body}</a>;
  if (onClick) return <button className="tile tile-link" onClick={onClick}>{body}</button>;
  return <div className="tile">{body}</div>;
}

export default function DetailScreen({ id, courses, inTelegram, onBack, onChanged, onDeleted, onOpenOther }) {
  const [lead, setLead] = useState(null);
  const [error, setError] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [askDecline, setAskDecline] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef();

  const showToast = useCallback((text, kind = "ok") => {
    setToast({ text, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), kind === "ok" ? 2600 : 6000);
  }, []);

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const load = useCallback(async () => {
    setLead(null);
    setError(null);
    try {
      const data = await getLead(id);
      setLead(data);
      setNote(data.manager_note);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    load();
    window.scrollTo(0, 0);
  }, [load]);

  async function mutate(action, success) {
    setBusy(true);
    try {
      const data = await action();
      setLead(data);
      setNote(data.manager_note);
      const outcome = typeof success === "function" ? success(data) : { text: success, kind: "ok" };
      haptic(outcome.kind === "ok" ? "success" : "warning");
      showToast(outcome.text, outcome.kind);
      onChanged();
    } catch (e) {
      haptic("error");
      showToast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function declineAndNotify() {
    await mutate(() => updateLead(id, { status: "declined" }), declineOutcome);
    setAskDecline(false);
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteLead(id);
      haptic("success");
      onDeleted(id);
    } catch (e) {
      setBusy(false);
      setAskDelete(false);
      haptic("error");
      showToast(e.message, "error");
    }
  }

  if (error) {
    return (
      <Message
        title={error.status === 404 ? "Заявка не найдена" : "Не удалось открыть заявку"}
        text={error.status === 404 ? "Возможно, её уже удалили." : error.message}
        action={error.status === 404 ? "К списку" : "Повторить"}
        onAction={error.status === 404 ? onBack : load}
      />
    );
  }
  if (!lead) return <Splash />;

  const noteDirty = note !== lead.manager_note;
  const level = lead.assessed_level || lead.declared_level;
  const showParent = lead.is_minor || lead.parent_phone || lead.parent_name;

  return (
    <main className="page page-detail">
      {!inTelegram && (
        <button className="back" onClick={onBack}>
          <ChevronLeft size={18} aria-hidden="true" /> К списку
        </button>
      )}

      <header className="detail-head">
        <span className="avatar avatar-lg" aria-hidden="true">
          {initials(lead.name)}
        </span>
        <div>
          <h1 className="h1 h1-detail">{lead.name || "Без имени"}</h1>
          <Squiggle />
        </div>
      </header>
      <div className="detail-sub">
        <StatusPill status={lead.status} label={lead.status_display} />
        <span className="muted">Заявка от {formatDateTime(lead.created_at)}</span>
      </div>

      {lead.duplicates.length > 0 && (
        <section className="banner" aria-label="Повторная заявка">
          <div className="banner-head">
            <TriangleAlert size={20} aria-hidden="true" />
            <strong>Этот человек уже записывался</strong>
          </div>
          <p>Есть другие заявки с тем же телефоном или Telegram. Проверьте, не создана ли заявка по ошибке.</p>
          <ul className="dup-list">
            {lead.duplicates.map((dup) => (
              <li key={dup.id}>
                <button className="dup" onClick={() => onOpenOther(dup.id)}>
                  <span className="dup-name">{dup.name || "Без имени"}</span>
                  <span className="dup-meta">
                    {dup.phone || "без телефона"} · {formatDate(dup.created_at)} · {dup.status_display}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="tiles" aria-label="Данные заявки">
        <Tile icon={Phone} label="Телефон" href={lead.phone ? telHref(lead.phone) : undefined}>
          {lead.phone || "—"}
        </Tile>
        <Tile
          icon={Send}
          label="Telegram"
          onClick={lead.telegram_username ? () => openLink(tgHref(lead.telegram_username)) : undefined}
        >
          {lead.telegram_username ? `@${lead.telegram_username}` : "Нет username"}
        </Tile>
        <Tile icon={CalendarDays} label="Дата регистрации">
          {formatDate(lead.created_at)}
        </Tile>
        <Tile icon={UserRound} label="Возраст">
          {lead.age ?? "—"}
        </Tile>
        <Tile icon={Signal} label="Уровень">
          {level || "—"}
        </Tile>
        <Tile icon={BookOpen} label="Курс">
          {lead.course || "—"}
        </Tile>
      </section>

      <section className="block">
        <label className="label" htmlFor="course">
          Желаемый курс
        </label>
        <div className="select-wrap">
          <select
            id="course"
            value={lead.desired_course ?? ""}
            disabled={busy}
            onChange={(e) =>
              mutate(() => updateLead(id, { desired_course: e.target.value ? Number(e.target.value) : null }), "Курс обновлён")
            }
          >
            <option value="">{lead.course ? `${lead.course} (по записи в группу)` : "Не выбран"}</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.name}
              </option>
            ))}
          </select>
        </div>
      </section>

      {lead.goal && (
        <section className="block">
          <h2 className="h2">
            <Target size={18} aria-hidden="true" /> Цель обучения
          </h2>
          <p className="text">{lead.goal}</p>
        </section>
      )}

      {showParent && (
        <section className="block">
          <h2 className="h2">
            <Users size={18} aria-hidden="true" /> Родитель
          </h2>
          <p className="text">
            {lead.parent_name || "Имя не указано"}
            {lead.parent_phone && (
              <>
                {" · "}
                <a className="link" href={telHref(lead.parent_phone)}>
                  {lead.parent_phone}
                </a>
              </>
            )}
          </p>
        </section>
      )}

      <section className="block">
        <h2 className="h2">Статус заявки</h2>
        <div className="status-grid" role="group" aria-label="Статус заявки">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              className={`chip chip-status ${lead.status === s.value ? "chip-active" : ""}`}
              aria-pressed={lead.status === s.value}
              disabled={busy}
              onClick={() => {
                if (s.value === lead.status) return;
                // «Отказался» отправляет ученику сообщение, поэтому сначала спрашиваем.
                if (s.value === "declined") setAskDecline(true);
                else mutate(() => updateLead(id, { status: s.value }), "Статус обновлён");
              }}
            >
              {lead.status === s.value && <Check size={14} aria-hidden="true" />}
              {s.label}
            </button>
          ))}
        </div>
        <p className="muted small">
          {lead.contacted_at ? (
            <span className="contacted">
              <Check size={14} aria-hidden="true" /> Связались с учеником: {formatDateTime(lead.contacted_at)}
            </span>
          ) : (
            "С учеником ещё не связывались."
          )}
        </p>
      </section>

      {lead.bookings.length > 0 && (
        <section className="block">
          <h2 className="h2">Записи в группы</h2>
          <ul className="bookings">
            {lead.bookings.map((b) => (
              <li key={b.id} className="booking">
                <div>
                  <strong>{b.group}</strong>
                  <span className="muted small">
                    {b.course} · {b.branch}
                  </span>
                  {b.trial_at && <span className="muted small">Пробный урок: {formatDateTime(b.trial_at)}</span>}
                </div>
                <span className="chip-soft">{b.status_display}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="block">
        <label className="label" htmlFor="note">
          Заметка менеджера
        </label>
        <textarea
          id="note"
          rows={4}
          value={note}
          placeholder="Например: просил перезвонить после 18:00"
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          className="btn btn-outline"
          disabled={!noteDirty || busy}
          onClick={() => mutate(() => updateLead(id, { manager_note: note }), "Заметка сохранена")}
        >
          Сохранить заметку
        </button>
      </section>

      <button className="btn btn-danger-outline btn-wide" disabled={busy} onClick={() => setAskDelete(true)}>
        <Trash2 size={18} aria-hidden="true" /> Удалить заявку
      </button>

      <div className="action-bar">
        {lead.phone && (
          <a className="btn btn-outline" href={telHref(lead.phone)}>
            <Phone size={18} aria-hidden="true" /> Позвонить
          </a>
        )}
        {!lead.contacted_at && (
          <button className="btn btn-accent" disabled={busy} onClick={() => mutate(() => confirmLead(id), "Заявка подтверждена")}>
            <Check size={18} aria-hidden="true" /> Связался
          </button>
        )}
      </div>

      {toast && (
        <div className={`toast toast-${toast.kind}`} role="status">
          {toast.text}
        </div>
      )}

      {askDecline && (
        <ConfirmSheet
          title="Отметить «Отказался»?"
          text="Ученику в Telegram придёт уведомление: запись на пробный урок отменена, а если он отказался по ошибке, пусть позвонит администрации. Действующие записи в группы будут отменены, места освободятся."
          confirmLabel="Отметить и уведомить"
          busyLabel="Отправляем…"
          busy={busy}
          onConfirm={declineAndNotify}
          onCancel={() => !busy && setAskDecline(false)}
        />
      )}

      {askDelete && (
        <ConfirmSheet
          title={`Удалить заявку «${lead.name || "Без имени"}»?`}
          text="Записи ученика в группы тоже удалятся, а занятые места освободятся. Отменить это нельзя."
          confirmLabel="Удалить"
          busyLabel="Удаляем…"
          busy={busy}
          onConfirm={remove}
          onCancel={() => !busy && setAskDelete(false)}
        />
      )}
    </main>
  );
}
