import { useCallback, useEffect, useRef, useState } from "react";
import { listLeads } from "../api";

/** Список заявок с фильтрами и подгрузкой страниц. Устаревшие ответы отбрасываются. */
export function useLeads({ search, status, course }) {
  const [state, setState] = useState({ items: [], count: 0, page: 0, hasMore: false, loading: true, error: null });
  const requestId = useRef(0);

  const load = useCallback(
    async (page) => {
      const id = ++requestId.current;
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const data = await listLeads({ search, status, course, page });
        if (id !== requestId.current) return;
        setState((s) => ({
          items: page === 1 ? data.results : [...s.items, ...data.results],
          count: data.count,
          page,
          hasMore: Boolean(data.next),
          loading: false,
          error: null,
        }));
      } catch (error) {
        if (id !== requestId.current) return;
        setState((s) => ({ ...s, loading: false, error }));
      }
    },
    [search, status, course],
  );

  useEffect(() => {
    load(1);
  }, [load]);

  return {
    ...state,
    loadMore: () => load(state.page + 1),
    refresh: () => load(1),
    removeLocal: (id) =>
      setState((s) => ({ ...s, items: s.items.filter((l) => l.id !== id), count: Math.max(0, s.count - 1) })),
  };
}
