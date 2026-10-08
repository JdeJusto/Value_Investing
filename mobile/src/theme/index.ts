/**
 * Color palettes for the mobile app. Navy + green mirror the project logo.
 * Screens never import these directly — they read the active theme through
 * `useTheme()` from `ThemeProvider`.
 */

export const lightTheme = {
  bg: "#ffffff",
  card: "#f5f6f8",
  text: "#0d1b2a",
  muted: "#5a6577",
  primary: "#1c2b4a", // navy from the logo
  accent: "#3bb273", // green from the logo
  danger: "#e63946",
  warning: "#f4a261",
  border: "#d9dde3",
};

export const darkTheme: typeof lightTheme = {
  bg: "#0b1524",
  card: "#152238",
  text: "#f2f5f9",
  muted: "#9aa7bb",
  primary: "#3bb273",
  accent: "#3bb273",
  danger: "#ff6b78",
  warning: "#f4a261",
  border: "#26334d",
};

export type Theme = typeof lightTheme;
