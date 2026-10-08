import { ApiRequestError } from "../api/client";

/** Map an API failure to a human message for the current screen. */
export function apiErrorMessage(error: unknown, ticker = ""): string {
  if (error instanceof ApiRequestError) {
    if (error.code === "TICKER_NOT_FOUND") {
      return ticker ? `Ticker ${ticker} not found.` : "Ticker not found.";
    }
    if (error.code === "NETWORK_ERROR") {
      return "Cannot reach the server. Check Settings.";
    }
    if (error.code === "UNAUTHORIZED" || error.status === 401) {
      return "Invalid API key. Check Settings.";
    }
    if (error.code === "API_KEY_NOT_CONFIGURED") {
      return "The server has no API key configured.";
    }
    return error.message;
  }
  return "Something went wrong. Try again.";
}
