import { useCallback, useEffect, useRef, useState } from "react";
import { getStats, listCourses } from "./api";
import DetailScreen from "./components/DetailScreen";
import ListScreen from "./components/ListScreen";
import { Message, Splash } from "./components/States";
import { useDebounce } from "./hooks/useDebounce";
import { useLeads } from "./hooks/useLeads";
import { bindBackButton, inTelegram } from "./telegram";

const EMPTY_FILTERS = { search: "", status: "", course: "" };

export default function App() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [openId, setOpenId] = useState(null);
  const [courses, setCourses] = useState([]);
  const [stats, setStats] = useState(null);
  const scrollY = useRef(0);

  const search = useDebounce(filters.search.trim(), 300);
  const leads = useLeads({ search, status: filters.status, course: filters.course });

  const refreshStats = useCallback(() => getStats().then(setStats).catch(() => {}), []);

  useEffect(() => {
    refreshStats();
    listCourses().then(setCourses).catch(() => {});
  }, [refreshStats]);

  const openLead = useCallback((id) => {
    setOpenId((current) => {
      if (current === null) scrollY.current = window.scrollY;
      return id;
    });
  }, []);

  const backToList = useCallback(() => {
    setOpenId(null);
    requestAnimationFrame(() => window.scrollTo(0, scrollY.current));
  }, []);

  useEffect(() => (openId === null ? undefined : bindBackButton(backToList)), [openId, backToList]);

  const changed = useCallback(() => {
    leads.refresh();
    refreshStats();
  }, [leads, refreshStats]);

  // Нет доступа или не Telegram: список не загрузится, показываем причину вместо пустого экрана.
  const fatal = leads.error && !leads.items.length && ["forbidden", "no-telegram", "auth"].includes(leads.error.code);
  if (fatal) {
    const forbidden = leads.error.code === "forbidden";
    return (
      <Message
        title={forbidden ? "Нет доступа" : leads.error.code === "no-telegram" ? "Откройте из Telegram" : "Не удалось войти"}
        text={
          forbidden
            ? "Ваш Telegram-аккаунт не добавлен в сотрудники центра. Попросите владельца добавить вас в админке."
            : leads.error.message
        }
        action={forbidden ? undefined : "Повторить"}
        onAction={() => window.location.reload()}
      />
    );
  }

  if (openId !== null) {
    return (
      <DetailScreen
        key={openId}
        id={openId}
        courses={courses}
        inTelegram={inTelegram}
        onBack={backToList}
        onChanged={changed}
        onOpenOther={(id) => setOpenId(id)}
        onDeleted={(id) => {
          leads.removeLocal(id);
          refreshStats();
          backToList();
        }}
      />
    );
  }

  return <ListScreen filters={filters} setFilters={setFilters} leads={leads} stats={stats} courses={courses} onOpen={openLead} />;
}
