const dateFormat = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const plural = new Intl.PluralRules("ru");

export const formatDate = (iso) => (iso ? dateFormat.format(new Date(iso)) : "—");
export const formatDateTime = (iso) => (iso ? dateTimeFormat.format(new Date(iso)) : "—");

export function initials(name) {
  const letters = (name || "").trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || "");
  return letters.join("") || "?";
}

export const telHref = (phone) => `tel:${(phone || "").replace(/[^\d+]/g, "")}`;
export const tgHref = (username) => `https://t.me/${(username || "").replace(/^@/, "")}`;

export function countLabel(n, one, few, many) {
  const form = plural.select(n);
  return `${n} ${form === "one" ? one : form === "few" ? few : many}`;
}
