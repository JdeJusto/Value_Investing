# Mobile App Design — Value Investing (Android-first)

> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)

Generated: 2026-10-07

This document describes the native mobile app architecture that consumes the
Value Investing REST API. **Android-first**; iOS is a future nice-to-have.

---

## C1 — Framework Choice: React Native + Expo

**Decision:** React Native with Expo (TypeScript)

| Criteria | React Native (Expo) | Flutter |
|----------|---------------------|---------|
| Language | TypeScript | Dart |
| APK build without Android Studio | Expo EAS (cloud) or `expo prebuild` | `flutter build apk` local |
| Learning curve (from Python) | Medium (JS/TS) | Medium (Dart) |
| Financial chart libraries | Many, mature (`victory-native`, `react-native-svg-charts`) | Good but fewer |
| Fintech community | Huge | Growing |
| OTA updates without rebuilding APK | Yes (EAS Update) | No (or limited) |
| Base APK size | ~40 MB | ~20 MB |

**Why Expo:**
- EAS Update allows pushing JS changes without regenerating the APK — essential for fast iteration
- Expo Go for instant testing on device
- Managed workflow handles keystore, signing, and build config
- Huge fintech ecosystem (charts, tables, forms)
- TypeScript shares mental model with Python developers

**The user can override** — Flutter is a valid alternative if APK size matters.

**Dependencies (NOT installed yet — documented for Phase 6):**
```json
{
  "expo": "~52.0.0",
  "expo-router": "~4.0.0",
  "react-native": "0.76.x",
  "@tanstack/react-query": "^5.60.0",
  "zustand": "^5.0.0",
  "victory-native": "^41.0.0",
  "react-native-safe-area-context": "4.12.x",
  "react-native-screens": "~4.0.0",
  "expo-secure-store": "~14.0.0",
  "expo-status-bar": "~2.0.0"
}
```

---

## C2 — Screen Structure (6 tabs)

Bottom tab navigation (6 items max):

### 1. Home
- Portfolio summary (value, PnL, top movers)
- Alerts feed (CRITICAL + WARNING only)
- Quick search bar (ticker)
- Pull to refresh

### 2. Company Detail (core screen)
- Header: ticker, name, price, daily change
- Tabs: **Overview** · **Methodologies** · **DCF** · **Financials** · **Filings**
- Swipe between tabs
- Pull to refresh per tab
- Overview: key ratios + verdict summary
- Methodologies: 8 cards (verdict, score, key reason)
- DCF: intrinsic value, margin of safety, sensitivity table
- Financials: yearly table (revenue, net income, FCF, etc.)
- Filings: list of SEC filings, tap to expand statement/section

### 3. Screener
- Filters as a bottom sheet (universe, sector, P/E max, ROE min, FCF yield min, market cap range)
- Results list with virtualized `FlatList`
- Tap a row → Company Detail
- Pagination: infinite scroll

### 4. Consensus
- Top by consensus score
- Best per Lynch category
- Disagreement zone
- Sort lenses (score, BUYs, AVOIDs)

### 5. Portfolio
- Positions list (ticker, shares, avg price, PnL, weight)
- Add / exit / remove (with confirm dialogs)
- Performance tab: total return, drawdown, allocation pie chart

### 6. Settings
- API base URLs (LAN + Tailscale)
- API key (secure storage)
- Theme (light/dark/system)
- Demo mode toggle (bundled fixtures, no backend)

### Mobile-Specific Considerations
- **Pull-to-refresh** on every data screen
- **Offline indicator** when the API is unreachable
- **Skeleton loaders** (not spinners) for tables
- **Charts:** `victory-native` for line/bar; `react-native-svg` for sparklines
- **Long tables:** virtualized `FlatList` with `windowSize=10`, `maxToRenderPerBatch=10`
- **Number formatting:** reuse the abbreviation convention from the UI (`$416.16B`, `12.34%`)
- **Deep links:** `valueinvesting://company/AAPL` for notifications → detail

---

## C3 — State Management

**No Redux.**

| Concern | Solution | Size |
|---------|----------|------|
| API state (fetch, cache, refetch, retries) | **TanStack Query (React Query)** | Library |
| Global settings (API URLs, key, theme, demo mode) | **Zustand** — 1 store, ~50 lines | Tiny |
| UI-only state (form inputs, modals) | `useState` / `useReducer` | Built-in |
| Navigation state | Expo Router (file-based) | Library |

**Why TanStack Query:**
- Automatic caching, deduplication, background refetching
- Stale-while-revalidate — shows cached data immediately, refreshes in background
- Retry logic (exponential backoff) out of the box
- Query invalidation on mutations (portfolio add/exit)
- Offline support via `persistQueryClient`

**Why Zustand:**
- Minimal boilerplate vs Redux
- Persists to AsyncStorage / SecureStore easily
- No context providers needed

---

## C4 — Offline / Degraded Behavior

| Scenario | Behavior |
|----------|----------|
| API unreachable | Show banner: "Offline — showing cached data" |
| Stale data (> 1h old) | Show banner: "Showing data from 2h ago" |
| Portfolio action while offline | Disable add/exit/remove; tooltip: "Requires connection" |
| First launch with no cache | Show empty states + retry button |
| Demo mode enabled | Use bundled fixtures; no network at all |

**Cache persistence:** `@tanstack/query-async-storage-persister` + AsyncStorage.
Last successful response per endpoint survives app restarts.

**Demo mode:** The Settings screen has a "Demo mode" toggle. When on, the app
reads from `assets/fixtures/*.json` (bundled at build time) instead of the API.
This allows demos without any backend running.

---

## C5 — Build & Distribution

### Personal Use (No Play Store)

**EAS Build (recommended):**
```bash
npx eas build --platform android --profile preview
# Produces: app-release.apk (signed with generated keystore)
```

- Keystore stored in `~/Documents/expo-keystore/` (NOT in the repo)
- Install via `adb install app-release.apk` or share the APK file
- OTA updates: `npx eas update --branch preview` (no rebuild needed)

**Alternative (local build):**
```bash
npx expo prebuild
cd android && ./gradlew assembleRelease
# Produces: app/build/outputs/apk/release/app-release.apk
```

### Play Store (Future, Optional)
- Same EAS project can produce an AAB: `npx eas build --platform android --profile production`
- No redesign needed — only store listing, screenshots, privacy policy
- **Not promised in the roadmap** — personal use is the primary target

### Update Workflow
1. Code change → `git commit`
2. `npx eas update --branch preview --message "Fix screener pagination"`
3. App checks for updates on launch (Expo Updates)

---

## C6 — Settings Screen (Day One)

The app must support configurable base URLs from the start:

```
API Base URL (LAN):      http://192.168.1.42:8000
API Base URL (Tailscale): http://100.64.0.5:8000
API Key:                 ••••••••••••••••••••••••••••••
Theme:                   [Light] [Dark] [System]
Demo mode:               [ ] Off
```

- Stores config in SecureStore (API key) + AsyncStorage (URLs, theme)
- "Test connection" button → `GET /api/v1/health`
- Falls back from LAN to Tailscale automatically when LAN is unreachable

---

## C7 — Files Created

- `docs/mobile_app_design.md` — this document
- Referenced by: `docs/api_roadmap.md`