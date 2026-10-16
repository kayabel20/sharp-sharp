"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Script from "next/script";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import { bankApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

const MONO_SDK_URL = "https://connect.withmono.com/connect.js";

interface BankConfig {
  mono_public_key: string | null;
  mono_configured: boolean;
  okra_configured: boolean;
  statement_period: string;
}

export default function BankLinkPage() {
  return (
    <Suspense fallback={null}>
      <BankLinkInner />
    </Suspense>
  );
}

function BankLinkInner() {
  const router = useRouter();
  const params = useSearchParams();
  const nextUrl = params.get("next") || "/apply";
  const { user } = useAuthStore();

  const [config, setConfig] = useState<BankConfig | null>(null);
  const [sdkReady, setSdkReady] = useState(false);
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState("");
  const [linked, setLinked] = useState<any>(null);

  // Hold a single MonoConnect instance for re-open / cleanup
  const monoRef = useRef<MonoConnectInstance | null>(null);

  useEffect(() => {
    bankApi
      .getConfig()
      .then((res) => setConfig(res.data))
      .catch(() => setConfig({
        mono_public_key: null,
        mono_configured: false,
        okra_configured: false,
        statement_period: "last6months",
      }));
  }, []);

  // Init Mono Connect once SDK + config are both ready
  useEffect(() => {
    if (!sdkReady || !config?.mono_configured || !config.mono_public_key) return;
    if (typeof window === "undefined" || !window.MonoConnect) return;
    if (monoRef.current) return;

    const mc = new window.MonoConnect({
      key: config.mono_public_key,
      data: {
        customer: {
          name: user ? `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim() : undefined,
          email: user?.email ?? undefined,
          phone: user?.phone_number,
        },
      },
      onSuccess: async ({ code }) => {
        setLinking(true);
        setError("");
        try {
          const res = await bankApi.linkAccount({
            provider: "mono",
            public_token: code,
          });
          setLinked(res.data);
        } catch (err: any) {
          setError(err.response?.data?.detail || "Bank link failed");
        } finally {
          setLinking(false);
        }
      },
      onClose: () => {
        // user dismissed the widget — no-op
      },
      onEvent: (event, data) => {
        if (event === "ERROR") {
          // eslint-disable-next-line no-console
          console.warn("Mono Connect error", data);
        }
      },
    });
    mc.setup();
    monoRef.current = mc;
  }, [sdkReady, config, user]);

  const openMonoWidget = () => {
    if (!monoRef.current) {
      setError("Mono widget not ready. Refresh and try again.");
      return;
    }
    setError("");
    monoRef.current.open();
  };

  const stubLink = async (provider: "mono" | "okra") => {
    setError("");
    setLinking(true);
    try {
      const res = await bankApi.linkAccount({
        provider,
        public_token: `stub-${provider}-${Date.now()}`,
      });
      setLinked(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Bank link failed");
    } finally {
      setLinking(false);
    }
  };

  const useRealMono = config?.mono_configured && config.mono_public_key;

  return (
    <AppShell requireAuth>
      {useRealMono && (
        <Script
          src={MONO_SDK_URL}
          strategy="afterInteractive"
          onLoad={() => setSdkReady(true)}
        />
      )}

      <div className="max-w-lg mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Link your bank</h1>
        <p className="text-gray-500 mb-6">
          We use 3-month bank statement to estimate your income and check
          affordability. Read-only access — we cannot move money out.
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {linked ? (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <div className="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-success"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
            <h2 className="font-semibold text-gray-900 text-lg mb-1">
              Bank linked
            </h2>
            <p className="text-sm text-gray-500 mb-1">
              {linked.institution || "Bank"}
              {linked.masked_account_number ? ` · ${linked.masked_account_number}` : ""}
            </p>
            {linked.account_name && (
              <p className="text-sm text-gray-500 mb-4">{linked.account_name}</p>
            )}
            {linked.note && (
              <p className="mt-2 text-xs text-warning bg-warning/10 p-2 rounded">
                {linked.note}
              </p>
            )}
            <button
              onClick={() => router.push(nextUrl)}
              className="w-full mt-4 py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 transition"
            >
              Continue
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {useRealMono ? (
              <button
                onClick={openMonoWidget}
                disabled={!sdkReady || linking}
                className="w-full p-4 bg-white border border-gray-200 rounded-xl hover:border-brand-500 disabled:opacity-50 transition flex items-center justify-between"
              >
                <div className="text-left">
                  <p className="font-semibold text-gray-900">
                    Link with Mono
                  </p>
                  <p className="text-sm text-gray-500">
                    {sdkReady
                      ? "All Nigerian banks supported"
                      : "Loading widget…"}
                  </p>
                </div>
                <span className="text-brand-500 font-semibold">→</span>
              </button>
            ) : (
              <>
                <button
                  onClick={() => stubLink("mono")}
                  disabled={linking}
                  className="w-full p-4 bg-white border border-gray-200 rounded-xl hover:border-brand-500 disabled:opacity-50 transition flex items-center justify-between"
                >
                  <div className="text-left">
                    <p className="font-semibold text-gray-900">
                      Link with Mono
                    </p>
                    <p className="text-sm text-gray-500">
                      All Nigerian banks supported
                    </p>
                  </div>
                  <span className="text-brand-500 font-semibold">→</span>
                </button>
                <button
                  onClick={() => stubLink("okra")}
                  disabled={linking}
                  className="w-full p-4 bg-white border border-gray-200 rounded-xl hover:border-brand-500 disabled:opacity-50 transition flex items-center justify-between"
                >
                  <div className="text-left">
                    <p className="font-semibold text-gray-900">Link with Okra</p>
                    <p className="text-sm text-gray-500">Alternative provider</p>
                  </div>
                  <span className="text-brand-500 font-semibold">→</span>
                </button>

                <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-xs text-yellow-800">
                  <p className="font-semibold mb-1">Dev mode</p>
                  <p>
                    Mono keys not configured. Set{" "}
                    <code>MONO_PUBLIC_KEY</code> and{" "}
                    <code>MONO_SECRET_KEY</code> in <code>backend/.env</code> to
                    enable the real Connect widget. The buttons above currently
                    create a stub-linked account so the rest of the pipeline can
                    run.
                  </p>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
