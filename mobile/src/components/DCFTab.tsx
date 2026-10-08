import type { UseQueryResult } from "@tanstack/react-query";
import { StyleSheet, View } from "react-native";

import type { ApiEnvelope } from "../api/client";
import type { DCFResponse, DCFSensitivityRow } from "../api/company";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { dcfVerdictColor } from "../theme/verdicts";
import { abbreviateCurrency, formatPercent } from "../utils/format";
import { ErrorNote, SkeletonCards } from "./StateViews";

type DCFQuery = UseQueryResult<ApiEnvelope<DCFResponse>, Error>;

const VARIANT_LABELS: Record<string, string> = {
  standard: "standard (free cash flow)",
  reit: "REIT (FFO)",
  ddm_financial: "financial (DDM)",
  ddm_financial_two_stage: "financial (two-stage DDM)",
  hyper_growth: "hyper-growth",
};

const VERDICT_SHORT: Record<string, string> = {
  UNDERVALUED: "UNDER",
  FAIR: "FAIR",
  OVERVALUED: "OVER",
  INSUFFICIENT_DATA: "INSUFFICIENT",
};

export function DCFTab({
  query,
  ticker,
}: {
  query: DCFQuery;
  ticker: string;
}) {
  const theme = useTheme();

  if (query.isLoading) {
    return <SkeletonCards count={3} />;
  }
  if (query.isError) {
    return <ErrorNote error={query.error} ticker={ticker} />;
  }
  const data = query.data?.data;
  if (!data) {
    return null;
  }

  const insufficient = data.verdict === "INSUFFICIENT_DATA";

  return (
    <View style={styles.wrap}>
      <View style={styles.headerRow}>
        <ThemedText style={styles.title}>DCF valuation</ThemedText>
        <View style={[styles.disclaimer, { borderColor: theme.border }]}>
          <ThemedText muted style={styles.disclaimerText}>
            {data.source}
          </ThemedText>
        </View>
      </View>
      <ThemedText muted>
        Variant: {VARIANT_LABELS[data.variant] ?? data.variant}
      </ThemedText>

      {insufficient ? (
        <View
          testID="dcf-insufficient"
          style={[
            styles.card,
            { backgroundColor: theme.card, borderColor: theme.border },
          ]}
        >
          <ThemedText>Not enough data to value this company.</ThemedText>
          {data.reasons.map((reason, index) => (
            <ThemedText key={index} muted style={styles.reason}>
              • {reason}
            </ThemedText>
          ))}
        </View>
      ) : (
        <>
          <View style={styles.metricsRow} testID="dcf-metrics">
            <Metric
              label="Intrinsic value"
              value={abbreviateCurrency(data.intrinsic_value)}
            />
            <Metric
              label="Current price"
              value={abbreviateCurrency(data.current_price)}
            />
            <Metric
              label="Margin of safety"
              value={formatPercent(data.margin_of_safety)}
            />
          </View>

          <View style={styles.verdictRow}>
            <View
              style={[
                styles.badge,
                { backgroundColor: dcfVerdictColor(data.verdict, theme) },
              ]}
            >
              <ThemedText style={styles.badgeText}>
                {VERDICT_SHORT[data.verdict] ?? data.verdict}
              </ThemedText>
            </View>
          </View>

          <View
            testID="dcf-assumptions"
            style={[
              styles.card,
              { backgroundColor: theme.card, borderColor: theme.border },
            ]}
          >
            <ThemedText style={styles.cardTitle}>Assumptions</ThemedText>
            <Row label="WACC" value={formatPercent(data.wacc, 2)} />
            <Row
              label="FCF base"
              value={abbreviateCurrency(data.assumptions.fcf_base)}
            />
            <Row
              label="Growth 1-5"
              value={formatPercent(data.assumptions.growth_1_5, 2)}
            />
            <Row
              label="Growth 6-10"
              value={formatPercent(data.assumptions.growth_6_10, 2)}
            />
            <Row
              label="Terminal growth"
              value={formatPercent(data.assumptions.terminal_growth, 2)}
            />
          </View>

          <SensitivityTable rows={data.sensitivity} />

          {data.reasons.length > 0 ? (
            <View
              style={[
                styles.card,
                { backgroundColor: theme.card, borderColor: theme.border },
              ]}
            >
              <ThemedText style={styles.cardTitle}>Notes</ThemedText>
              {data.reasons.map((reason, index) => (
                <ThemedText key={index} muted style={styles.reason}>
                  • {reason}
                </ThemedText>
              ))}
            </View>
          ) : null}
        </>
      )}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <ThemedText muted style={styles.metricLabel}>
        {label}
      </ThemedText>
      <ThemedText style={styles.metricValue}>{value}</ThemedText>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <ThemedText muted>{label}</ThemedText>
      <ThemedText>{value}</ThemedText>
    </View>
  );
}

function SensitivityTable({ rows }: { rows: DCFSensitivityRow[] }) {
  const theme = useTheme();
  if (rows.length === 0) {
    return null;
  }
  const waccs = [...new Set(rows.map((row) => row.wacc))].sort((a, b) => a - b);
  const growths = [...new Set(rows.map((row) => row.growth))].sort(
    (a, b) => a - b,
  );
  const values = new Map(
    rows.map((row) => [`${row.wacc}|${row.growth}`, row.value]),
  );
  const baseWacc = waccs[1];
  const baseGrowth = growths[1];

  return (
    <View
      testID="sensitivity-table"
      style={[styles.table, { borderColor: theme.border }]}
    >
      <View style={styles.tableRow}>
        <Cell text="" header />
        {growths.map((growth) => (
          <Cell key={growth} text={formatPercent(growth, 1)} header />
        ))}
      </View>
      {waccs.map((wacc) => (
        <View key={wacc} style={styles.tableRow}>
          <Cell text={formatPercent(wacc, 1)} header />
          {growths.map((growth) => {
            const value = values.get(`${wacc}|${growth}`);
            return (
              <Cell
                key={growth}
                text={
                  value === null || value === undefined
                    ? "—"
                    : abbreviateCurrency(value)
                }
                highlight={wacc === baseWacc && growth === baseGrowth}
              />
            );
          })}
        </View>
      ))}
    </View>
  );
}

function Cell({
  text,
  header = false,
  highlight = false,
}: {
  text: string;
  header?: boolean;
  highlight?: boolean;
}) {
  const theme = useTheme();
  return (
    <View
      style={[
        styles.cell,
        { borderColor: theme.border },
        header && { backgroundColor: theme.card },
        highlight && { backgroundColor: theme.accent },
      ]}
    >
      <ThemedText
        style={[styles.cellText, highlight && styles.cellTextHighlight]}
      >
        {text}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  title: { fontSize: 18, fontWeight: "700" },
  disclaimer: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  disclaimerText: { fontSize: 11 },
  metricsRow: { flexDirection: "row", gap: 8 },
  metric: { flex: 1, gap: 2 },
  metricLabel: { fontSize: 11 },
  metricValue: { fontSize: 16, fontWeight: "600" },
  verdictRow: { flexDirection: "row" },
  badge: { borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4 },
  badgeText: { color: "#ffffff", fontSize: 12, fontWeight: "700" },
  card: { borderWidth: 1, borderRadius: 10, padding: 12, gap: 6 },
  cardTitle: { fontSize: 14, fontWeight: "600", marginBottom: 2 },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 10 },
  reason: { fontSize: 12, lineHeight: 17 },
  table: { borderWidth: 1, borderRadius: 8, overflow: "hidden" },
  tableRow: { flexDirection: "row" },
  cell: {
    flex: 1,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 6,
    paddingHorizontal: 4,
    alignItems: "center",
  },
  cellText: { fontSize: 11 },
  cellTextHighlight: { color: "#ffffff", fontWeight: "700" },
});
