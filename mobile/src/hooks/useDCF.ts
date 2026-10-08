import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchDCF } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/**
 * DCF query for one ticker. Same client/keying rules as `useCompany` and
 * `useMethodologies`; the valuation itself runs server-side and is cached
 * for 5 minutes.
 */
export function useDCF(ticker: string) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["dcf", ticker, baseUrl],
    queryFn: () => fetchDCF(client, ticker),
    enabled: ticker.length > 0,
  });
}
