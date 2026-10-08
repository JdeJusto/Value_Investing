import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchFilings } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/** Filings list for one ticker, with the UI's form/year/amendment filters. */
export function useFilings(
  ticker: string,
  filters?: {
    form?: string;
    year?: number;
    limit?: number;
    includeAmendments?: boolean;
  },
) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const form = filters?.form ?? null;
  const year = filters?.year ?? null;
  const limit = filters?.limit ?? 50;
  const includeAmendments = filters?.includeAmendments ?? true;

  return useQuery({
    queryKey: ["filings", ticker, baseUrl, form, year, limit, includeAmendments],
    queryFn: () =>
      fetchFilings(client, ticker, {
        form: form ?? undefined,
        year: year ?? undefined,
        limit,
        includeAmendments,
      }),
    enabled: ticker.length > 0,
  });
}
