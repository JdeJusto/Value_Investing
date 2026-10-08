import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchMethodologies } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/**
 * Methodologies query for one ticker. Same client/keying rules as
 * `useCompany`: the query key includes the base URL so switching servers
 * never serves another server's cached data.
 */
export function useMethodologies(ticker: string) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["methodologies", ticker, baseUrl],
    queryFn: () => fetchMethodologies(client, ticker),
    enabled: ticker.length > 0,
  });
}
