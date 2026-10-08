import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchCompany } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/**
 * Company query for one ticker. The client is rebuilt when the effective
 * base URL or the API key changes, and the query key includes the base URL
 * so switching servers never serves another server's cached data.
 */
export function useCompany(ticker: string) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["company", ticker, baseUrl],
    queryFn: () => fetchCompany(client, ticker),
    enabled: ticker.length > 0,
  });
}
