import { useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  TextInput,
  View,
} from "react-native";

import { ApiClient, ApiRequestError } from "../../src/api/client";
import { getEffectiveBaseUrl } from "../../src/api/config";
import { useSettings, type ThemeMode } from "../../src/store/settings";
import { ThemedText, ThemedView } from "../../src/theme/Themed";
import { useTheme } from "../../src/theme/ThemeProvider";

const THEME_MODES: { value: ThemeMode; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

type TestStatus = "idle" | "testing" | "ok" | "error";

export default function SettingsScreen() {
  const theme = useTheme();
  const settings = useSettings();
  const [showKey, setShowKey] = useState(false);
  const [status, setStatus] = useState<TestStatus>("idle");
  const [statusMessage, setStatusMessage] = useState("");

  const effectiveBaseUrl = getEffectiveBaseUrl(settings);
  const canTest = effectiveBaseUrl.length > 0 && settings.apiKey.length > 0;

  const testConnection = async () => {
    setStatus("testing");
    setStatusMessage("");
    try {
      const client = new ApiClient({
        baseUrl: effectiveBaseUrl,
        apiKey: settings.apiKey,
      });
      await client.get("/api/v1/health");
      setStatus("ok");
      setStatusMessage(`Connected to ${effectiveBaseUrl}`);
    } catch (error) {
      setStatus("error");
      setStatusMessage(
        error instanceof ApiRequestError
          ? error.message
          : "Unexpected error while testing the connection.",
      );
    }
  };

  return (
    <ThemedView>
      <ScrollView contentContainerStyle={styles.content}>
        {settings.apiKey.length === 0 ? (
          <View style={[styles.banner, { backgroundColor: theme.warning }]}>
            <ThemedText style={styles.bannerText}>
              No API key set — the server rejects requests until you add one.
            </ThemedText>
          </View>
        ) : null}

        <ThemedText style={styles.sectionTitle}>Connection</ThemedText>

        <ThemedText style={styles.label}>LAN URL</ThemedText>
        <TextInput
          value={settings.lanUrl}
          onChangeText={settings.setLanUrl}
          placeholder="http://192.168.0.105:8000"
          placeholderTextColor={theme.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          style={[
            styles.input,
            {
              color: theme.text,
              borderColor: theme.border,
              backgroundColor: theme.card,
            },
          ]}
        />

        <ThemedText style={styles.label}>Tailscale URL (optional)</ThemedText>
        <TextInput
          value={settings.tailscaleUrl}
          onChangeText={settings.setTailscaleUrl}
          placeholder="http://100.x.y.z:8000"
          placeholderTextColor={theme.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          style={[
            styles.input,
            {
              color: theme.text,
              borderColor: theme.border,
              backgroundColor: theme.card,
            },
          ]}
        />

        <View style={styles.switchRow}>
          <ThemedText>Prefer Tailscale</ThemedText>
          <Switch
            value={settings.useTailscale}
            onValueChange={settings.setUseTailscale}
            trackColor={{ true: theme.accent, false: theme.border }}
          />
        </View>

        <ThemedText style={styles.label}>API key</ThemedText>
        <View style={styles.keyRow}>
          <TextInput
            value={settings.apiKey}
            onChangeText={settings.setApiKey}
            placeholder="API_KEY from the server .env"
            placeholderTextColor={theme.muted}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry={!showKey}
            style={[
              styles.input,
              styles.keyInput,
              {
                color: theme.text,
                borderColor: theme.border,
                backgroundColor: theme.card,
              },
            ]}
          />
          <Pressable
            onPress={() => setShowKey((value) => !value)}
            style={[styles.keyToggle, { borderColor: theme.border }]}
          >
            <ThemedText>{showKey ? "Hide" : "Show"}</ThemedText>
          </Pressable>
        </View>

        <Pressable
          onPress={testConnection}
          disabled={!canTest || status === "testing"}
          style={[
            styles.button,
            { backgroundColor: canTest ? theme.primary : theme.border },
          ]}
        >
          <ThemedText style={styles.buttonText}>
            {status === "testing" ? "Testing…" : "Test connection"}
          </ThemedText>
        </Pressable>

        {status === "ok" ? (
          <ThemedText style={[styles.status, { color: theme.accent }]}>
            ✓ {statusMessage}
          </ThemedText>
        ) : null}
        {status === "error" ? (
          <ThemedText style={[styles.status, { color: theme.danger }]}>
            ✕ {statusMessage}
          </ThemedText>
        ) : null}

        <View
          style={[
            styles.infoBox,
            { backgroundColor: theme.card, borderColor: theme.border },
          ]}
        >
          <ThemedText muted style={styles.infoTitle}>
            How to find your LAN IP
          </ThemedText>
          <ThemedText style={styles.mono}>
            ip -4 addr show | grep inet
          </ThemedText>
          <ThemedText muted>
            Run it on the machine serving the API, then use the address in the
            LAN URL above.
          </ThemedText>
        </View>

        <ThemedText style={styles.sectionTitle}>Appearance</ThemedText>
        <View style={[styles.segment, { borderColor: theme.border }]}>
          {THEME_MODES.map((mode) => {
            const active = settings.themeMode === mode.value;
            return (
              <Pressable
                key={mode.value}
                onPress={() => settings.setThemeMode(mode.value)}
                style={[
                  styles.segmentItem,
                  active && { backgroundColor: theme.accent },
                ]}
              >
                <ThemedText
                  style={active ? styles.segmentTextActive : undefined}
                >
                  {mode.label}
                </ThemedText>
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 8 },
  banner: { borderRadius: 8, padding: 10, marginBottom: 8 },
  bannerText: { color: "#0d1b2a" },
  sectionTitle: { fontSize: 18, fontWeight: "600", marginTop: 12 },
  label: { fontSize: 13, marginTop: 8 },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  switchRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 8,
  },
  keyRow: { flexDirection: "row", gap: 8, alignItems: "stretch" },
  keyInput: { flex: 1 },
  keyToggle: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    justifyContent: "center",
  },
  button: {
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 12,
  },
  buttonText: { color: "#ffffff", fontWeight: "600" },
  status: { marginTop: 8 },
  infoBox: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
    gap: 4,
  },
  infoTitle: { fontSize: 13, fontWeight: "600" },
  mono: { fontFamily: "monospace" },
  segment: {
    flexDirection: "row",
    borderWidth: 1,
    borderRadius: 8,
    overflow: "hidden",
  },
  segmentItem: { flex: 1, alignItems: "center", paddingVertical: 10 },
  segmentTextActive: { color: "#ffffff", fontWeight: "600" },
});
