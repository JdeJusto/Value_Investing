# Value Investing — Mobile app

Native Android app consuming the local FastAPI backend. Expo (React Native +
TypeScript) with Expo Router; see `docs/mobile_app_design.md` for the full
architecture and issue [#27](https://github.com/JdeJusto/Value_Investing/issues/27)
for the roadmap.

## Requirements

- Node.js >= 20
- The API server running on the same network (`docs/api_design.md`)

## Development

```bash
cd mobile
npm install
npx expo start
```

Scan the QR with Expo Go (Android) or run on a device via
`npx expo run:android`.

## Configuration

In the app, open **Settings** and set:

- **LAN URL**: the IP of the machine running the API (find it with
  `ip -4 addr show | grep inet`).
- **Tailscale URL** (optional): the Tailscale IP of the same machine, for
  remote use.
- **API key**: the same value as `API_KEY` in the server's `.env`.

Settings persist across restarts (AsyncStorage). The **Test connection**
button calls `GET /api/v1/health` with the current configuration.

> Security note: the API key is stored in AsyncStorage for the skeleton.
> Upgrade to `expo-secure-store` once a development build is in place (it
> needs a native module).

## Testing

```bash
npm test          # jest (unit + component)
npm run typecheck # tsc --noEmit
npm run lint      # eslint (flat config)
```

## Building an APK

Two paths are supported. The EAS path needs no Android SDK locally; the
local path needs the Android SDK installed on Arch (a large download).

### Easy path (EAS Build, cloud)

```bash
npm install -g eas-cli
eas login
eas build:configure
eas build -p android --profile preview
# Download the APK link printed at the end
```

`eas.json` defines two profiles: `preview` (APK, internal distribution) and
`production` (AAB for a future Play Store release).

### Local path (prebuild + Gradle)

```bash
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease
# android/app/build/outputs/apk/release/app-release.apk
```

The keystore must exist outside the repo (for example
`~/.android/release.keystore`); generate one with:

```bash
keytool -genkeypair -v -keystore ~/.android/release.keystore \
  -alias valueinvesting -keyalg RSA -keysize 2048 -validity 10000
```

### Install on the phone

- **Via USB**: `adb install <path>.apk`
- **Without USB**: send the APK to yourself (email, Signal, etc.), open it on
  the phone, and enable "Install from unknown sources" for the file manager.

### Connecting the app to the API

See "Configuration" above. After the first launch, set the URLs and the API
key once and the app remembers them.

## Troubleshooting

- **`npx expo install` fails with `EALLOWSCRIPTS`**: the npx wrapper exports
  the user-level `allow-scripts` npm setting, which npm rejects for
  project-scoped installs. Use the local binary instead:
  `./node_modules/.bin/expo install <package>`.
- **Metro is running but the phone cannot connect**: make sure the phone is
  on the same Wi-Fi and the API URL uses the machine's LAN IP, not
  `localhost`.
