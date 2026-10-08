import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { fetchStatement } from "../api/company";
import { getEffectiveBaseUrl } from "../api/config";
import { useSettings } from "../store/settings";

/**
 * One statement from one filing. Disabled until the user selects the
 * Statements sub-view (the no-auto-fetch rule inherited from the desktop).
 */
export function useStatement(
  accession: string,
  statementType: string,
  enabled: boolean,
) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["statement", accession, statementType, baseUrl],
    queryFn: () => fetchStatement(client, accession, statementType),
    enabled: enabled && accession.length > 0,
  });
}
