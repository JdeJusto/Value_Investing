import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchSection } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/**
 * One narrative section from one filing. Disabled until the user selects the
 * Narrative sub-view; ``wordLimit`` keeps the first load a short preview and
 * the "Load full section" action re-runs the query without it.
 */
export function useSection(
  accession: string,
  sectionType: string,
  enabled: boolean,
  wordLimit?: number,
) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["section", accession, sectionType, baseUrl, wordLimit ?? null],
    queryFn: () => fetchSection(client, accession, sectionType, { wordLimit }),
    enabled: enabled && accession.length > 0,
  });
}
