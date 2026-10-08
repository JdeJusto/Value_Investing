# Android emulator setup for the mobile app

> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)
> Companion docs: `mobile/README.md`, `docs/mobile_app_design.md`

## Why an emulator

Testing the mobile app on a physical phone hit repeated network issues
(Tailscale, router AP isolation, VPN conflicts, Expo Go SDK mismatches).
The Android emulator on the same Arch machine speaks to the API on the host
via the special IP **`10.0.2.2`**, which is an alias for the host's
`localhost`. No Tailscale, no hotspot, no router configuration.

Tradeoff: the emulator uses ~4 GB of RAM and needs KVM for smooth
performance. If the machine is short on either, use the physical phone
(see `mobile/README.md`).

## Requirements

- Arch Linux with `linux` or `linux-lts` (KVM support built-in)
- CPU with virtualization extensions (Intel VT-x / AMD-V) enabled in the BIOS
- ~10 GB free disk for the SDK + emulator system images
- ~4 GB RAM free while the emulator runs

Verify KVM is available:

```bash
ls -l /dev/kvm
# Expected: crw-rw---- 1 root kvm ... /dev/kvm

groups
# Your user must be in the "kvm" group. If not:
#   sudo usermod -aG kvm $USER
# then log out and back in.
```

## Installation

### 1. Install Android Studio

Android Studio bundles the SDK manager, the emulator and the platform tools.

```bash
# Official repositories (preferred):
sudo pacman -S android-studio

# If your mirror does not carry it, use the AUR:
yay -S android-studio
```

CLI-only alternative (no IDE; the emulator + SDK tools):

```bash
yay -S android-sdk android-sdk-platform-tools \
       android-sdk-build-tools android-emulator
```

### 2. First launch

```bash
android-studio
```

On the first run it asks to download the Android SDK. Accept the default
location (`~/Android/Sdk`).

### 3. Create a Virtual Device (AVD)

In Android Studio:

1. **Tools → Device Manager → Create Device**
2. Category: **Phone** → **Pixel 6** (or Pixel 7)
3. System Image: **API 34 (Android 14)**, "Google APIs", `x86_64`
4. Name: `Pixel_6_API_34`
5. Memory: **4096 MB RAM**, 2 GB internal storage
6. **Finish**

### 4. Add the emulator tools to your PATH

```bash
echo 'export ANDROID_HOME=$HOME/Android/Sdk' >> ~/.zshrc
echo 'export PATH=$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools' >> ~/.zshrc
source ~/.zshrc

# Verify:
which emulator
which adb
```

## One-command launcher

If you have a supported terminal emulator (alacritty, kitty, gnome-terminal
or konsole), the whole stack can be started with:

```bash
./scripts/dev_emulator.sh
```

It ensures the API key exists (generating and reusing
`~/.config/vi-api-key`), opens FastAPI in a new terminal, boots the
emulator, waits for it to appear on `adb`, and starts Expo Metro targeting
it. `Ctrl+C` on the Metro terminal stops everything.

Configure the app once with:

- **Emulator mode**: ON
- **API key**: the value printed in the FastAPI terminal

## Daily workflow

### Terminal 1 — API server

```bash
cd /home/caudillo/Value_Investing
source .venv/bin/activate

# Generate the API key once and reuse it on later runs:
export API_KEY="$(cat ~/.config/vi-api-key 2>/dev/null || \
  openssl rand -hex 32 | tee ~/.config/vi-api-key)"

uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
```

Note the `API_KEY` value — the mobile app needs it. Binding to `0.0.0.0`
keeps the API reachable from both the emulator and the LAN.

### Terminal 2 — Emulator

```bash
emulator -avd Pixel_6_API_34 -no-snapshot-load -gpu host
```

Wait for Android to boot (~30-60 s). You will see the home screen.

### Terminal 3 — Metro + install on the emulator

```bash
cd /home/caudillo/Value_Investing/mobile
npx expo start --android
```

Expo detects the running emulator via `adb`, builds the dev bundle and
installs the app automatically. The app opens on the emulator.

### Configure the app

In the app → **Settings**:

- **Emulator mode (10.0.2.2)**: ON
- **API key**: paste the value from Terminal 1
- **Test connection** → green ✓

Then **Home** → type `AAPL` → the card should show Apple Inc. with real
data from Financial-DataBase.

## Verifying the connection from the emulator

If the app fails, open Chrome inside the emulator and visit:

```
http://10.0.2.2:8000/api/v1/version
```

Expected: a JSON blob with `"api_version": "v1"` (this endpoint needs no
API key, so it isolates network problems from auth problems).

If this fails, the API is not reachable from the emulator. Check:

- The uvicorn process is running on the host (Terminal 1).
- It is bound to `0.0.0.0:8000`, not `127.0.0.1:8000`.
- No host firewall blocks the emulator bridge.

## Building the APK for the physical phone (when the app is done)

The emulator is for development. When the app is ready for daily use on the
phone, build an APK.

### Option A — EAS Build (cloud)

```bash
cd mobile
npm install -g eas-cli
eas login
eas build -p android --profile preview
# Download the .apk from the link EAS prints.
```

### Option B — Local Gradle

```bash
cd mobile
npx expo prebuild --platform android
cd android
./gradlew assembleRelease
# Result: android/app/build/outputs/apk/release/app-release.apk
```

### Install on the phone

```bash
adb install app-release.apk
```

Or transfer the file to the phone via USB / Signal / email and open it
(enable "Install from unknown sources").

On the phone, in the app's Settings:

- **Emulator mode**: OFF
- **LAN URL** or **Tailscale URL**: the reachable address of your Arch
  machine (see `mobile/README.md` for the Tailscale section).

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Emulator is very slow | No KVM acceleration | Verify `/dev/kvm` and the `kvm` group membership |
| `emulator: command not found` | PATH not updated | `source ~/.zshrc` |
| App cannot reach the API | uvicorn bound to 127.0.0.1 | Restart with `--host 0.0.0.0` |
| App shows `NETWORK_ERROR` | Wrong IP in Settings | Enable Emulator mode |
| `adb: no devices` | Emulator not running | Wait for boot; `adb devices` to verify |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | Old app signature on the emulator | Uninstall the old app: `adb uninstall com.jdejusto.valueinvesting` |
