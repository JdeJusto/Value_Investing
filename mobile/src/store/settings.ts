import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type ThemeMode = "system" | "light" | "dark";

export type SettingsState = {
  lanUrl: string; // e.g. "http://192.168.0.105:8000"
  tailscaleUrl: string; // e.g. "http://100.64.1.5:8000"
  apiKey: string;
  useTailscale: boolean; // false by default (prefer LAN at home)
  useEmulator: boolean; // when true, force http://10.0.2.2:8000 (emulator -> host)
  themeMode: ThemeMode;
  setLanUrl: (v: string) => void;
  setTailscaleUrl: (v: string) => void;
  setApiKey: (v: string) => void;
  setUseTailscale: (v: boolean) => void;
  setUseEmulator: (v: boolean) => void;
  setThemeMode: (v: ThemeMode) => void;
};

// NOTE: the API key lives in AsyncStorage for the skeleton. Upgrade to
// expo-secure-store once we have a dev build (it needs a native module).
export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      lanUrl: "",
      tailscaleUrl: "",
      apiKey: "",
      useTailscale: false,
      useEmulator: false,
      themeMode: "system",
      setLanUrl: (v) => set({ lanUrl: v }),
      setTailscaleUrl: (v) => set({ tailscaleUrl: v }),
      setApiKey: (v) => set({ apiKey: v }),
      setUseTailscale: (v) => set({ useTailscale: v }),
      setUseEmulator: (v) => set({ useEmulator: v }),
      setThemeMode: (v) => set({ themeMode: v }),
    }),
    {
      name: "vi-settings",
      storage: createJSONStorage(() => AsyncStorage),
    },
  ),
);
