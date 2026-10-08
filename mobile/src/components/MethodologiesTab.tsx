import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import type { ApiEnvelope } from "../api/client";
import type {
  MethodologiesResponse,
  MethodologiesSummary,
  MethodologyResult,
} from "../api/company";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { verdictColor } from "../theme/verdicts";
import { formatScore } from "../utils/format";
import { ErrorNote, SkeletonCards } from "./StateViews";

type MethodologiesQuery = UseQueryResult<
  ApiEnvelope<MethodologiesResponse>,
  Error
>;

const CHIPS: {
  label: string;
  verdict: string;
  countKey: keyof MethodologiesSummary;
}[] = [
  { label: "BUY", verdict: "BUY", countKey: "buy_count" },
  { label: "WATCH", verdict: "WATCH", countKey: "watch_count" },
  { label: "HOLD", verdict: "HOLD", countKey: "hold_count" },
  { label: "AVOID", verdict: "AVOID", countKey: "avoid_count" },
  { label: "N/A", verdict: "N/A", countKey: "na_count" },
  { label: "INS", verdict: "INSUFFICIENT_DATA", countKey: "insufficient_count" },
];

export function MethodologiesTab({
  query,
  ticker,
}: {
  query: MethodologiesQuery;
  ticker: string;
}) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState<string | null>(null);

  if (query.isLoading) {
    return <SkeletonCards count={4} />;
  }
  if (query.isError) {
    return <ErrorNote error={query.error} ticker={ticker} />;
  }
  const data = query.data?.data;
  if (!data) {
    return null;
  }

  const score = data.summary.consensus_score;
  const scoreColor = score >= 0 ? theme.accent : theme.danger;

  return (
    <View style={styles.wrap}>
      <View style={styles.chips} testID="methodology-summary">
        {CHIPS.map((chip) => {
          const color = verdictColor(chip.verdict, theme);
          return (
            <View
              key={chip.label}
              testID={`summary-chip-${chip.label}`}
              style={[
                styles.chip,
                { borderColor: color, backgroundColor: theme.card },
              ]}
            >
              <ThemedText style={[styles.chipLabel, { color }]}>
                {chip.label} {data.summary[chip.countKey]}
              </ThemedText>
            </View>
          );
        })}
      </View>

      <View style={styles.scoreRow}>
        <ThemedText muted>Consensus score</ThemedText>
        <ThemedText style={{ color: scoreColor }}>
          {score > 0 ? `+${score}` : String(score)}
        </ThemedText>
      </View>

      {data.methodologies.map((methodology) => (
        <MethodologyCard
          key={methodology.name}
          methodology={methodology}
          expanded={expanded === methodology.name}
          onToggle={() =>
            setExpanded((current) =>
              current === methodology.name ? null : methodology.name,
            )
          }
        />
      ))}
    </View>
  );
}

function MethodologyCard({
  methodology,
  expanded,
  onToggle,
}: {
  methodology: MethodologyResult;
  expanded: boolean;
  onToggle: () => void;
}) {
  const theme = useTheme();
  const color = verdictColor(methodology.verdict, theme);
  return (
    <Pressable
      testID={`methodology-card-${methodology.name}`}
      onPress={onToggle}
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border },
      ]}
    >
      <View style={styles.cardHeader}>
        <ThemedText style={styles.cardName}>{methodology.name}</ThemedText>
        <ThemedText muted style={styles.family}>
          {methodology.family}
        </ThemedText>
      </View>
      <View style={styles.cardMeta}>
        <View style={[styles.badge, { backgroundColor: color }]}>
          <ThemedText style={styles.badgeText}>{methodology.verdict}</ThemedText>
        </View>
        <ThemedText>Score: {formatScore(methodology.score)}</ThemedText>
        <ThemedText muted>{methodology.confidence}</ThemedText>
      </View>
      {expanded ? (
        <View
          style={styles.expanded}
          testID={`methodology-detail-${methodology.name}`}
        >
          <Section title="Reasons" items={methodology.reasons} />
          <Section title="Red flags" items={methodology.red_flags} />
          <Section title="Failed rules" items={methodology.failed_rules} />
        </View>
      ) : null}
    </Pressable>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  const theme = useTheme();
  if (items.length === 0) {
    return null;
  }
  return (
    <View style={styles.section}>
      <ThemedText style={[styles.sectionTitle, { color: theme.accent }]}>
        {title}
      </ThemedText>
      {items.map((item, index) => (
        <ThemedText key={index} muted style={styles.sectionItem}>
          • {item}
        </ThemedText>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { borderWidth: 1, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4 },
  chipLabel: { fontSize: 12, fontWeight: "600" },
  scoreRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  card: { borderWidth: 1, borderRadius: 10, padding: 12, gap: 8 },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 8,
  },
  cardName: { fontSize: 16, fontWeight: "600", flexShrink: 1 },
  family: { fontSize: 11 },
  cardMeta: { flexDirection: "row", alignItems: "center", gap: 10 },
  badge: { borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { color: "#ffffff", fontSize: 12, fontWeight: "700" },
  expanded: { gap: 8, marginTop: 4 },
  section: { gap: 2 },
  sectionTitle: { fontSize: 12, fontWeight: "700" },
  sectionItem: { fontSize: 13, lineHeight: 18 },
});
