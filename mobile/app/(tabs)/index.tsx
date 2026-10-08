import { router } from "expo-router";
import { useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from "react-native";

import { ApiRequestError } from "../../src/api/client";
import { useCompany } from "../../src/hooks/useCompany";
import { ThemedText, ThemedView } from "../../src/theme/Themed";
import { useTheme } from "../../src/theme/ThemeProvider";
import { abbreviateCurrency } from "../../src/utils/format";

const SUGGESTED = ["AAPL", "MSFT", "KO", "JNJ"];

export default function HomeScreen() {
  const theme = useTheme();
  const [ticker, setTicker] = useState("");
  const normalized = ticker.trim().toUpperCase();
  const query = useCompany(normalized);
  const company = query.data?.data;

  return (
    <ThemedView>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <ThemedText style={styles.title}>Value Investing</ThemedText>
        <ThemedText muted>Fundamental analysis, on the go.</ThemedText>

        <TextInput
          value={ticker}
          onChangeText={setTicker}
          placeholder="Ticker (e.g. AAPL)"
          placeholderTextColor={theme.muted}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={8}
          style={[
            styles.input,
            {
              color: theme.text,
              borderColor: theme.border,
              backgroundColor: theme.card,
            },
          ]}
        />

        <View style={styles.chips}>
          {SUGGESTED.map((symbol) => (
            <Pressable
              key={symbol}
              onPress={() => setTicker(symbol)}
              style={[
                styles.chip,
                { borderColor: theme.border, backgroundColor: theme.card },
              ]}
            >
              <ThemedText>{symbol}</ThemedText>
            </Pressable>
          ))}
        </View>

        {normalized.length === 0 ? (
          <ThemedText muted style={styles.hint}>
            Type a ticker to load a company.
          </ThemedText>
        ) : null}

        {query.isLoading ? <SkeletonCard /> : null}

        {query.isError ? (
          <View
            testID="company-error"
            style={[
              styles.card,
              { backgroundColor: theme.card, borderColor: theme.danger },
            ]}
          >
            <ThemedText style={{ color: theme.danger }}>
              {errorMessage(query.error, normalized)}
            </ThemedText>
          </View>
        ) : null}

        {company ? (
          <Pressable
            testID="company-card"
            onPress={() =>
              router.push({
                pathname: "/company/[ticker]",
                params: { ticker: company.ticker },
              })
            }
            style={[
              styles.card,
              { backgroundColor: theme.card, borderColor: theme.border },
            ]}
          >
            <View style={styles.cardHeader}>
              <ThemedText style={styles.cardTicker}>{company.ticker}</ThemedText>
              <ThemedText style={styles.cardPrice}>
                {abbreviateCurrency(company.price)}
              </ThemedText>
            </View>
            <ThemedText>{company.name ?? "Unknown name"}</ThemedText>
            <ThemedText muted>{company.sector ?? "Unknown sector"}</ThemedText>
            <View style={styles.cardRow}>
              <ThemedText muted>Market cap</ThemedText>
              <ThemedText>{abbreviateCurrency(company.market_cap)}</ThemedText>
            </View>
          </Pressable>
        ) : null}
      </ScrollView>
    </ThemedView>
  );
}

function SkeletonCard() {
  const theme = useTheme();
  return (
    <View
      testID="company-skeleton"
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.border },
      ]}
    >
      <View
        style={[styles.skeletonLine, { backgroundColor: theme.border, width: "40%" }]}
      />
      <View
        style={[styles.skeletonLine, { backgroundColor: theme.border, width: "70%" }]}
      />
      <View
        style={[styles.skeletonLine, { backgroundColor: theme.border, width: "55%" }]}
      />
    </View>
  );
}

function errorMessage(error: unknown, ticker: string): string {
  if (error instanceof ApiRequestError) {
    if (error.code === "TICKER_NOT_FOUND") {
      return `Ticker ${ticker} not found.`;
    }
    if (error.code === "NETWORK_ERROR") {
      return "Cannot reach the server. Check Settings.";
    }
    if (error.code === "UNAUTHORIZED" || error.status === 401) {
      return "Invalid API key. Check Settings.";
    }
    if (error.code === "API_KEY_NOT_CONFIGURED") {
      return "The server has no API key configured.";
    }
    return error.message;
  }
  return "Something went wrong. Try again.";
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 10 },
  title: { fontSize: 24, fontWeight: "700" },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
  chips: { flexDirection: "row", gap: 8 },
  chip: {
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  hint: { marginTop: 8 },
  card: { borderWidth: 1, borderRadius: 10, padding: 14, gap: 6 },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  cardTicker: { fontSize: 20, fontWeight: "700" },
  cardPrice: { fontSize: 18, fontWeight: "600" },
  cardRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 4,
  },
  skeletonLine: { height: 14, borderRadius: 7, marginBottom: 8 },
});
