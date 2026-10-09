import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { getEffectiveBaseUrl } from "../api/config";
import { fetchScreener, type ScreenerFilterParams } from "../api/screener";
import { useSettings } from "../store/settings";

export const SCREENER_PAGE_SIZE = 50;

/**
 * Paginated screener query.
 *
 * The screener is expensive, so the query stays disabled until the user taps
 * "Run" (`enabled`); every page after the first is served from the server's
 * 5-minute cache. The query key includes the filters and the base URL.
 */
export function useScreener(filters: ScreenerFilterParams, enabled: boolean) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const filterKey = JSON.stringify(filters);

  return useInfiniteQuery({
    queryKey: ["screener", filterKey, baseUrl],
    enabled,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      fetchScreener(client, {
        ...filters,
        page: pageParam,
        page_size: SCREENER_PAGE_SIZE,
      }),
    getNextPageParam: (last) =>
      last.data.page < last.data.total_pages ? last.data.page + 1 : undefined,
  });
}
