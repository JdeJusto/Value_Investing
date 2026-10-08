import type { UseQueryResult } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react-native";

import CompanyScreen from "../../app/company/[ticker]";
import { ApiRequestError, type ApiEnvelope } from "../api/client";
import type { CompanyResponse } from "../api/company";
import { useCompany } from "../hooks/useCompany";
import { ThemeProvider } from "../theme/ThemeProvider";

jest.mock("expo-router", () => ({
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({ ticker: "AAPL" }),
}));

jest.mock("../hooks/useCompany", () => ({
  useCompany: jest.fn(),
}));

const mockUseCompany = useCompany as jest.MockedFunction<typeof useCompany>;

type CompanyQuery = UseQueryResult<ApiEnvelope<CompanyResponse>, Error>;

function queryResult(partial: Partial<CompanyQuery>): CompanyQuery {
  return {
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
    isPending: false,
    isRefetching: false,
    isSuccess: false,
    refetch: jest.fn(),
    ...partial,
  } as unknown as CompanyQuery;
}

const ENVELOPE: ApiEnvelope<CompanyResponse> = {
  data: {
    ticker: "AAPL",
    name: "Apple Inc.",
    sector: "Technology",
    cik: "0000320193",
    price: 336.67,
    market_cap: 4_913_422_663_680,
    currency: "USD",
    fiscal_year: 2025,
  },
  meta: { source: "mixed", as_of: "2026-10-08T00:00:00Z", cache_ttl: 300 },
};

function renderCompany() {
  return render(
    <ThemeProvider>
      <CompanyScreen />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  mockUseCompany.mockReset();
});

test("renders the overview with live company data", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({ data: ENVELOPE, isSuccess: true }),
  );
  await renderCompany();
  const card = screen.getByText("Apple Inc.");
  expect(card).toBeTruthy();
  expect(screen.getByText("Technology")).toBeTruthy();
  expect(screen.getByText("$336.67")).toBeTruthy();
  expect(screen.getByText("$4.91T")).toBeTruthy();
  expect(screen.getByText("2025")).toBeTruthy();
});

test("switches to a stub tab without leaving the screen", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({ data: ENVELOPE, isSuccess: true }),
  );
  await renderCompany();
  await fireEvent.press(screen.getByText("DCF"));
  expect(screen.getByText("DCF — coming soon.")).toBeTruthy();
});

test("shows a pull-to-refresh error state when the query fails", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({
      error: new ApiRequestError("NETWORK_ERROR", "unreachable", 0),
      isError: true,
    }),
  );
  await renderCompany();
  const message = screen.getByText(
    "Could not load this company. Pull to refresh.",
  );
  expect(message).toBeTruthy();
});
