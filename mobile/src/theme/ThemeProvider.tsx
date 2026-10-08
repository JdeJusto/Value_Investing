import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useColorScheme } from "react-native";

import { useSettings } from "../store/settings";
import { darkTheme, lightTheme, type Theme } from "./index";

const ThemeContext = createContext<Theme>(lightTheme);

/**
 * Resolves the active palette from the persisted `themeMode` setting
 * ("system" follows the OS) and provides it through React context.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const themeMode = useSettings((state) => state.themeMode);
  const systemScheme = useColorScheme();

  const theme = useMemo(() => {
    const resolved =
      themeMode === "system"
        ? systemScheme === "dark"
          ? "dark"
          : "light"
        : themeMode;
    return resolved === "dark" ? darkTheme : lightTheme;
  }, [themeMode, systemScheme]);

  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}
