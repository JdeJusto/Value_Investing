import { Pressable, StyleSheet, View } from "react-native";

import type { PortfolioPosition } from "../api/portfolio";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { verdictColor } from "../theme/verdicts";
import { abbreviateCurrency, formatPercent, DASH } from "../utils/format";

/** One portfolio position row with PnL and signal badge. */
export function PortfolioRowCard({
  row,
  onPress,
}: {
  row: PortfolioPosition;
  onPress: () => void;
}) {
  const theme = useTheme();
  const signal = row.signal_at_entry ?? row.signal ?? "—";
  const color = verdictColor(signal, theme);
  const pnl = row.pnl;
  const pnlPct = row.pnl_pct;
  const pnlColor =
    pnl !== null && pnl > 0
      ? "#3bb273"
      : pnl !== null && pnl < 0
      ? "#e63946"
      : theme.text;

  return (
    <Pressable
      testID={`portfolio-row-${row.ticker}`}
      onPress={onPress}
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border },
      ]}
    >
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <ThemedText style={styles.ticker}>{row.ticker}</ThemedText>
          <ThemedText muted style={styles.shares}>
            {row.shares} sh @ {abbreviateCurrency(row.avg_price)}
          </ThemedText>
        </View>
        <View style={[styles.badge, { borderColor: color }]}>
          <ThemedText style={{ color, fontSize: 11 }}>{signal}</ThemedText>
        </View>
      </View>

      <View style={styles.metrics}>
        <Metric
          label="Current"
          value={abbreviateCurrency(row.current_price)}
        />
        <Metric
          label="Value"
          value={abbreviateCurrency(row.value)}
        />
        <Metric
          label="PnL"
          value={pnl === null ? DASH : abbreviateCurrency(pnl)}
          valueColor={pnlColor}
        />
        <Metric
          label="%"
          value={pnlPct === null ? DASH : formatPercent(pnlPct)}
          valueColor={pnlColor}
        />
      </View>

      <View style={styles.footer}>
        {row.thesis && (
          <ThemedText muted numberOfLines={1} style={styles.thesis}>
            {row.thesis}
          </ThemedText>
        )}
        {row.price_source && (
          <ThemedText muted style={styles.priceSource}>
            {row.price_source === "live" ? "🔴 Live" : "⚪ Stored"}
          </ThemedText>
        )}
      </View>
    </Pressable>
  );
}

function Metric({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <View style={styles.metric}>
      <ThemedText muted style={styles.metricLabel}>{label}</ThemedText>
      <ThemedText
        style={[
          styles.metricValue,
          valueColor ? { color: valueColor } : undefined,
        ]}
      >
        {value}
      </ThemedText>
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
  shares: { fontSize: 12 },
  badge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  metrics: { flexDirection: "row", gap: 16 },
  metric: { gap: 2 },
  metricLabel: { fontSize: 11 },
  metricValue: { fontSize: 14, fontWeight: "600" },
  footer: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  thesis: { flex: 1, fontSize: 12 },
  priceSource: { fontSize: 11 },
});