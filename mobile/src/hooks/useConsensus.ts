import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { getEffectiveBaseUrl } from "../api/config";
import {
  fetchConsensus,
  fetchRanking,
  fetchByCategory,
  fetchDisagreement,
  type ConsensusSnapshot,
  type ConsensusRanking,
  type ConsensusByCategory,
  type ConsensusDisagreement,
} from "../api/consensus";
import { useSettings } from "../store/settings";

/**
 * Query the latest consensus snapshot.
 */
export function useConsensusSnapshot(date?: string) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["consensus", date ?? "latest", baseUrl],
    queryFn: () => fetchConsensus(client, date),
    enabled: true,
  });
}

/**
 * Query the top-N consensus ranking.
 */
export function useConsensusRanking(params: {
  date?: string;
  top?: number;
  by?: string;
} = {}) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const key = JSON.stringify(params);

  return useQuery({
    queryKey: ["consensus-ranking", key, baseUrl],
    queryFn: () => fetchRanking(client, params),
    enabled: true,
  });
}

/**
 * Query best companies per Lynch category.
 */
export function useConsensusByCategory(params: {
  date?: string;
  per_category?: number;
} = {}) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const key = JSON.stringify(params);

  return useQuery({
    queryKey: ["consensus-by-category", key, baseUrl],
    queryFn: () => fetchByCategory(client, params),
    enabled: true,
  });
}

/**
 * Query the disagreement zone.
 */
export function useConsensusDisagreement(params: {
  date?: string;
  min_buy?: number;
  max_buy?: number;
} = {}) {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const key = JSON.stringify(params);

  return useQuery({
    queryKey: ["consensus-disagreement", key, baseUrl],
    queryFn: () => fetchDisagreement(client, params),
    enabled: true,
  });
}