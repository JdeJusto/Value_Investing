import {
  abbreviateCurrency,
  abbreviateNumber,
  DASH,
  formatPercent,
  formatScore,
} from "../format";

test("abbreviates large currency values with K/M/B/T", () => {
  expect(abbreviateCurrency(416_161_000_000)).toBe("$416.16B");
  expect(abbreviateCurrency(4_913_422_663_680)).toBe("$4.91T");
  expect(abbreviateCurrency(14_776_000_000)).toBe("$14.78B");
  expect(abbreviateCurrency(1_234_000)).toBe("$1.23M");
});

test("renders negatives in parentheses", () => {
  expect(abbreviateCurrency(-19_001_000_000)).toBe("($19.00B)");
});

test("keeps small values with two decimals", () => {
  expect(abbreviateCurrency(42.15)).toBe("$42.15");
  expect(abbreviateCurrency(336.67)).toBe("$336.67");
});

test("null renders as the em dash and zero as 0", () => {
  expect(abbreviateCurrency(null)).toBe(DASH);
  expect(abbreviateCurrency(0)).toBe("0");
});

test("promotes a scaled value that rounds up to 1000", () => {
  expect(abbreviateCurrency(999_999)).toBe("$1.00M");
  expect(abbreviateCurrency(999_999_999)).toBe("$1.00B");
});

test("abbreviateNumber drops the currency symbol", () => {
  expect(abbreviateNumber(416_161_000_000)).toBe("416.16B");
  expect(abbreviateNumber(-19_001_000_000)).toBe("(19.00B)");
  expect(abbreviateNumber(null)).toBe(DASH);
});

test("formatScore keeps two decimals and maps null to the em dash", () => {
  expect(formatScore(28.57)).toBe("28.57");
  expect(formatScore(100)).toBe("100.00");
  expect(formatScore(null)).toBe(DASH);
});

test("formatPercent renders percentages", () => {
  expect(formatPercent(-1.411)).toBe("-141%");
  expect(formatPercent(0.085, 2)).toBe("8.50%");
  expect(formatPercent(null)).toBe(DASH);
});
