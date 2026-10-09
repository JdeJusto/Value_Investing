import { useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from "react-native";

import type { ScreenerFilterParams, ScreenerRow } from "../../src/api/screener";
import { ScreenerFilterSheet } from "../../src/components/ScreenerFilterSheet";
import { ScreenerRowCard } from "../../src/components/ScreenerRowCard";
import { useScreener } from "../../src/hooks/useScreener";
import { ThemedText, ThemedView } from "../../src/theme/Themed";
import { useTheme } from "../../src/theme/ThemeProvider";
import { SkeletonCards, ErrorNote } from "../../src/components/StateViews";
import { router } from "expo-router";

export const SCREENER_DEFAULT_FILTERS: ScreenerFilterParams = {
  universe: "sp500",
};

export default function ScreenerScreen() {
  const theme = useTheme();
  const [filters, setFilters] = useState<ScreenerFilterParams>(
    SCREENER_DEFAULT_FILTERS
  );
  const [hasRun, setHasRun] = useState(false);
  const [showSheet, setShowSheet] = useState(false);

  const query = useScreener(filters, hasRun);

  function handleRun() {
    setHasRun(true);
    setShowSheet(false);
  }

  function renderRow({ item }: { item: ScreenerRow }) {
    return (
      <ScreenerRowCard
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

  const data = query.data;
  const allRows = data?.pages.flatMap((p) => p.data.rows) ?? [];
  const isLoading = query.isPending;
  const isRefetching = query.isFetchingNextPage;
  const hasRows = allRows.length > 0;

  return (
    <ThemedView>
      <View style={styles.header}>
        <ThemedText style={styles.title}>Screener</ThemedText>
        <Pressable
          testID="filters-button"
          onPress={() => setShowSheet(true)}
          style={styles.filterButton}
        >
          <ThemedText>Filters</ThemedText>
        </Pressable>
      </View>

      {!hasRun ? (
        <ThemedView center style={styles.empty}>
          <ThemedText muted style={styles.hint}>
            Adjust filters and tap Run to screen the universe.
          </ThemedText>
        </ThemedView>
      ) : isLoading ? (
        <ThemedView center style={styles.loading}>
          <SkeletonCards count={5} />
        </ThemedView>
      ) : !hasRows ? (
        <ThemedView center style={styles.empty}>
          <ThemedText muted>No companies match the filters.</ThemedText>
        </ThemedView>
      ) : query.isError ? (
        <ErrorNote error={query.error} />
      ) : (
        <FlatList
          testID="screener-list"
          data={allRows}
          keyExtractor={(item) => item.ticker}
          renderItem={renderRow}
          ListFooterComponent={
            isRefetching ? (
              <View style={styles.footer}>
                <ThemedText muted>Loading more…</ThemedText>
              </View>
            ) : (
              <View style={styles.footer}>
                <ThemedText muted>
                  {allRows.length} of {data?.pages[0].data.count ?? 0} — page{" "}
                  {data?.pages[0].data.page ?? 1} /{" "}
                  {data?.pages[0].data.total_pages ?? 1}
                </ThemedText>
              </View>
            )
          }
          onEndReached={() => {
            if (!isRefetching && query.hasNextPage) {
              query.fetchNextPage();
            }
          }}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl
              refreshing={query.isRefetching}
              onRefresh={() => query.refetch()}
              tintColor={theme.accent}
            />
          }
          contentContainerStyle={styles.list}
        />
      )}

      {showSheet && (
        <ScreenerFilterSheet
          filters={filters}
          onChange={setFilters}
          onRun={handleRun}
        />
      )}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
  },
  title: { fontSize: 20, fontWeight: "700" },
  filterButton: {
    borderWidth: 1,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  empty: { flex: 1, gap: 8, padding: 24 },
  hint: { textAlign: "center", fontSize: 15 },
  loading: { flex: 1 },
  list: { padding: 16, gap: 10 },
  footer: { padding: 16, alignItems: "center" },
});