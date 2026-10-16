import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Sharp Sharp — Capacitor config.
 *
 * Dev mode: load the live Next.js dev server so changes hot-reload on the
 * device. Set CAP_BUILD=production to use a static export instead (requires
 * `next build` with output: 'export').
 *
 * For Android emulator, the host loopback is 10.0.2.2 (not localhost).
 * Override per-platform with capacitor.config.ts overrides if needed.
 */
const config: CapacitorConfig = {
  appId: "com.sharpsharp.app",
  appName: "Sharp Sharp",
  webDir: "out", // populated by `next build && next export`
  server:
    process.env.CAP_BUILD === "production"
      ? undefined
      : {
          url: "http://localhost:3000",
          cleartext: true,
        },
  ios: {
    contentInset: "always",
  },
  android: {
    backgroundColor: "#2E86AB",
  },
};

export default config;
