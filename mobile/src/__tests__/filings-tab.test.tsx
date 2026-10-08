import type { UseQueryResult } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react-native";

import type { ApiEnvelope } from "../api/client";
import type {
  FilingsResponse,
  SectionResponse,
  StatementResponse,
} from "../api/company";
import { FilingsTab } from "../components/FilingsTab";
import { useFilings } from "../hooks/useFilings";
import { useSection } from "../hooks/useSection";
import { useStatement } from "../hooks/useStatement";
import { ThemeProvider } from "../theme/ThemeProvider";

jest.mock("../hooks/useFilings", () => ({ useFilings: jest.fn() }));
jest.mock("../hooks/useStatement", () => ({ useStatement: jest.fn() }));
jest.mock("../hooks/useSection", () => ({ useSection: jest.fn() }));

const mockUseFilings = useFilings as jest.MockedFunction<typeof useFilings>;
const mockUseStatement = useStatement as jest.MockedFunction<
  typeof useStatement
>;
const mockUseSection = useSection as jest.MockedFunction<typeof useSection>;

function queryResult<T>(
  partial: Partial<UseQueryResult<ApiEnvelope<T>, Error>>,
): UseQueryResult<ApiEnvelope<T>, Error> {
  return {
    data: undefined,
    error: null,
    isError: false,
    isLoading: false,
    isPending: false,
    isSuccess: false,
    ...partial,
  } as unknown as UseQueryResult<ApiEnvelope<T>, Error>;
}

const META = { source: "financial_database", as_of: "", cache_ttl: 0 } as const;

const FILINGS: FilingsResponse = {
  ticker: "AAPL",
  filings: [
    {
      accession_number: "0000320193-24-000123",
      form_type: "10-K",
      filing_date: "2024-11-01",
      period_of_report: "2024-09-28",
      fiscal_year: 2024,
      is_amended: false,
      sec_url: "https://www.sec.gov/Archives/edgar/data/320193/x",
    },
    {
      accession_number: "0000320193-24-000200",
      form_type: "8-K",
      filing_date: "2024-08-01",
      period_of_report: null,
      fiscal_year: 2024,
      is_amended: true,
      sec_url: null,
    },
  ],
  count: 2,
  available_forms: ["10-K", "8-K"],
  available_years: [2024],
};

const STATEMENT: StatementResponse = {
  accession_number: "0000320193-24-000123",
  form_type: "10-K",
  filing_date: "2024-11-01",
  period_end: "2024-09-28",
  statement_type: "balance_sheet",
  source: "anchors",
  warnings: [],
  lines: [
    {
      label: "Cash and cash equivalents",
      current: "$29,943",
      prior: "$29,965",
      indent_level: 0,
    },
    { label: "Total assets", current: "$364,980", prior: "$352,583", indent_level: 0 },
  ],
};

const SECTION: SectionResponse = {
  accession_number: "0000320193-24-000123",
  form_type: "10-K",
  section_type: "risk_factors",
  title: "Item 1A. Risk Factors",
  word_count: 12000,
  source: "toc_anchor",
  warnings: [],
  text: "The Company faces risks. ".repeat(20),
  truncated: true,
};

beforeEach(() => {
  mockUseFilings.mockReset();
  mockUseFilings.mockReturnValue(
    queryResult<FilingsResponse>({
      data: { data: FILINGS, meta: META },
      isSuccess: true,
    }),
  );
  mockUseStatement.mockReset();
  mockUseStatement.mockReturnValue(
    queryResult<StatementResponse>({
      data: { data: STATEMENT, meta: META },
      isSuccess: true,
    }),
  );
  mockUseSection.mockReset();
  mockUseSection.mockReturnValue(
    queryResult<SectionResponse>({
      data: { data: SECTION, meta: META },
      isSuccess: true,
    }),
  );
});

function renderTab() {
  return render(
    <ThemeProvider>
      <FilingsTab ticker="AAPL" />
    </ThemeProvider>,
  );
}

test("renders one row per filing with form badges", async () => {
  await renderTab();
  expect(screen.getByTestId("filing-0000320193-24-000123")).toBeTruthy();
  expect(screen.getByTestId("filing-0000320193-24-000200")).toBeTruthy();
  expect(screen.getAllByText("10-K")).toHaveLength(2); // chip + badge
  expect(screen.getAllByText("8-K")).toHaveLength(2);
  expect(screen.getByText("A")).toBeTruthy(); // amended chip
});

test("selecting a filing opens the preview without fetching", async () => {
  await renderTab();
  await fireEvent.press(screen.getByTestId("filing-0000320193-24-000123"));
  expect(screen.getByTestId("filing-preview")).toBeTruthy();
  // No auto-fetch: the last statement hook call still has enabled=false.
  expect(mockUseStatement.mock.calls.at(-1)?.[2]).toBe(false);
  expect(screen.queryByTestId("statement-preview")).toBeNull();
});

test("Statements → Balance Sheet fetches and renders the lines", async () => {
  await renderTab();
  await fireEvent.press(screen.getByTestId("filing-0000320193-24-000123"));
  await fireEvent.press(screen.getByText("Statements"));
  expect(mockUseStatement.mock.calls.at(-1)?.[2]).toBe(true);
  expect(screen.getByTestId("statement-preview")).toBeTruthy();
  expect(screen.getByText("Cash and cash equivalents")).toBeTruthy();
  expect(screen.getByText("$29,943")).toBeTruthy();
  await fireEvent.press(screen.getByText("Income"));
  expect(mockUseStatement.mock.calls.at(-1)?.[1]).toBe("income_statement");
});

test("Narrative → Risk Factors fetches and renders the section", async () => {
  await renderTab();
  await fireEvent.press(screen.getByTestId("filing-0000320193-24-000123"));
  await fireEvent.press(screen.getByText("Narrative"));
  expect(mockUseSection.mock.calls.at(-1)?.[2]).toBe(true);
  expect(screen.getByTestId("section-preview")).toBeTruthy();
  expect(screen.getByText("Item 1A. Risk Factors")).toBeTruthy();
  expect(screen.getByText("Load full section")).toBeTruthy();
});

test("statement warnings render as a banner", async () => {
  mockUseStatement.mockReturnValue(
    queryResult<StatementResponse>({
      data: {
        data: {
          ...STATEMENT,
          warnings: ["Statement not found in filing."],
          lines: [],
        },
        meta: META,
      },
      isSuccess: true,
    }),
  );
  await renderTab();
  await fireEvent.press(screen.getByTestId("filing-0000320193-24-000123"));
  await fireEvent.press(screen.getByText("Statements"));
  expect(screen.getByTestId("filing-warning")).toBeTruthy();
  expect(screen.getByText("⚠ Statement not found in filing.")).toBeTruthy();
});

test("form and year filters update the query", async () => {
  await renderTab();
  await fireEvent.press(screen.getByTestId("filter-form-8-K"));
  expect(mockUseFilings.mock.calls.at(-1)?.[1]?.form).toBe("8-K");
  await fireEvent.press(screen.getByTestId("filter-year-2024"));
  expect(mockUseFilings.mock.calls.at(-1)?.[1]?.year).toBe(2024);
});
