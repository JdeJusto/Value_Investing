import AsyncStorage from "@react-native-async-storage/async-storage";

import { useSettings } from "../settings";

const DEFAULTS = {
  lanUrl: "",
  tailscaleUrl: "",
  apiKey: "",
  useTailscale: false,
  useEmulator: false,
  themeMode: "system" as const,
};

/** Let the persist middleware finish its async storage write. */
async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

beforeEach(async () => {
  await AsyncStorage.clear();
  useSettings.setState(DEFAULTS);
  await flush();
});

test("useEmulator defaults to false", () => {
  expect(useSettings.getState().useEmulator).toBe(false);
});

test("setUseEmulator updates the flag", () => {
  useSettings.getState().setUseEmulator(true);
  expect(useSettings.getState().useEmulator).toBe(true);
});

test("useEmulator is written to AsyncStorage", async () => {
  useSettings.getState().setUseEmulator(true);
  await flush();

  const raw = await AsyncStorage.getItem("vi-settings");
  expect(raw).not.toBeNull();
  expect(JSON.parse(raw as string).state.useEmulator).toBe(true);
});

test("useEmulator rehydrates from AsyncStorage on a fresh start", async () => {
  await AsyncStorage.setItem(
    "vi-settings",
    JSON.stringify({ state: { ...DEFAULTS, useEmulator: true }, version: 0 }),
  );

  await useSettings.persist.rehydrate();

  expect(useSettings.getState().useEmulator).toBe(true);
});
