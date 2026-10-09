import { Pressable, StyleSheet, View } from "react-native";

import type { ScreenerRow } from "../api/screener";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { verdictColor } from "../theme/verdicts";
import { abbreviateCurrency, DASH } from "../utils/format";

/** One screener result row: ticker/name, badges and key metrics. */
export function ScreenerRowCard({
  row,
  onPress,
}: {
  row: ScreenerRow;
  onPress: () => void;
}) {
  const theme = useTheme();
  const verdict = row.verdict ?? "N/A";
  const color = verdictColor(verdict, theme);
  const roe = row.roe === null ? DASH : `${(row.roe * 100).toFixed(1)}%`;
  const pe = row.pe === null ? DASH : row.pe.toFixed(1);

  return (
    <Pressable
      testID={`screener-row-${row.ticker}`}
      onPress={onPress}
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border },
      ]}
    >
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <ThemedText style={styles.ticker}>{row.ticker}</ThemedText>
          <ThemedText muted numberOfLines={1} style={styles.name}>
            {row.name ?? "Unknown name"}
          </ThemedText>
        </View>
        <View style={[styles.badge, { borderColor: color }]}>
          <ThemedText style={{ color, fontSize: 12 }}>{verdict}</ThemedText>
        </View>
      </View>

      <View style={styles.metrics}>
        <Metric label="Price" value={abbreviateCurrency(row.price)} />
        <Metric label="P/E" value={pe} />
        <Metric label="ROE" value={roe} />
      </View>

      <View style={styles.footer}>
        {row.category ? (
          <View style={[styles.categoryBadge, { borderColor: theme.border }]}>
            <ThemedText muted style={styles.categoryText}>
              {row.category}
            </ThemedText>
          </View>
        ) : null}
        {row.key_reason ? (
          <ThemedText muted numberOfLines={1} style={styles.reason}>
            {row.key_reason}
          </ThemedText>
        ) : null}
      </View>
    </Pressable>
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

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 10, padding: 12, gap: 8 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  headerLeft: { flex: 1, gap: 2 },
  ticker: { fontSize: 17, fontWeight: "700" },
  name: { fontSize: 13 },
  badge: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 2 },
  metrics: { flexDirection: "row", gap: 16 },
  metric: { gap: 2 },
  metricLabel: { fontSize: 11 },
  metricValue: { fontSize: 14, fontWeight: "600" },
  footer: { flexDirection: "row", alignItems: "center", gap: 8 },
  categoryBadge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 6 },
  categoryText: { fontSize: 11 },
  reason: { flex: 1, fontSize: 12 },
});
