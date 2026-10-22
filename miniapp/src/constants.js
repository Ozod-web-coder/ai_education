// Статусы, которые администратор ставит вручную.
export const STATUSES = [
  { value: "new", label: "Новая" },
  { value: "confirmed", label: "Подтверждена" },
  { value: "attended", label: "Пришёл" },
  { value: "no_show", label: "Не пришёл" },
  { value: "enrolled", label: "Записан на курс" },
  { value: "declined", label: "Отказался" },
];

// Статусы, которые ставит бот. Показываем их, если такие заявки есть.
export const BOT_STATUSES = [
  { value: "needs_manager", label: "Нужен менеджер" },
  { value: "tested", label: "Прошёл тест" },
  { value: "booked", label: "Записан" },
  { value: "lost", label: "Потерян" },
];

export const STATUS_LABELS = Object.fromEntries([...STATUSES, ...BOT_STATUSES].map((s) => [s.value, s.label]));
