import type { UseQueryResult } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";

import type { ApiEnvelope } from "../../src/api/client";
import type { CompanyResponse } from "../../src/api/company";
import { DCFTab } from "../../src/components/DCFTab";
import { MethodologiesTab } from "../../src/components/MethodologiesTab";
import { useCompany } from "../../src/hooks/useCompany";
import { useDCF } from "../../src/hooks/useDCF";
import { useMethodologies } from "../../src/hooks/useMethodologies";
import { ThemedText, ThemedView } from "../../src/theme/Themed";
import { useTheme } from "../../src/theme/ThemeProvider";
import { abbreviateCurrency } from "../../src/utils/format";

const TABS = [
  "Overview",
  "Methodologies",
  "DCF",
  "Financials",
  "Filings",
] as const;

type Tab = (typeof TABS)[number];

type CompanyQuery = UseQueryResult<ApiEnvelope<CompanyResponse>, Error>;

export default function CompanyScreen() {
  const theme = useTheme();
  const params = useLocalSearchParams<{ ticker?: string }>();
  const normalized = (params.ticker ?? "").toUpperCase();
  const query = useCompany(normalized);
  const methodologiesQuery = useMethodologies(normalized);
  const dcfQuery = useDCF(normalized);
  const [tab, setTab] = useState<Tab>("Overview");

  return (
    <ThemedView>
      <Stack.Screen options={{ title: normalized || "Company" }} />

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={[styles.segment, { borderColor: theme.border }]}
      >
        {TABS.map((name) => {
          const active = name === tab;
          return (
            <Pressable
              key={name}
              onPress={() => setTab(name)}
              style={[
                styles.segmentItem,
                active && { backgroundColor: theme.accent },
              ]}
            >
              <ThemedText style={active ? styles.segmentActive : undefined}>
                {name}
              </ThemedText>
            </Pressable>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={
              query.isRefetching ||
              methodologiesQuery.isRefetching ||
              dcfQuery.isRefetching
            }
            onRefresh={() => {
              void query.refetch();
              void methodologiesQuery.refetch();
              void dcfQuery.refetch();
            }}
            tintColor={theme.accent}
          />
        }
      >
        {tab === "Overview" ? (
          <OverviewTab query={query} />
        ) : tab === "Methodologies" ? (
          <MethodologiesTab query={methodologiesQuery} ticker={normalized} />
        ) : tab === "DCF" ? (
          <DCFTab query={dcfQuery} ticker={normalized} />
        ) : (
          <View style={styles.comingSoon}>
            <ThemedText muted>{tab} — coming soon.</ThemedText>
            <ThemedText muted>
              API endpoint pending (Phase 2+ of issue #27).
            </ThemedText>
          </View>
        )}
      </ScrollView>
    </ThemedView>
  );
}

function OverviewTab({ query }: { query: CompanyQuery }) {
  const theme = useTheme();
  const company = query.data?.data;

  if (query.isLoading) {
    return <ThemedText muted>Loading…</ThemedText>;
  }
  if (query.isError) {
    return (
      <ThemedText style={{ color: theme.danger }}>
        Could not load this company. Pull to refresh.
      </ThemedText>
    );
  }
  if (!company) {
    return null;
  }

  const rows: [string, string][] = [
    ["Name", company.name ?? "—"],
    ["Sector", company.sector ?? "—"],
    ["Price", abbreviateCurrency(company.price)],
    ["Market cap", abbreviateCurrency(company.market_cap)],
    [
      "Fiscal year",
      company.fiscal_year !== null ? String(company.fiscal_year) : "—",
    ],
    ["CIK", company.cik ?? "—"],
    ["Currency", company.currency ?? "—"],
  ];

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border },
      ]}
    >
      {rows.map(([label, value]) => (
        <View key={label} style={styles.row}>
          <ThemedText muted>{label}</ThemedText>
          <ThemedText style={styles.rowValue}>{value}</ThemedText>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  segment: {
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  segmentItem: {
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  segmentActive: { color: "#ffffff", fontWeight: "600" },
  content: { padding: 16, gap: 12 },
  card: { borderWidth: 1, borderRadius: 10, padding: 14, gap: 10 },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  rowValue: { flexShrink: 1, textAlign: "right" },
  comingSoon: { alignItems: "center", paddingTop: 48, gap: 6 },
});
