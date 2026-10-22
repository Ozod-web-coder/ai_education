import { Search, X } from "lucide-react";
import { BOT_STATUSES, STATUSES } from "../constants";
import { countLabel } from "../format";
import LeadCard from "./LeadCard";
import Squiggle from "./Squiggle";
import { Message, Splash } from "./States";

export default function ListScreen({ filters, setFilters, leads, stats, courses, onOpen }) {
  const byStatus = stats?.by_status || {};
  const chips = [
    { value: "", label: "Все", count: stats?.total },
    ...STATUSES.map((s) => ({ ...s, count: byStatus[s.value] || 0 })),
    ...BOT_STATUSES.filter((s) => byStatus[s.value]).map((s) => ({ ...s, count: byStatus[s.value] })),
  ];
  const hasFilters = Boolean(filters.search || filters.status || filters.course);
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <main className="page">
      <header className="page-head">
        <h1 className="h1">Заявки</h1>
        <Squiggle />
        <p className="muted head-sub">
          {leads.loading && !leads.items.length ? "Загружаем…" : countLabel(leads.count, "заявка", "заявки", "заявок")}
        </p>
      </header>

      <div className="search">
        <Search size={18} aria-hidden="true" />
        <input
          type="search"
          inputMode="search"
          placeholder="Имя, телефон или @username"
          aria-label="Поиск по заявкам"
          value={filters.search}
          onChange={(e) => set({ search: e.target.value })}
        />
        {filters.search && (
          <button className="icon-btn" aria-label="Очистить поиск" onClick={() => set({ search: "" })}>
            <X size={16} />
          </button>
        )}
      </div>

      <div className="chips" role="group" aria-label="Фильтр по статусу">
        {chips.map((chip) => (
          <button
            key={chip.value || "all"}
            className={`chip ${filters.status === chip.value ? "chip-active" : ""}`}
            aria-pressed={filters.status === chip.value}
            onClick={() => set({ status: chip.value })}
          >
            {chip.label}
            {chip.count !== undefined && <span className="chip-count">{chip.count}</span>}
          </button>
        ))}
      </div>

      <label className="select-wrap">
        <span className="sr-only">Курс</span>
        <select value={filters.course} onChange={(e) => set({ course: e.target.value })}>
          <option value="">Все курсы</option>
          {courses.map((course) => (
            <option key={course.id} value={course.id}>
              {course.name}
            </option>
          ))}
        </select>
      </label>

      {leads.error && !leads.items.length ? (
        <Message title="Не удалось загрузить" text={leads.error.message} action="Повторить" onAction={leads.refresh} />
      ) : leads.loading && !leads.items.length ? (
        <Splash />
      ) : !leads.items.length ? (
        <Message
          title={hasFilters ? "Ничего не найдено" : "Заявок пока нет"}
          text={hasFilters ? "Измените поиск или сбросьте фильтры." : "Новые заявки появятся здесь, когда ученики запишутся через бота."}
          action={hasFilters ? "Сбросить фильтры" : undefined}
          onAction={() => setFilters({ search: "", status: "", course: "" })}
        />
      ) : (
        <>
          <ul className="list" aria-busy={leads.loading}>
            {leads.items.map((lead) => (
              <li key={lead.id}>
                <LeadCard lead={lead} onOpen={onOpen} />
              </li>
            ))}
          </ul>
          {leads.error && <p className="form-error">{leads.error.message}</p>}
          {leads.hasMore && (
            <button className="btn btn-outline btn-wide" onClick={leads.loadMore} disabled={leads.loading}>
              {leads.loading ? "Загружаем…" : "Показать ещё"}
            </button>
          )}
        </>
      )}
    </main>
  );
}
