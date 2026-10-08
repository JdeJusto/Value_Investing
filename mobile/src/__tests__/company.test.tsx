import type { UseQueryResult } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react-native";

import CompanyScreen from "../../app/company/[ticker]";
import { ApiRequestError, type ApiEnvelope } from "../api/client";
import type {
  CompanyResponse,
  DCFResponse,
  FinancialsResponse,
  InsightsResponse,
  MethodologiesResponse,
} from "../api/company";
import { useCompany } from "../hooks/useCompany";
import { useDCF } from "../hooks/useDCF";
import { useFinancials } from "../hooks/useFinancials";
import { useInsights } from "../hooks/useInsights";
import { useMethodologies } from "../hooks/useMethodologies";
import { ThemeProvider } from "../theme/ThemeProvider";

jest.mock("expo-router", () => ({
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({ ticker: "AAPL" }),
}));

jest.mock("../hooks/useCompany", () => ({
  useCompany: jest.fn(),
}));

jest.mock("../hooks/useMethodologies", () => ({
  useMethodologies: jest.fn(),
}));

jest.mock("../hooks/useDCF", () => ({
  useDCF: jest.fn(),
}));

jest.mock("../hooks/useFinancials", () => ({
  useFinancials: jest.fn(),
}));

jest.mock("../hooks/useInsights", () => ({
  useInsights: jest.fn(),
}));

const mockUseCompany = useCompany as jest.MockedFunction<typeof useCompany>;
const mockUseMethodologies = useMethodologies as jest.MockedFunction<
  typeof useMethodologies
>;
const mockUseDCF = useDCF as jest.MockedFunction<typeof useDCF>;
const mockUseFinancials = useFinancials as jest.MockedFunction<
  typeof useFinancials
>;
const mockUseInsights = useInsights as jest.MockedFunction<typeof useInsights>;

function queryResult<T>(
  partial: Partial<UseQueryResult<ApiEnvelope<T>, Error>>,
): UseQueryResult<ApiEnvelope<T>, Error> {
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
  } as unknown as UseQueryResult<ApiEnvelope<T>, Error>;
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
  mockUseMethodologies.mockReset();
  mockUseMethodologies.mockReturnValue(
    queryResult<MethodologiesResponse>({ isLoading: true, isPending: true }),
  );
  mockUseDCF.mockReset();
  mockUseDCF.mockReturnValue(
    queryResult<DCFResponse>({ isLoading: true, isPending: true }),
  );
  mockUseFinancials.mockReset();
  mockUseFinancials.mockReturnValue(
    queryResult<FinancialsResponse>({ isLoading: true, isPending: true }),
  );
  mockUseInsights.mockReset();
  mockUseInsights.mockReturnValue(
    queryResult<InsightsResponse>({ isLoading: true, isPending: true }),
  );
});

test("renders the overview with live company data", async () => {
  mockUseCompany.mockReturnValue(
    queryResult<CompanyResponse>({ data: ENVELOPE, isSuccess: true }),
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
    queryResult<CompanyResponse>({ data: ENVELOPE, isSuccess: true }),
  );
  await renderCompany();
  await fireEvent.press(screen.getByText("Filings"));
  expect(screen.getByText("Filings — coming soon.")).toBeTruthy();
});

test("opens the Financials tab with its own loading state", async () => {
  mockUseCompany.mockReturnValue(
    queryResult<CompanyResponse>({ data: ENVELOPE, isSuccess: true }),
  );
  await renderCompany();
  await fireEvent.press(screen.getByText("Financials"));
  expect(screen.getByTestId("skeleton-cards")).toBeTruthy();
});

test("opens the DCF tab with its own loading state", async () => {
  mockUseCompany.mockReturnValue(
    queryResult<CompanyResponse>({ data: ENVELOPE, isSuccess: true }),
  );
  await renderCompany();
  await fireEvent.press(screen.getByText("DCF"));
  expect(screen.getByTestId("skeleton-cards")).toBeTruthy();
});

test("shows a pull-to-refresh error state when the query fails", async () => {
  mockUseCompany.mockReturnValue(
    queryResult<CompanyResponse>({
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
