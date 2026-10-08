import type { SettingsState } from "../store/settings";

export type BaseUrlSettings = Pick<
  SettingsState,
  "lanUrl" | "tailscaleUrl" | "useTailscale" | "useEmulator"
>;

/**
 * Effective base URL for API calls.
 *
 * Emulator mode forces `http://10.0.2.2:8000` — `10.0.2.2` is the Android
 * emulator's alias for the host machine's localhost, which removes all
 * LAN/Tailscale friction during development.
 *
 * Otherwise: the Tailscale URL when preferred and configured, else the LAN
 * URL. Trailing slashes and stray whitespace are removed.
 */
export function getEffectiveBaseUrl(settings: BaseUrlSettings): string {
  if (settings.useEmulator) {
    return "http://10.0.2.2:8000";
  }
  const url =
    settings.useTailscale && settings.tailscaleUrl
      ? settings.tailscaleUrl
      : settings.lanUrl;
  return url.trim().replace(/\/$/, "");
}
