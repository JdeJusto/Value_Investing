import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";
import {
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  View,
} from "react-native";

import type { ApiEnvelope } from "../api/client";
import type {
  Filing,
  SectionResponse,
  StatementResponse,
} from "../api/company";
import { useFilings } from "../hooks/useFilings";
import { useSection } from "../hooks/useSection";
import { useStatement } from "../hooks/useStatement";
import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { ErrorNote, SkeletonCards } from "./StateViews";

type StatementQuery = UseQueryResult<ApiEnvelope<StatementResponse>, Error>;
type SectionQuery = UseQueryResult<ApiEnvelope<SectionResponse>, Error>;

/** Words fetched for the first narrative preview ("Load full" removes it). */
const PREVIEW_WORDS = 150;

const STATEMENTS = [
  { key: "balance_sheet", label: "Balance Sheet" },
  { key: "income_statement", label: "Income" },
  { key: "cash_flow", label: "Cash Flow" },
] as const;

const SECTIONS = [
  { key: "risk_factors", label: "Risk Factors" },
  { key: "md_a", label: "MD&A" },
] as const;

const FORM_COLORS: Record<string, string> = {
  "10-K": "#3bb273",
  "10-Q": "#00acc1",
  "8-K": "#f4a261",
};

export function FilingsTab({ ticker }: { ticker: string }) {
  const theme = useTheme();
  const [form, setForm] = useState<string | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [includeAmendments, setIncludeAmendments] = useState(true);
  const [selected, setSelected] = useState<Filing | null>(null);
  const [view, setView] = useState<"statements" | "narrative" | null>(null);
  const [statementType, setStatementType] = useState<string>("balance_sheet");
  const [sectionType, setSectionType] = useState<string>("risk_factors");
  const [wordLimit, setWordLimit] = useState<number | undefined>(PREVIEW_WORDS);

  const filingsQuery = useFilings(ticker, {
    form: form ?? undefined,
    year: year ?? undefined,
    limit: 50,
    includeAmendments,
  });
  const statementQuery = useStatement(
    selected?.accession_number ?? "",
    statementType,
    view === "statements",
  );
  const sectionQuery = useSection(
    selected?.accession_number ?? "",
    sectionType,
    view === "narrative",
    wordLimit,
  );

  const filings = filingsQuery.data?.data.filings ?? [];
  const availableForms = filingsQuery.data?.data.available_forms ?? [];
  const availableYears = filingsQuery.data?.data.available_years ?? [];

  return (
    <View style={styles.wrap}>
      <View style={styles.chipsRow}>
        <FilterChip
          testID="filter-form-all"
          label="All"
          active={form === null}
          onPress={() => setForm(null)}
        />
        {availableForms.map((item) => (
          <FilterChip
            key={item}
            testID={`filter-form-${item}`}
            label={item}
            active={form === item}
            onPress={() => setForm(item)}
          />
        ))}
      </View>
      <View style={styles.chipsRow}>
        <FilterChip
          testID="filter-year-all"
          label="All years"
          active={year === null}
          onPress={() => setYear(null)}
        />
        {availableYears.map((item) => (
          <FilterChip
            key={item}
            testID={`filter-year-${item}`}
            label={String(item)}
            active={year === item}
            onPress={() => setYear(item)}
          />
        ))}
      </View>
      <View style={styles.switchRow}>
        <ThemedText muted>Include amendments</ThemedText>
        <Switch
          value={includeAmendments}
          onValueChange={setIncludeAmendments}
          trackColor={{ true: theme.accent, false: theme.border }}
        />
      </View>

      {filingsQuery.isLoading ? (
        <SkeletonCards count={4} />
      ) : filingsQuery.isError ? (
        <ErrorNote error={filingsQuery.error} ticker={ticker} />
      ) : filings.length === 0 ? (
        <ThemedText muted>No filings match the filters.</ThemedText>
      ) : (
        filings.map((filing) => (
          <FilingRow
            key={filing.accession_number}
            filing={filing}
            selected={selected?.accession_number === filing.accession_number}
            onPress={() => {
              setSelected(filing);
              setView(null);
              setWordLimit(PREVIEW_WORDS);
            }}
          />
        ))
      )}

      {selected ? (
        <View
          testID="filing-preview"
          style={[
            styles.card,
            { backgroundColor: theme.card, borderColor: theme.border },
          ]}
        >
          <ThemedText style={styles.previewTitle}>
            {selected.form_type} · {selected.filing_date}
          </ThemedText>
          {selected.sec_url ? (
            <Pressable
              onPress={() => {
                void Linking.openURL(selected.sec_url ?? "");
              }}
            >
              <ThemedText style={{ color: theme.accent }}>
                Open on SEC.gov
              </ThemedText>
            </Pressable>
          ) : null}

          <View style={styles.segmentRow}>
            <Segment
              label="Statements"
              active={view === "statements"}
              onPress={() => setView("statements")}
            />
            <Segment
              label="Narrative"
              active={view === "narrative"}
              onPress={() => setView("narrative")}
            />
          </View>

          {view === "statements" ? (
            <View style={styles.wrap}>
              <View style={styles.segmentRow}>
                {STATEMENTS.map((item) => (
                  <Segment
                    key={item.key}
                    label={item.label}
                    active={statementType === item.key}
                    onPress={() => setStatementType(item.key)}
                  />
                ))}
              </View>
              <StatementPreview query={statementQuery} />
            </View>
          ) : null}

          {view === "narrative" ? (
            <View style={styles.wrap}>
              <View style={styles.segmentRow}>
                {SECTIONS.map((item) => (
                  <Segment
                    key={item.key}
                    label={item.label}
                    active={sectionType === item.key}
                    onPress={() => setSectionType(item.key)}
                  />
                ))}
              </View>
              <SectionPreview
                query={sectionQuery}
                onLoadFull={() => setWordLimit(undefined)}
              />
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function FilingRow({
  filing,
  selected,
  onPress,
}: {
  filing: Filing;
  selected: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  const color = FORM_COLORS[filing.form_type] ?? theme.muted;
  return (
    <Pressable
      testID={`filing-${filing.accession_number}`}
      onPress={onPress}
      style={[
        styles.filingRow,
        { borderColor: theme.border },
        selected && { backgroundColor: theme.card },
      ]}
    >
      <View style={[styles.formBadge, { backgroundColor: color }]}>
        <ThemedText style={styles.formBadgeText}>{filing.form_type}</ThemedText>
      </View>
      <View style={styles.filingMeta}>
        <ThemedText>{filing.filing_date}</ThemedText>
        <ThemedText muted style={styles.filingSub}>
          {filing.period_of_report ? `Period ${filing.period_of_report}` : "—"}
        </ThemedText>
      </View>
      {filing.is_amended ? (
        <View style={[styles.amendedChip, { borderColor: theme.warning }]}>
          <ThemedText style={[styles.amendedText, { color: theme.warning }]}>
            A
          </ThemedText>
        </View>
      ) : null}
    </Pressable>
  );
}

function StatementPreview({ query }: { query: StatementQuery }) {
  const theme = useTheme();
  if (query.isLoading) {
    return <SkeletonCards count={2} />;
  }
  if (query.isError) {
    return <ErrorNote error={query.error} />;
  }
  const data = query.data?.data;
  if (!data) {
    return null;
  }
  return (
    <View testID="statement-preview" style={styles.wrap}>
      <WarningBanner warnings={data.warnings} />
      {data.lines.length === 0 ? (
        <ThemedText muted>No lines for this statement.</ThemedText>
      ) : (
        data.lines.map((line, index) => (
          <View
            key={index}
            style={[styles.statementRow, { borderColor: theme.border }]}
          >
            <ThemedText
              numberOfLines={2}
              style={[
                styles.statementLabel,
                { paddingLeft: 8 + line.indent_level * 10 },
              ]}
            >
              {line.label}
            </ThemedText>
            <ThemedText style={styles.statementValue}>
              {line.current ?? "—"}
            </ThemedText>
            <ThemedText muted style={styles.statementValue}>
              {line.prior ?? "—"}
            </ThemedText>
          </View>
        ))
      )}
    </View>
  );
}

function SectionPreview({
  query,
  onLoadFull,
}: {
  query: SectionQuery;
  onLoadFull: () => void;
}) {
  const theme = useTheme();
  if (query.isLoading) {
    return <SkeletonCards count={2} />;
  }
  if (query.isError) {
    return <ErrorNote error={query.error} />;
  }
  const data = query.data?.data;
  if (!data) {
    return null;
  }
  return (
    <View testID="section-preview" style={styles.wrap}>
      <WarningBanner warnings={data.warnings} />
      <ThemedText style={styles.sectionTitle}>
        {data.title || "Section"}
      </ThemedText>
      <ThemedText muted style={styles.filingSub}>
        {data.word_count} words · {data.source}
      </ThemedText>
      <ScrollView style={styles.sectionScroll} nestedScrollEnabled>
        <ThemedText style={styles.sectionText}>
          {data.text || "No text."}
        </ThemedText>
      </ScrollView>
      {data.truncated ? (
        <Pressable
          onPress={onLoadFull}
          style={[styles.loadButton, { backgroundColor: theme.primary }]}
        >
          <ThemedText style={styles.loadButtonText}>
            Load full section
          </ThemedText>
        </Pressable>
      ) : null}
    </View>
  );
}

function WarningBanner({ warnings }: { warnings: string[] }) {
  const theme = useTheme();
  if (warnings.length === 0) {
    return null;
  }
  return (
    <View
      testID="filing-warning"
      style={[styles.warning, { borderColor: theme.warning }]}
    >
      {warnings.map((warning, index) => (
        <ThemedText key={index} style={[styles.warningText, { color: theme.warning }]}>
          ⚠ {warning}
        </ThemedText>
      ))}
    </View>
  );
}

function Segment({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.segment,
        { borderColor: theme.border },
        active && { backgroundColor: theme.accent, borderColor: theme.accent },
      ]}
    >
      <ThemedText style={active ? styles.segmentActive : undefined}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

function FilterChip({
  label,
  active,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID?: string;
}) {
  const theme = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[
        styles.filterChip,
        {
          borderColor: active ? theme.accent : theme.border,
          backgroundColor: active ? theme.accent : theme.card,
        },
      ]}
    >
      <ThemedText style={active ? styles.segmentActive : undefined}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  filterChip: {
    borderWidth: 1,
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  filingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
  },
  formBadge: { borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  formBadgeText: { color: "#ffffff", fontSize: 12, fontWeight: "700" },
  filingMeta: { flex: 1 },
  filingSub: { fontSize: 11 },
  amendedChip: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6 },
  amendedText: { fontSize: 11, fontWeight: "700" },
  card: { borderWidth: 1, borderRadius: 10, padding: 12, gap: 8 },
  previewTitle: { fontSize: 14, fontWeight: "600" },
  segmentRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  segment: { borderWidth: 1, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4 },
  segmentActive: { color: "#ffffff", fontWeight: "600" },
  statementRow: {
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: 5,
  },
  statementLabel: { flex: 1, fontSize: 12 },
  statementValue: { width: 78, textAlign: "right", fontSize: 12 },
  sectionTitle: { fontSize: 14, fontWeight: "600" },
  sectionScroll: { maxHeight: 340 },
  sectionText: { fontSize: 12, lineHeight: 18 },
  loadButton: { borderRadius: 8, paddingVertical: 8, alignItems: "center" },
  loadButtonText: { color: "#ffffff", fontWeight: "600", fontSize: 12 },
  warning: { borderWidth: 1, borderRadius: 8, padding: 8, gap: 2 },
  warningText: { fontSize: 11 },
});
