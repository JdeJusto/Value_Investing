import { useEffect, useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from "react-native";

import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import type { ScreenerFilterParams } from "../api/screener";

const SECTORS = [
  "Technology",
  "Financial Services",
  "Healthcare",
  "Consumer Cyclical",
  "Consumer Defensive",
  "Industrials",
  "Communication Services",
  "Energy",
  "Real Estate",
  "Utilities",
  "Basic Materials",
];

const UNIVERSE_OPTIONS = [
  { key: "sp500", label: "S&P 500" },
  { key: "nasdaq100", label: "Nasdaq 100" },
  { key: "russell2000", label: "Russell 2000" },
  { key: "european", label: "European" },
  { key: "all", label: "All (slow)" },
];

export function ScreenerFilterSheet({
  filters,
  onChange,
  onRun,
}: {
  filters: ScreenerFilterParams;
  onChange: (next: Partial<ScreenerFilterParams>) => void;
  onRun: () => void;
}) {
  const theme = useTheme();

  const [universe, setUniverse] = useState(filters.universe ?? "");
  const [sector, setSector] = useState<string[]>(
    filters.sector ? filters.sector.split(",").filter(Boolean) : []
  );
  const [verdict, setVerdict] = useState<string[]>(
    filters.verdict ? filters.verdict.split(",").filter(Boolean) : []
  );
  const [pe_max, setPeMax] = useState<number | null>(
    filters.pe_max ?? null
  );
  const [roe_min, setRoeMin] = useState<number | null>(
    filters.roe_min ?? null
  );
  const [fcf_yield_min, setFcfMin] = useState<number | null>(
    filters.fcf_yield_min ?? null
  );
  const [market_cap_min, setMcapMin] = useState<number | null>(
    filters.market_cap_min ?? null
  );
  const [market_cap_max, setMcapMax] = useState<number | null>(
    filters.market_cap_max ?? null
  );

  useEffect(() => {
    onChange({
      universe: universe || undefined,
      sector: sector.length > 0 ? sector.join(",") : undefined,
      verdict: verdict.length > 0 ? verdict.join(",") : undefined,
      pe_max: pe_max ?? undefined,
      roe_min: roe_min ?? undefined,
      fcf_yield_min: fcf_yield_min ?? undefined,
      market_cap_min: market_cap_min ?? undefined,
      market_cap_max: market_cap_max ?? undefined,
    });
  }, [
    universe,
    sector,
    verdict,
    pe_max,
    roe_min,
    fcf_yield_min,
    market_cap_min,
    market_cap_max,
    onChange,
  ]);

  function toggleSector(s: string) {
    const next = sector.includes(s)
      ? sector.filter((x) => x !== s)
      : [...sector, s];
    setSector(next);
  }

  function toggleVerdict(v: string) {
    const next = verdict.includes(v)
      ? verdict.filter((x) => x !== v)
      : [...verdict, v];
    setVerdict(next);
  }

  function toggleUniverse(u: string) {
    setUniverse(u === universe ? "" : u);
  }

  return (
    <Modal visible={true} transparent animationType="slide">
      <Pressable
        testID="filter-sheet-backdrop"
        onPress={() => {}}
        style={styles.backdrop}
      />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <View style={styles.header}>
          <ThemedText style={styles.title}>Filters</ThemedText>
          <Pressable onPress={onRun} style={styles.runButton}>
            <ThemedText style={styles.runText}>Run</ThemedText>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {/* Universe */}
          <ThemedText style={styles.sectionTitle}>Universe</ThemedText>
          <View style={styles.chips}>
            {UNIVERSE_OPTIONS.map((opt) => (
              <Pressable
                key={opt.key}
                onPress={() => toggleUniverse(opt.key)}
                style={[
                  styles.chip,
                  universe === opt.key && { backgroundColor: theme.accent },
                ]}
              >
                <ThemedText
                  style={universe === opt.key ? styles.chipActive : undefined}
                >
                  {opt.label}
                </ThemedText>
              </Pressable>
            ))}
          </View>

          {/* Sectors */}
          <ThemedText style={styles.sectionTitle}>Sectors</ThemedText>
          <View style={styles.chips}>
            {SECTORS.map((s) => (
              <Pressable
                key={s}
                onPress={() => toggleSector(s)}
                style={[
                  styles.chip,
                  sector.includes(s) && { backgroundColor: theme.accent },
                ]}
              >
                <ThemedText
                  style={sector.includes(s) ? styles.chipActive : undefined}
                >
                  {s}
                </ThemedText>
              </Pressable>
            ))}
          </View>

          {/* Verdicts */}
          <ThemedText style={styles.sectionTitle}>Verdict</ThemedText>
          <View style={styles.chips}>
            {["BUY", "WATCH", "HOLD", "AVOID", "N/A", "INSUFFICIENT_DATA"].map((v) => (
              <Pressable
                key={v}
                onPress={() => toggleVerdict(v)}
                style={[
                  styles.chip,
                  verdict.includes(v) && { backgroundColor: theme.accent },
                ]}
              >
                <ThemedText
                  style={verdict.includes(v) ? styles.chipActive : undefined}
                >
                  {v}
                </ThemedText>
              </Pressable>
            ))}
          </View>

          {/* Numerics */}
          <ThemedText style={styles.sectionTitle}>Metrics</ThemedText>
          <NumericInput
            label="Max P/E"
            value={pe_max}
            onChange={(v) => setPeMax(v)}
            placeholder="15"
          />
          <NumericInput
            label="Min ROE %"
            value={roe_min}
            onChange={(v) => setRoeMin(v)}
            placeholder="15"
          />
          <NumericInput
            label="Min FCF Yield %"
            value={fcf_yield_min}
            onChange={(v) => setFcfMin(v)}
            placeholder="5"
          />
          <NumericInput
            label="Min Market Cap ($B)"
            value={market_cap_min}
            onChange={(v) => setMcapMin(v)}
            placeholder="1"
          />
          <NumericInput
            label="Max Market Cap ($B)"
            value={market_cap_max}
            onChange={(v) => setMcapMax(v)}
            placeholder="1000"
          />
        </ScrollView>
      </View>
    </Modal>
  );
}

function NumericInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  placeholder: string;
}) {
  const theme = useTheme();
  return (
    <View style={styles.inputRow}>
      <ThemedText style={styles.inputLabel}>{label}</ThemedText>
      <TextInput
        value={value === null ? "" : String(value)}
        onChangeText={(text) => onChange(text === "" ? null : Number(text))}
        placeholder={placeholder}
        placeholderTextColor={theme.muted}
        keyboardType="decimal-pad"
        style={[
          styles.input,
          { color: theme.text, borderColor: theme.border, backgroundColor: theme.card },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.3)" },
  sheet: {
    flex: 1,
    backgroundColor: "#fff",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    marginTop: "auto",
  },
  handle: {
    width: 40,
    height: 5,
    borderRadius: 3,
    alignSelf: "center",
    marginTop: 10,
    backgroundColor: "#ccc",
  },
  header: { flexDirection: "row", justifyContent: "space-between", padding: 16 },
  title: { fontSize: 18, fontWeight: "700" },
  runButton: {
    backgroundColor: "#3bb273",
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 8,
  },
  runText: { color: "#fff", fontWeight: "600" },
  scroll: { padding: 16, gap: 16 },
  sectionTitle: { fontSize: 14, fontWeight: "600" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  chipActive: { color: "#fff", fontWeight: "600" },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  inputLabel: { width: 120, fontSize: 14 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 14,
  },
});