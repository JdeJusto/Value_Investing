import { StyleSheet, View } from "react-native";

import { ThemedText } from "../theme/Themed";
import { useTheme } from "../theme/ThemeProvider";
import { apiErrorMessage } from "../utils/errors";

/** Skeleton cards for loading states (never a blank screen). */
export function SkeletonCards({ count = 3 }: { count?: number }) {
  const theme = useTheme();
  return (
    <View style={styles.list} testID="skeleton-cards">
      {Array.from({ length: count }, (_, index) => (
        <View
          key={index}
          style={[
            styles.card,
            { backgroundColor: theme.card, borderColor: theme.border },
          ]}
        >
          <View
            style={[styles.line, { backgroundColor: theme.border, width: "35%" }]}
          />
          <View
            style={[styles.line, { backgroundColor: theme.border, width: "80%" }]}
          />
        </View>
      ))}
    </View>
  );
}

/** Inline error card with the shared message mapping. */
export function ErrorNote({
  error,
  ticker = "",
}: {
  error: unknown;
  ticker?: string;
}) {
  const theme = useTheme();
  return (
    <View
      testID="error-note"
      style={[
        styles.card,
        { backgroundColor: theme.card, borderColor: theme.danger },
      ]}
    >
      <ThemedText style={{ color: theme.danger }}>
        {apiErrorMessage(error, ticker)}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 10 },
  card: { borderWidth: 1, borderRadius: 10, padding: 14, gap: 8 },
  line: { height: 14, borderRadius: 7 },
});
