import type { SettingsState } from "../store/settings";

/**
 * Effective base URL: the Tailscale URL when preferred and configured,
 * otherwise the LAN URL. Trailing slashes and stray whitespace are removed.
 */
export function getEffectiveBaseUrl(settings: SettingsState): string {
  const url =
    settings.useTailscale && settings.tailscaleUrl
      ? settings.tailscaleUrl
      : settings.lanUrl;
  return url.trim().replace(/\/$/, "");
}
