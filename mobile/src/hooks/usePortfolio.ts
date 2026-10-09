import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { ApiClient } from "../api/client";
import { getEffectiveBaseUrl } from "../api/config";
import {
  fetchPortfolio,
  fetchPortfolioPerformance,
  addPosition,
  removePosition,
  exitPosition,
  type PortfolioData,
  type PortfolioPerformanceData,
  type PositionCreate,
  type ExitResponse,
} from "../api/portfolio";
import { useSettings } from "../store/settings";

export function usePortfolio() {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["portfolio", baseUrl],
    queryFn: () => fetchPortfolio(client),
    enabled: true,
    refetchInterval: 60_000,
  });
}

export function usePortfolioPerformance() {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );

  return useQuery({
    queryKey: ["portfolio-performance", baseUrl],
    queryFn: () => fetchPortfolioPerformance(client),
    enabled: true,
    refetchInterval: 60_000,
  });
}

export function useAddPosition() {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PositionCreate) => addPosition(client, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", baseUrl] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-performance", baseUrl] });
    },
  });
}

export function useRemovePosition() {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ticker: string) => removePosition(client, ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", baseUrl] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-performance", baseUrl] });
    },
  });
}

export function useExitPosition() {
  const settings = useSettings();
  const baseUrl = getEffectiveBaseUrl(settings);
  const apiKey = settings.apiKey;
  const client = useMemo(
    () => new ApiClient({ baseUrl, apiKey }),
    [baseUrl, apiKey],
  );
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ticker: string) => exitPosition(client, ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", baseUrl] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-performance", baseUrl] });
    },
  });
}