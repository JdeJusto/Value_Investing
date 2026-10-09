import { useState } from "react";
import {
  Alert,
  FlatList,
  Keyboard,
  Modal,
  Pressable,
  RefreshControl,
  StyleSheet,
  TextInput,
  View,
} from "react-native";

import type { PortfolioPosition, PortfolioPerformanceData } from "../../src/api/portfolio";
import { PortfolioRowCard } from "../../src/components/PortfolioRowCard";
import {
  usePortfolio,
  usePortfolioPerformance,
  useAddPosition,
  useRemovePosition,
  useExitPosition,
} from "../../src/hooks/usePortfolio";
import { ThemedText, ThemedView } from "../../src/theme/Themed";
import { useTheme } from "../../src/theme/ThemeProvider";
import { SkeletonCards, ErrorNote } from "../../src/components/StateViews";
import { abbreviateCurrency, formatPercent, DASH } from "../../src/utils/format";
import { router } from "expo-router";

const SIGNALS = ["BUY", "WATCH", "HOLD"];

export default function PortfolioScreen() {
  const theme = useTheme();
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    ticker: "",
    shares: "",
    price: "",
    thesis: "",
    signal: "BUY",
  });

  const portfolio = usePortfolio();
  const performance = usePortfolioPerformance();
  const addPosition = useAddPosition();
  const removePosition = useRemovePosition();
  const exitPosition = useExitPosition();

  const positions = portfolio.data?.data.positions ?? [];
  const summary = portfolio.data?.data.summary;
  const perfData = performance.data?.data;
  const isLoading = portfolio.isPending;
  const isRefetching = portfolio.isRefetching || performance.isRefetching;
  const hasPositions = positions.length > 0;

  function handleAddSubmit() {
    if (!addForm.ticker || !addForm.shares || !addForm.price) {
      Alert.alert("Missing fields", "Ticker, shares and price are required.");
      return;
    }
    const shares = Number(addForm.shares);
    const price = Number(addForm.price);
    if (shares <= 0 || price <= 0) {
      Alert.alert("Invalid values", "Shares and price must be positive.");
      return;
    }
    addPosition.mutate(
      {
        ticker: addForm.ticker.toUpperCase(),
        shares,
        price,
        thesis: addForm.thesis || undefined,
        signal: addForm.signal || undefined,
        date: new Date().toISOString().split("T")[0],
      },
      {
        onSuccess: () => {
          setShowAddModal(false);
          setAddForm({ ticker: "", shares: "", price: "", thesis: "", signal: "BUY" });
          Keyboard.dismiss();
        },
        onError: (error) => {
          Alert.alert("Failed to add position", String(error));
        },
      },
    );
  }

  function handleExit(ticker: string) {
    Alert.alert(
      "Exit position?",
      `Sell ${ticker} at the current market price?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Exit",
          style: "destructive",
          onPress: () =>
            exitPosition.mutate(ticker, {
              onError: (error) => Alert.alert("Failed to exit", String(error)),
            }),
        },
      ],
    );
  }

  function handleRemove(ticker: string) {
    Alert.alert(
      "Remove position?",
      `Remove ${ticker} without recording PnL?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: () =>
            removePosition.mutate(ticker, {
              onError: (error) => Alert.alert("Failed to remove", String(error)),
            }),
        },
      ],
    );
  }

  function renderRow({ item }: { item: PortfolioPosition }) {
    return (
      <PortfolioRowCard
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

  return (
    <ThemedView>
      <View style={styles.header}>
        <ThemedText style={styles.title}>Portfolio</ThemedText>
        <Pressable
          testID="add-position-button"
          onPress={() => setShowAddModal(true)}
          style={styles.addButton}
        >
          <ThemedText>+ Add</ThemedText>
        </Pressable>
      </View>

      {summary && (
        <View style={styles.summary}>
          <SummaryMetric label="Cost" value={abbreviateCurrency(summary.cost)} />
          <SummaryMetric label="Value" value={abbreviateCurrency(summary.value)} />
          <SummaryMetric
            label="PnL"
            value={abbreviateCurrency(summary.pnl)}
            valueColor={summary.pnl > 0 ? "#3bb273" : summary.pnl < 0 ? "#e63946" : theme.text}
          />
          <SummaryMetric
            label="Return"
            value={summary.return_pct === null ? DASH : formatPercent(summary.return_pct)}
            valueColor={
              summary.return_pct !== null && summary.return_pct > 0
                ? "#3bb273"
                : summary.return_pct !== null && summary.return_pct < 0
                ? "#e63946"
                : theme.text
            }
          />
        </View>
      )}

      {perfData && (
        <View style={styles.allocation}>
          <ThemedText style={styles.sectionTitle}>Allocation Risk</ThemedText>
          <View style={styles.allocationRow}>
            <ThemedText muted>Largest: </ThemedText>
            <ThemedText>
              {formatPercent(perfData.allocation.risk.largest_position_weight)}
            </ThemedText>
          </View>
          <View style={styles.allocationRow}>
            <ThemedText muted>Top-5: </ThemedText>
            <ThemedText>{formatPercent(perfData.allocation.risk.top_n_share)}</ThemedText>
          </View>
          <View style={styles.allocationRow}>
            <ThemedText muted>HHI: </ThemedText>
            <ThemedText>
              {perfData.allocation.risk.hhi?.toFixed(3) ?? DASH}
            </ThemedText>
          </View>
        </View>
      )}

      {!hasPositions && !isLoading ? (
        <ThemedView center style={styles.empty}>
          <ThemedText muted style={styles.emptyText}>No positions yet.</ThemedText>
          <ThemedText muted>Tap + Add to open your first position.</ThemedText>
        </ThemedView>
      ) : isLoading ? (
        <ThemedView center style={styles.loading}>
          <SkeletonCards count={4} />
        </ThemedView>
      ) : portfolio.isError ? (
        <ErrorNote error={portfolio.error} />
      ) : (
        <FlatList
          testID="portfolio-list"
          data={positions}
          keyExtractor={(item) => item.ticker}
          renderItem={renderRow}
          ListFooterComponent={
            isRefetching ? (
              <View style={styles.footer}>
                <ThemedText muted>Refreshing…</ThemedText>
              </View>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={() => {
                void portfolio.refetch();
                void performance.refetch();
              }}
              tintColor={theme.accent}
            />
          }
          contentContainerStyle={styles.list}
        />
      )}

      {showAddModal && (
        <AddPositionModal
          form={addForm}
          onChange={setAddForm}
          onSubmit={handleAddSubmit}
          onCancel={() => setShowAddModal(false)}
          isSubmitting={addPosition.isPending}
        />
      )}
    </ThemedView>
  );
}

function SummaryMetric({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  const theme = useTheme();
  return (
    <View style={styles.summaryCard}>
      <ThemedText muted style={styles.summaryLabel}>{label}</ThemedText>
      <ThemedText
        style={[
          styles.summaryValue,
          valueColor ? { color: valueColor } : undefined,
        ]}
      >
        {value}
      </ThemedText>
    </View>
  );
}

type AddForm = { ticker: string; shares: string; price: string; thesis: string; signal: string };

function AddPositionModal({
  form,
  onChange,
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  form: AddForm;
  onChange: (form: AddForm) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  return (
    <Modal visible={true} transparent animationType="slide">
      <Pressable
        testID="add-modal-backdrop"
        onPress={onCancel}
        style={styles.modalBackdrop}
      />
      <View style={styles.modal}>
        <View style={styles.modalHeader}>
          <ThemedText style={styles.modalTitle}>Add Position</ThemedText>
          <Pressable onPress={onCancel} style={styles.closeButton}>
            <ThemedText>✕</ThemedText>
          </Pressable>
        </View>

        <View style={styles.modalBody}>
          <InputRow label="Ticker" value={form.ticker} onChange={(v) => onChange({ ...form, ticker: v.toUpperCase() })} autoCapitalize="characters" maxLength={8} />
          <InputRow label="Shares" value={form.shares} onChange={(v) => onChange({ ...form, shares: v })} keyboardType="decimal-pad" placeholder="10" />
          <InputRow label="Price" value={form.price} onChange={(v) => onChange({ ...form, price: v })} keyboardType="decimal-pad" placeholder="150.00" />
          <InputRow label="Thesis (optional)" value={form.thesis} onChange={(v) => onChange({ ...form, thesis: v })} placeholder="Moat, compounding..." />
          <SignalPicker value={form.signal} onChange={(v) => onChange({ ...form, signal: v })} />
        </View>

        <Pressable
          disabled={isSubmitting}
          onPress={onSubmit}
          style={[
            styles.submitButton,
            isSubmitting && { opacity: 0.6 },
          ]}
        >
          <ThemedText style={styles.submitText}>
            {isSubmitting ? "Adding…" : "Add Position"}
          </ThemedText>
        </Pressable>
      </View>
    </Modal>
  );
}

function InputRow({
  label,
  value,
  onChange,
  keyboardType,
  placeholder,
  autoCapitalize,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  keyboardType?: "decimal-pad" | "default";
  placeholder?: string;
  autoCapitalize?: "characters" | "none";
  maxLength?: number;
}) {
  const theme = useTheme();
  return (
    <View style={styles.inputRow}>
      <ThemedText style={styles.inputLabel}>{label}</ThemedText>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={theme.muted}
        keyboardType={keyboardType ?? "default"}
        autoCapitalize={autoCapitalize ?? "none"}
        maxLength={maxLength}
        style={[
          styles.input,
          { color: theme.text, borderColor: theme.border, backgroundColor: theme.card },
        ]}
      />
    </View>
  );
}

function SignalPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const theme = useTheme();
  return (
    <View style={styles.inputRow}>
      <ThemedText style={styles.inputLabel}>Signal</ThemedText>
      <View style={styles.signalChips}>
        {SIGNALS.map((s) => (
          <Pressable
            key={s}
            onPress={() => onChange(s)}
            style={[
              styles.signalChip,
              value === s && { backgroundColor: theme.accent, borderColor: theme.accent },
            ]}
          >
            <ThemedText style={value === s ? styles.signalChipActive : undefined}>
              {s}
            </ThemedText>
          </Pressable>
        ))}
      </View>
    </View>
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
  addButton: {
    backgroundColor: "#3bb273",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  summary: {
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: 16,
    gap: 12,
    marginBottom: 8,
  },
  summaryCard: { flex: 1, minWidth: "45%", gap: 2 },
  summaryLabel: { fontSize: 11 },
  summaryValue: { fontSize: 16, fontWeight: "600" },
  allocation: { paddingHorizontal: 16, gap: 4, marginBottom: 8 },
  sectionTitle: { fontSize: 14, fontWeight: "600" },
  allocationRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
  },
  empty: { flex: 1, gap: 8, padding: 24 },
  emptyText: { textAlign: "center", fontSize: 15 },
  loading: { flex: 1 },
  list: { padding: 16, gap: 10 },
  footer: { padding: 16, alignItems: "center" },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.3)" },
  modal: {
    marginTop: "auto",
    backgroundColor: "#fff",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: "85%",
  },
  modalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 16,
    borderBottomWidth: 1,
  },
  modalTitle: { fontSize: 18, fontWeight: "700" },
  closeButton: { padding: 4 },
  modalBody: { padding: 16, gap: 12 },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  inputLabel: { width: 100, fontSize: 14 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    fontSize: 14,
  },
  signalChips: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  signalChip: {
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  signalChipActive: { color: "#fff", fontWeight: "600" },
  submitButton: {
    backgroundColor: "#3bb273",
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: "center",
    marginTop: 8,
  },
  submitText: { color: "#fff", fontWeight: "600", fontSize: 16 },
});