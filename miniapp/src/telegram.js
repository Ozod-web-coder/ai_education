const tg = typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

export const inTelegram = Boolean(tg?.initData);
export const getInitData = () => tg?.initData || "";

export function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  // Дизайн светлый, поэтому шапку и фон красим под него независимо от темы Telegram.
  tg.setHeaderColor?.("#ffffff");
  tg.setBackgroundColor?.("#ffffff");
  tg.disableVerticalSwipes?.();
}

export function haptic(kind = "light") {
  if (kind === "success" || kind === "error" || kind === "warning") tg?.HapticFeedback?.notificationOccurred(kind);
  else tg?.HapticFeedback?.impactOccurred(kind);
}

export function bindBackButton(onBack) {
  const button = tg?.BackButton;
  if (!button) return () => {};
  button.onClick(onBack);
  button.show();
  return () => {
    button.offClick(onBack);
    button.hide();
  };
}

export function openLink(url) {
  if (tg && url.startsWith("https://t.me/")) tg.openTelegramLink(url);
  else if (tg && url.startsWith("http")) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}
