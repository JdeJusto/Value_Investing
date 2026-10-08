import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from "react-native";

import type { ApiEnvelope } from "../api/client";
import type {
  FinancialsResponse,
  InsightsMetric,
  InsightsResponse,
} from "../api/company";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import type { Theme } from "../theme";
import { ErrorNote, SkeletonCards } from "./StateViews";

type FinancialsQuery = UseQueryResult<ApiEnvelope<FinancialsResponse>, Error>;
type InsightsQuery = UseQueryResult<ApiEnvelope<InsightsResponse>, Error>;

const SECTIONS = [
  { key: "balance_sheet", label: "Balance Sheet" },
  { key: "income_statement", label: "Income Statement" },
  { key: "cash_flow", label: "Cash Flow" },
  { key: "other", label: "Other" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

export function FinancialsTab({
  financialsQuery,
  insightsQuery,
  ticker,
}: {
  financialsQuery: FinancialsQuery;
  insightsQuery: InsightsQuery;
  ticker: string;
}) {
  const theme = useTheme();
  const [section, setSection] = useState<SectionKey>("balance_sheet");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  if (financialsQuery.isLoading) {
    return <SkeletonCards count={4} />;
  }
  if (financialsQuery.isError) {
    return <ErrorNote error={financialsQuery.error} ticker={ticker} />;
  }
  const data = financialsQuery.data?.data;
  if (!data) {
    return null;
  }

  const rows = data[section];
  const years = data.years;

  return (
    <View style={styles.wrap}>
      <InsightsSummary
        query={insightsQuery}
        search={search}
        onSearch={setSearch}
        expanded={expanded}
        onToggle={(metric) =>
          setExpanded((current) => (current === metric ? null : metric))
        }
      />

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.segmentScroll}
        contentContainerStyle={styles.segment}
      >
        {SECTIONS.map((item) => {
          const active = item.key === section;
          return (
            <Pressable
              key={item.key}
              testID={`financials-tab-${item.key}`}
              onPress={() => setSection(item.key)}
              style={[
                styles.segmentItem,
                active && { backgroundColor: theme.accent },
              ]}
            >
              <ThemedText style={active ? styles.segmentActive : undefined}>
                {item.label} ({data.counts[item.key]})
              </ThemedText>
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={styles.table}>
        <View style={styles.labelColumn}>
          <View style={[styles.headerCell, { borderColor: theme.border }]}>
            <ThemedText style={styles.headerText}>Line item</ThemedText>
          </View>
          {rows.map((row) => (
            <View
              key={row.concept}
              style={[styles.labelCell, { borderColor: theme.border }]}
            >
              <ThemedText numberOfLines={1} style={styles.labelText}>
                {row.label}
              </ThemedText>
            </View>
          ))}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View>
            <View style={styles.row}>
              {years.map((year) => (
                <View
                  key={year}
                  style={[styles.headerCell, { borderColor: theme.border }]}
                >
                  <ThemedText style={styles.headerText}>FY{year}</ThemedText>
                </View>
              ))}
            </View>
            {rows.map((row) => (
              <View key={row.concept} style={styles.row}>
                {years.map((year) => (
                  <View
                    key={year}
                    style={[styles.valueCell, { borderColor: theme.border }]}
                  >
                    <ThemedText numberOfLines={1} style={styles.valueText}>
                      {row.values[String(year)] ?? "—"}
                    </ThemedText>
                  </View>
                ))}
              </View>
            ))}
          </View>
        </ScrollView>
      </View>

      <ThemedText muted style={styles.caption}>
        Source: Financial-DataBase (SEC EDGAR) · {data.period} data · Last{" "}
        {years.length} years
      </ThemedText>
    </View>
  );
}

function InsightsSummary({
  query,
  search,
  onSearch,
  expanded,
  onToggle,
}: {
  query: InsightsQuery;
  search: string;
  onSearch: (value: string) => void;
  expanded: string | null;
  onToggle: (metric: string) => void;
}) {
  const theme = useTheme();
  if (query.isLoading) {
    return <SkeletonCards count={2} />;
  }
  if (query.isError) {
    return <ErrorNote error={query.error} />;
  }
  const metrics = query.data?.data.metrics ?? [];
  const needle = search.trim().toLowerCase();
  const filtered = needle
    ? metrics.filter((metric) => metric.label.toLowerCase().includes(needle))
    : metrics;

  return (
    <View
      testID="insights-summary"
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border },
      ]}
    >
      <ThemedText style={styles.cardTitle}>Summary</ThemedText>
      <TextInput
        value={search}
        onChangeText={onSearch}
        placeholder="Search concepts"
        placeholderTextColor={theme.muted}
        autoCapitalize="none"
        autoCorrect={false}
        testID="insights-search"
        style={[
          styles.search,
          {
            color: theme.text,
            borderColor: theme.border,
            backgroundColor: theme.bg,
          },
        ]}
      />
      {filtered.map((metric) => (
        <InsightRow
          key={metric.metric}
          metric={metric}
          expanded={expanded === metric.metric}
          onToggle={() => onToggle(metric.metric)}
        />
      ))}
    </View>
  );
}

function InsightRow({
  metric,
  expanded,
  onToggle,
}: {
  metric: InsightsMetric;
  expanded: boolean;
  onToggle: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      testID={`insight-${metric.metric}`}
      onPress={onToggle}
      style={[styles.insightRow, { borderColor: theme.border }]}
    >
      <View style={styles.insightHeader}>
        <ThemedText style={styles.insightLabel}>{metric.label}</ThemedText>
        <ThemedText style={styles.insightValue}>
          {metric.latest_value ?? "—"}
        </ThemedText>
      </View>
      <View style={styles.chipsRow}>
        <Chip
          text={`YoY ${signedPercent(metric.yoy_change_pct)}`}
          color={changeColor(metric.yoy_change_pct, theme)}
        />
        <Chip
          text={`5y ${signedPercent(metric.cagr_5y)}`}
          color={theme.muted}
        />
        <Chip text={metric.trend} color={trendColor(metric.trend, theme)} />
        <Chip text={metric.stability} color={theme.muted} />
      </View>
      {expanded ? (
        <View
          testID={`insight-notes-${metric.metric}`}
          style={styles.notes}
        >
          {(metric.notes.length > 0 ? metric.notes : ["No notes."]).map(
            (note, index) => (
              <ThemedText key={index} muted style={styles.note}>
                • {note}
              </ThemedText>
            ),
          )}
        </View>
      ) : null}
    </Pressable>
  );
}

function Chip({ text, color }: { text: string; color: string }) {
  return (
    <View style={[styles.chip, { borderColor: color }]}>
      <ThemedText style={[styles.chipText, { color }]}>{text}</ThemedText>
    </View>
  );
}

function signedPercent(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

function changeColor(value: number | null, theme: Theme): string {
  if (value === null || value === undefined) {
    return theme.muted;
  }
  return value >= 0 ? theme.accent : theme.danger;
}

function trendColor(trend: string, theme: Theme): string {
  if (trend === "growing") {
    return theme.accent;
  }
  if (trend === "declining") {
    return theme.danger;
  }
  return theme.muted;
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  card: { borderWidth: 1, borderRadius: 10, padding: 12, gap: 8 },
  cardTitle: { fontSize: 14, fontWeight: "600" },
  search: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  insightRow: { borderTopWidth: StyleSheet.hairlineWidth, paddingTop: 8, gap: 4 },
  insightHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 8,
  },
  insightLabel: { fontSize: 13, fontWeight: "600" },
  insightValue: { fontSize: 13 },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 4 },
  chip: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 6, paddingVertical: 1 },
  chipText: { fontSize: 10 },
  notes: { gap: 2, paddingBottom: 4 },
  note: { fontSize: 11, lineHeight: 15 },
  segmentScroll: { flexGrow: 0, flexShrink: 0 },
  segment: { gap: 4, alignItems: "center" },
  segmentItem: { borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5 },
  segmentActive: { color: "#ffffff", fontWeight: "600" },
  table: { flexDirection: "row", borderWidth: 1, borderRadius: 8, overflow: "hidden" },
  labelColumn: { width: 132 },
  row: { flexDirection: "row" },
  headerCell: {
    height: 30,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 6,
    justifyContent: "center",
    minWidth: 92,
  },
  headerText: { fontSize: 11, fontWeight: "600" },
  labelCell: {
    height: 30,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 6,
    justifyContent: "center",
  },
  labelText: { fontSize: 11 },
  valueCell: {
    height: 30,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 6,
    justifyContent: "center",
    minWidth: 92,
    alignItems: "flex-end",
  },
  valueText: { fontSize: 11 },
  caption: { fontSize: 11 },
});
