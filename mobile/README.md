# Value Investing — Mobile app

Native Android app consuming the local FastAPI backend.

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

## Building an APK

Two paths are documented in the [APK section](#building-an-apk) below.
See also `eas.json`.

## Testing

```bash
npm test
npx tsc --noEmit
npx eslint . --ext .ts,.tsx
```
