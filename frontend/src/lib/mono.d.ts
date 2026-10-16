/**
 * Minimal ambient typing for the Mono Connect SDK loaded from CDN.
 * Full surface: https://docs.mono.co/docs/mono-connect-popup
 */
export {};

declare global {
  interface MonoConnectInstance {
    setup(): void;
    open(): void;
    close(): void;
    reauthorise?(reauth_token: string): void;
  }

  interface MonoConnectConfig {
    key: string;
    scope?: "auth" | "reauth";
    data?: {
      customer?: { name?: string; email?: string; phone?: string };
      reference?: string;
    };
    onSuccess?: (response: { code: string; id?: string }) => void;
    onClose?: () => void;
    onLoad?: () => void;
    onEvent?: (eventName: string, data: unknown) => void;
  }

  interface Window {
    MonoConnect?: new (config: MonoConnectConfig) => MonoConnectInstance;
  }
}
