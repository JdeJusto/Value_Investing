import { useState } from "react";
import { Pressable, StyleSheet, View, FlatList, RefreshControl } from "react-native";

import type { ConsensusCompany } from "../../src/api/consensus";
import { ConsensusRowCard } from "../../src/components/ConsensusRowCard";
import {
  useConsensusSnapshot,
  useConsensusRanking,
  useConsensusByCategory,
  useConsensusDisagreement,
} from "../../src/hooks/useConsensus";
import { ThemedText, ThemedView } from "../../src/theme/Themed";
import { useTheme } from "../../src/theme/ThemeProvider";
import { SkeletonCards, ErrorNote } from "../../src/components/StateViews";
import { abbreviateCurrency } from "../../src/utils/format";
import { router } from "expo-router";

const TABS = ["Top", "By Category", "Disagreement"] as const;
type ConsensusTab = (typeof TABS)[number];

function renderRow(item: ConsensusCompany) {
  return (
    <ConsensusRowCard
      row={item}
      onPress={() =>
        router.push({
          pathname: "/company/[ticker]",
          params: { ticker: item.ticker },
        })
      }
    />
  );
}

function buildCategoryRows(categories: Record<string, ConsensusCompany[]>): Array<{ category: string; companies: ConsensusCompany[] }> {
  return Object.entries(categories)
    .filter(([, companies]) => companies.length > 0)
    .map(([category, companies]) => ({ category, companies }));
}

function renderCategorySection({
  item,
}: {
  item: { category: string; companies: ConsensusCompany[] };
}) {
  return (
    <View style={styles.categorySection}>
      <View style={styles.categoryHeader}>
        <ThemedText style={styles.categoryTitle}>
          {item.category} ({item.companies.length})
        </ThemedText>
      </View>
      <FlatList
        data={item.companies}
        keyExtractor={(c) => c.ticker}
        renderItem={({ item }) => renderRow(item)}
        ListFooterComponent={() => null}
      />
    </View>
  );
}

export default function ConsensusScreen() {
  const theme = useTheme();
  const [tab, setTab] = useState<ConsensusTab>("Top");

  const snapshot = useConsensusSnapshot();
  const ranking = useConsensusRanking({ top: 100 });
  const byCategory = useConsensusByCategory({ per_category: 5 });
  const disagreement = useConsensusDisagreement({ min_buy: 3, max_buy: 4 });

  const isLoading =
    tab === "Top"
      ? ranking.isPending
      : tab === "By Category"
      ? byCategory.isPending
      : disagreement.isPending;
  const isRefetching =
    tab === "Top"
      ? ranking.isRefetching
      : tab === "By Category"
      ? byCategory.isRefetching
      : disagreement.isRefetching;
  const hasRows =
    tab === "Top"
      ? (ranking.data?.data.rows?.length ?? 0) > 0
      : tab === "By Category"
      ? (byCategory.data?.data.categories &&
          Object.values(byCategory.data.data.categories).some((c) => c.length > 0))
      : (disagreement.data?.data.rows?.length ?? 0) > 0;

  return (
    <ThemedView>
      <View style={styles.header}>
        <ThemedText style={styles.title}>Consensus</ThemedText>
        {snapshot.data && (
          <View style={styles.snapshotInfo}>
            <ThemedText muted style={styles.snapshotLabel}>
              Snapshot: {snapshot.data.data.date}
            </ThemedText>
            <ThemedText muted style={styles.snapshotLabel}>
              Universe: {snapshot.data.data.universe}
            </ThemedText>
            <ThemedText muted style={styles.snapshotLabel}>
              {snapshot.data.data.count} companies
            </ThemedText>
            <ThemedText muted style={styles.snapshotLabel}>
              BUY: {snapshot.data.data.buy_distribution["4+"] ?? 0} |{" "}
              {snapshot.data.data.buy_distribution["3"] ?? 0} |{" "}
              {snapshot.data.data.buy_distribution["2"] ?? 0} |{" "}
              {snapshot.data.data.buy_distribution["1"] ?? 0} |{" "}
              {snapshot.data.data.buy_distribution["0"] ?? 0}
            </ThemedText>
          </View>
        )}
      </View>

      <View style={styles.tabBar}>
        {TABS.map((name) => {
          const active = name === tab;
          return (
            <Pressable
              key={name}
              onPress={() => setTab(name)}
              style={[
                styles.tabButton,
                active && { backgroundColor: theme.accent },
              ]}
            >
              <ThemedText style={active ? styles.tabActive : undefined}>
                {name}
              </ThemedText>
            </Pressable>
          );
        })}
      </View>

      {tab === "Top" ? (
        <FlatList
          testID="consensus-list-top"
          data={ranking.data?.data.rows ?? []}
          keyExtractor={(item) => item.ticker}
          renderItem={({ item }) => renderRow(item)}
          ListFooterComponent={
            isRefetching ? (
              <View style={styles.footer}>
                <ThemedText muted>Loading more…</ThemedText>
              </View>
            ) : !isLoading && !hasRows ? (
              <View style={styles.footer}>
                <ThemedText muted>No companies in this view.</ThemedText>
              </View>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={ranking.isRefetching}
              onRefresh={() => ranking.refetch()}
              tintColor={theme.accent}
            />
          }
          contentContainerStyle={styles.list}
        />
      ) : tab === "By Category" ? (
        <FlatList
          testID="consensus-list-category"
          data={buildCategoryRows(byCategory.data?.data.categories ?? {})}
          keyExtractor={(item) => item.category}
          renderItem={renderCategorySection}
          ListFooterComponent={
            isRefetching ? (
              <View style={styles.footer}>
                <ThemedText muted>Loading more…</ThemedText>
              </View>
            ) : !isLoading && !hasRows ? (
              <View style={styles.footer}>
                <ThemedText muted>No companies in this view.</ThemedText>
              </View>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={byCategory.isRefetching}
              onRefresh={() => byCategory.refetch()}
              tintColor={theme.accent}
            />
          }
          contentContainerStyle={styles.list}
          ItemSeparatorComponent={() => <View style={styles.categorySeparator} />}
        />
      ) : (
        <FlatList
          testID="consensus-list-disagreement"
          data={disagreement.data?.data.rows ?? []}
          keyExtractor={(item) => item.ticker}
          renderItem={({ item }) => renderRow(item)}
          ListFooterComponent={
            isRefetching ? (
              <View style={styles.footer}>
                <ThemedText muted>Loading more…</ThemedText>
              </View>
            ) : !isLoading && !hasRows ? (
              <View style={styles.footer}>
                <ThemedText muted>No companies in this view.</ThemedText>
              </View>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={disagreement.isRefetching}
              onRefresh={() => disagreement.refetch()}
              tintColor={theme.accent}
            />
          }
          contentContainerStyle={styles.list}
        />
      )}

      {snapshot.isError && <ErrorNote error={snapshot.error} />}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  header: { padding: 16, gap: 8 },
  title: { fontSize: 20, fontWeight: "700" },
  snapshotInfo: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  snapshotLabel: { fontSize: 12 },
  tabBar: {
    flexDirection: "row",
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 8,
  },
  tabButton: {
    borderWidth: 1,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  tabActive: { color: "#fff", fontWeight: "600" },
  list: { padding: 16, gap: 10 },
  footer: { padding: 16, alignItems: "center" },
  categorySection: { gap: 6 },
  categoryHeader: { paddingHorizontal: 4 },
  categoryTitle: { fontSize: 16, fontWeight: "600" },
  categorySeparator: { height: 16 },
});