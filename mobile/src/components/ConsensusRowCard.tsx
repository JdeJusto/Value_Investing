import { Pressable, StyleSheet, View } from "react-native";

import type { ConsensusCompany } from "../api/consensus";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { verdictColor } from "../theme/verdicts";
import { abbreviateCurrency } from "../utils/format";

/** One consensus ranking row with badges and verdict string. */
export function ConsensusRowCard({
  row,
  onPress,
}: {
  row: ConsensusCompany;
  onPress: () => void;
}) {
  const theme = useTheme();
  const verdictString = row.verdict_string || "";
  const verdictParts = verdictString.split("/");
  const firstVerdict = verdictParts[0] ?? "—";
  const color = verdictColor(firstVerdict, theme);

  return (
    <Pressable
      testID={`consensus-row-${row.ticker}`}
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
        <View style={styles.badgeRow}>
          <View style={[styles.badge, { borderColor: color }]}>
            <ThemedText style={{ color, fontSize: 12 }}>{firstVerdict}</ThemedText>
          </View>
          <View style={styles.categoryBadge}>
            <ThemedText muted style={styles.categoryText}>
              {row.category}
            </ThemedText>
          </View>
        </View>
      </View>

      <View style={styles.metrics}>
        <Metric label="Score" value={row.consensus_score.toString()} />
        <Metric label="BUY" value={row.buy_count.toString()} />
        <Metric label="AVOID" value={row.avoid_count.toString()} />
        <Metric label="Price" value={abbreviateCurrency(row.price)} />
      </View>

      <ThemedText muted style={styles.verdictString} numberOfLines={1}>
        {verdictString}
      </ThemedText>
    </Pressable>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <ThemedText muted style={styles.metricLabel}>{label}</ThemedText>
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
  badgeRow: { flexDirection: "row", gap: 6, alignItems: "center" },
  badge: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 2 },
  categoryBadge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 6, paddingVertical: 2 },
  categoryText: { fontSize: 11 },
  metrics: { flexDirection: "row", gap: 16 },
  metric: { gap: 2 },
  metricLabel: { fontSize: 11 },
  metricValue: { fontSize: 14, fontWeight: "600" },
  verdictString: { fontSize: 11, fontFamily: "monospace" },
});