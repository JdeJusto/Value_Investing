import { useLocalSearchParams } from "expo-router";

import { ThemedText, ThemedView } from "../../src/theme/Themed";

export default function CompanyScreen() {
  const { ticker } = useLocalSearchParams<{ ticker: string }>();
  return (
    <ThemedView center>
      <ThemedText>Company {ticker} — coming soon.</ThemedText>
    </ThemedView>
  );
}
