import type { UseQueryResult } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react-native";

import HomeScreen from "../../app/(tabs)/index";
import { ApiRequestError, type ApiEnvelope } from "../api/client";
import type { CompanyResponse } from "../api/company";
import { useCompany } from "../hooks/useCompany";
import { ThemeProvider } from "../theme/ThemeProvider";

jest.mock("expo-router", () => ({
  router: { push: jest.fn() },
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
    isSuccess: false,
    ...partial,
  } as unknown as CompanyQuery;
}

const COMPANY: CompanyResponse = {
  ticker: "AAPL",
  name: "Apple Inc.",
  sector: "Technology",
  cik: "0000320193",
  price: 336.67,
  market_cap: 4_913_422_663_680,
  currency: "USD",
  fiscal_year: 2025,
};

const ENVELOPE: ApiEnvelope<CompanyResponse> = {
  data: COMPANY,
  meta: { source: "mixed", as_of: "2026-10-08T00:00:00Z", cache_ttl: 300 },
};

function renderHome() {
  return render(
    <ThemeProvider>
      <HomeScreen />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  mockUseCompany.mockReset();
});

test("renders a skeleton while loading", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({ isLoading: true, isPending: true }),
  );
  await renderHome();
  expect(screen.getByTestId("company-skeleton")).toBeTruthy();
});

test("renders the company card on success", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({ data: ENVELOPE, isSuccess: true }),
  );
  await renderHome();
  const card = screen.getByTestId("company-card");
  expect(within(card).getByText("AAPL")).toBeTruthy();
  expect(within(card).getByText("Apple Inc.")).toBeTruthy();
  expect(within(card).getByText("$336.67")).toBeTruthy();
  expect(within(card).getByText("$4.91T")).toBeTruthy();
});

test("maps TICKER_NOT_FOUND to a clear message", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({
      error: new ApiRequestError(
        "TICKER_NOT_FOUND",
        "Unknown ticker: ZZZZ",
        404,
      ),
      isError: true,
    }),
  );
  await renderHome();
  await fireEvent.changeText(
    screen.getByPlaceholderText("Ticker (e.g. AAPL)"),
    "ZZZZ",
  );
  expect(screen.getByText("Ticker ZZZZ not found.")).toBeTruthy();
});

test("maps NETWORK_ERROR to a settings hint", async () => {
  mockUseCompany.mockReturnValue(
    queryResult({
      error: new ApiRequestError("NETWORK_ERROR", "unreachable", 0),
      isError: true,
    }),
  );
  await renderHome();
  expect(
    screen.getByText("Cannot reach the server. Check Settings."),
  ).toBeTruthy();
});
