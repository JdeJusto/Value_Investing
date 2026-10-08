import { getEffectiveBaseUrl } from "../config";

const BASE = { lanUrl: "", tailscaleUrl: "", useTailscale: false };

test("uses the LAN URL by default", () => {
  expect(
    getEffectiveBaseUrl({ ...BASE, lanUrl: "http://192.168.0.10:8000" }),
  ).toBe("http://192.168.0.10:8000");
});

test("uses the Tailscale URL when preferred and configured", () => {
  expect(
    getEffectiveBaseUrl({
      lanUrl: "http://192.168.0.10:8000",
      tailscaleUrl: "http://100.64.1.5:8000",
      useTailscale: true,
    }),
  ).toBe("http://100.64.1.5:8000");
});

test("falls back to the LAN URL when Tailscale is preferred but empty", () => {
  expect(
    getEffectiveBaseUrl({
      lanUrl: "http://192.168.0.10:8000",
      tailscaleUrl: "",
      useTailscale: true,
    }),
  ).toBe("http://192.168.0.10:8000");
});

test("strips trailing slashes and whitespace", () => {
  expect(
    getEffectiveBaseUrl({
      ...BASE,
      lanUrl: "  http://192.168.0.10:8000/  ",
    }),
  ).toBe("http://192.168.0.10:8000");
});
