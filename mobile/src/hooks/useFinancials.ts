import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchFinancials } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/** Facts view for one ticker; the table requests the compact format. */
export function useFinancials(
  ticker: string,
  opts?: { years?: number; abbreviate?: boolean },
) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const years = opts?.years ?? 10;
  const abbreviate = opts?.abbreviate ?? false;

  return useQuery({
    queryKey: ["financials", ticker, baseUrl, years, abbreviate],
    queryFn: () => fetchFinancials(client, ticker, { years, abbreviate }),
    enabled: ticker.length > 0,
  });
}
