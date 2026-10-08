import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchInsights } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/** Derived growth/stability metrics for one ticker. */
export function useInsights(ticker: string) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["insights", ticker, baseUrl],
    queryFn: () => fetchInsights(client, ticker),
    enabled: ticker.length > 0,
  });
}
