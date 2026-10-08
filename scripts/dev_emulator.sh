#!/usr/bin/env bash
# Launch the three pieces needed for emulator development:
#   1. FastAPI on the host (new terminal)
#   2. The Android emulator (background)
#   3. Expo Metro targeting the emulator (foreground)
#
# This script assumes a desktop environment is available (needed to display
# the emulator window). Run it on the host, not in a sandbox.
#
# Requires `emulator` and `adb` in PATH — see docs/mobile_emulator_setup.md.

set -euo pipefail

AVD_NAME="${AVD_NAME:-Pixel_6_API_34}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY_FILE="$HOME/.config/vi-api-key"

for tool in emulator adb; do
    if ! command -v "$tool" >/dev/null; then
        echo "✗ '$tool' is not in PATH. See docs/mobile_emulator_setup.md." >&2
        exit 1
    fi
done

echo "→ Ensuring the API key exists"
mkdir -p "$(dirname "$KEY_FILE")"
if [ ! -f "$KEY_FILE" ]; then
    openssl rand -hex 32 > "$KEY_FILE"
    echo "  Generated new key at $KEY_FILE"
fi
API_KEY="$(cat "$KEY_FILE")"
export API_KEY

echo "→ Starting FastAPI in a new terminal"
if command -v alacritty >/dev/null; then
    TERM_CMD=(alacritty -e)
elif command -v kitty >/dev/null; then
    TERM_CMD=(kitty)
elif command -v gnome-terminal >/dev/null; then
    TERM_CMD=(gnome-terminal --)
elif command -v konsole >/dev/null; then
    TERM_CMD=(konsole -e)
else
    echo "No supported terminal emulator found (alacritty, kitty, gnome-terminal, konsole)."
    echo "Start FastAPI manually in another terminal:"
    echo "  cd $PROJECT_ROOT && source .venv/bin/activate && \\"
    echo "  export API_KEY='$API_KEY' && \\"
    echo "  uvicorn backend.api.app:app --host 0.0.0.0 --port 8000"
    exit 1
fi

"${TERM_CMD[@]}" bash -c "
    cd '$PROJECT_ROOT'
    source .venv/bin/activate
    export API_KEY='$API_KEY'
    echo 'API key: $API_KEY'
    uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
" &

sleep 2

echo "→ Starting Android emulator: $AVD_NAME"
emulator -avd "$AVD_NAME" -no-snapshot-load -gpu host &

echo "→ Waiting for the emulator to appear on adb (up to 2 minutes)"
for _ in $(seq 1 60); do
    if adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
        echo "  Emulator booted"
        break
    fi
    sleep 2
done

echo "→ Starting Expo Metro targeting the emulator"
cd "$PROJECT_ROOT/mobile"
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT
npx expo start --android
