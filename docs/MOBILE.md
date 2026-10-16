# Mobile distribution — Sharp Sharp

Three ways to ship the app to a phone, ordered by effort.

## 1. PWA (works today, no toolchain)

The frontend now includes a Web App Manifest, iOS/Android icons, and theme
colour. Visit `localhost:3000` from your phone (same WiFi) and:

- **iOS Safari** → Share → "Add to Home Screen". Launches in standalone mode,
  no browser chrome, with the Sharp Sharp icon.
- **Android Chrome** → menu → "Install app". Installs as a top-level app.

To open from an external phone, expose your Mac:

```bash
# pick one
ngrok http 3000           # easiest
cloudflared tunnel --url http://localhost:3000
```

## 2. Capacitor (real .ipa / .apk, needs Xcode + Android Studio)

Capacitor wraps the Next.js app in a native WebView shell. The scaffolding is
already in `frontend/ios/` and `frontend/android/`.

Prereqs:
- **iOS:** install full Xcode from the App Store, then run
  `sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer`.
- **Android:** install Android Studio, then in Settings → SDK Manager install
  Platform 34 + Build Tools.

### Dev mode (hot-reload from localhost:3000)

Already configured. With the Docker stack running:

```bash
cd ~/sharp-sharp/frontend

# iOS simulator — opens Xcode, Run > select iPhone 15
npx cap open ios

# Android emulator — opens Studio, Run > select Pixel 8
npx cap open android
```

The simulator/emulator will load `http://localhost:3000` directly, so any code
change in the Next.js app appears after a refresh.

> Android emulator caveat: `localhost` from inside the emulator points to the
> emulator itself. Either use `10.0.2.2:3000` or run a `adb reverse tcp:3000 tcp:3000`.

### Production mode (static bundle)

To ship a self-contained app that doesn't depend on the dev server, the
Next.js app needs a static export. Edit `next.config.mjs`:

```js
const nextConfig = {
  output: "export",
};
```

Then:

```bash
cd ~/sharp-sharp/frontend
CAP_BUILD=production npm run build
npx cap sync
npx cap open ios       # or android
```

Hit **Run** in Xcode/Studio. Output is the `.ipa`/`.apk` you'd upload to
TestFlight or Google Play internal testing.

> Caveat: `output: "export"` disables API routes and SSR. Since this app uses
> `"use client"` everywhere and talks to the FastAPI backend over HTTP, that's
> fine — but you'll need to point `NEXT_PUBLIC_API_URL` at a publicly reachable
> backend (your laptop won't be reachable from a TestFlight build).

## 3. Real React Native rebuild (days)

If you outgrow Capacitor (need real native gestures, push notifications,
camera, biometrics with first-class APIs), rewrite the screens in React Native.
Most of the Tailwind UI work translates to NativeWind. Backend stays untouched.

---

## Design assets

- `docs/design-stamp.html` — open locally; renders all 8 screens at iPhone
  viewport, embeds the live web app via iframes.
- `docs/design-tokens.json` — colour palette, type scale, radius/spacing,
  shadow tokens. Import into Figma Variables or feed to Tailwind.
- `frontend/public/icon-{192,512}.png` and `apple-touch-icon.png` — PWA icons
  (programmatically generated from the brand colour, replace with proper art
  before shipping).

For a Figma file: install the **html.to.design** plugin, point it at
`http://localhost:3000`, and import each route as an editable Figma frame —
takes about a minute and gives you fully editable components.
