/**
 * Minimal typed client for the Value Investing REST API.
 *
 * Every call carries the `X-API-Key` header and parses the standard envelope:
 *   { data, meta: { source, as_of, cache_ttl } }
 *
 * Errors are normalized to `ApiRequestError` so screens can react to `code`
 * (e.g. TICKER_NOT_FOUND, NETWORK_ERROR, UNAUTHORIZED).
 */

export type ApiEnvelope<T> = {
  data: T;
  meta: {
    source:
      | "financial_database"
      | "yahoo"
      | "mixed"
      | "internal"
      | "consensus_json"
      | "portfolio_json";
    as_of: string;
    cache_ttl: number;
    warning?: string;
  };
};

export type ApiError = {
  error: {
    code: string;
    message: string;
  };
};

export type ApiConfig = {
  baseUrl: string; // e.g. "http://192.168.0.105:8000"
  apiKey: string;
};

/** Per-request timeout (AbortController). */
const TIMEOUT_MS = 15_000;

export class ApiRequestError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
  }
}

export class ApiClient {
  constructor(private readonly config: ApiConfig) {}

  get<T>(path: string): Promise<ApiEnvelope<T>> {
    return this.request<T>("GET", path);
  }

  post<T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> {
    return this.request<T>("POST", path, body);
  }

  delete<T>(path: string): Promise<ApiEnvelope<T>> {
    return this.request<T>("DELETE", path);
  }

  private async request<T>(
    method: "GET" | "POST" | "DELETE",
    path: string,
    body?: unknown,
  ): Promise<ApiEnvelope<T>> {
    const base = this.config.baseUrl.replace(/\/+$/, "");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(`${base}${path}`, {
        method,
        headers: {
          Accept: "application/json",
          "X-API-Key": this.config.apiKey,
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (error) {
      const aborted = error instanceof Error && error.name === "AbortError";
      throw new ApiRequestError(
        "NETWORK_ERROR",
        aborted
          ? `Request to ${base} timed out after ${TIMEOUT_MS / 1000}s.`
          : `Cannot reach the server at ${base}. Check Settings.`,
        0,
      );
    } finally {
      clearTimeout(timer);
    }

    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const bodyError = (payload as ApiError | null)?.error;
      throw new ApiRequestError(
        bodyError?.code ?? `HTTP_${response.status}`,
        bodyError?.message ?? `Request failed with status ${response.status}`,
        response.status,
      );
    }

    return payload as ApiEnvelope<T>;
  }
}
