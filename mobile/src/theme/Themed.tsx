import { Text, View, type TextProps, type ViewProps } from "react-native";

import { useTheme } from "./ThemeProvider";

type ThemedViewProps = ViewProps & { center?: boolean };

/** Full-screen container with the theme background; `center` centers content. */
export function ThemedView({ style, center = false, ...rest }: ThemedViewProps) {
  const theme = useTheme();
  return (
    <View
      style={[
        { flex: 1, backgroundColor: theme.bg },
        center && { alignItems: "center", justifyContent: "center" },
        style,
      ]}
      {...rest}
    />
  );
}

type ThemedTextProps = TextProps & { muted?: boolean };

/** Text with the theme foreground color; `muted` dims it. */
export function ThemedText({ style, muted = false, ...rest }: ThemedTextProps) {
  const theme = useTheme();
  return (
    <Text style={[{ color: muted ? theme.muted : theme.text }, style]} {...rest} />
  );
}
