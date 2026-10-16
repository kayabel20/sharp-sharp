"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { applicationApi } from "@/lib/api";

const STEP_LABELS: Record<string, string> = {
  submitted: "Application received",
  kyc: "Verifying identity",
  fraud_check: "Running fraud checks",
  bank_analysis: "Analysing bank statement",
  income_estimation: "Estimating income",
  ml_scoring: "Calculating credit score",
  bureau_check: "Checking credit bureau",
  offer_generation: "Generating offer",
  human_review: "Awaiting human review",
};

const STEP_ORDER = [
  "submitted",
  "kyc",
  "fraud_check",
  "bank_analysis",
  "income_estimation",
  "ml_scoring",
  "bureau_check",
  "offer_generation",
];

const TERMINAL_STATUSES = new Set([
  "offer_generated",
  "offer_accepted",
  "disbursed",
  "rejected",
  "expired",
  "cancelled",
]);

export default function ApplicationStatusPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [app, setApp] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let timer: any;

    const tick = async () => {
      try {
        const res = await applicationApi.get(id);
        if (cancelled) return;
        setApp(res.data);
        setLoading(false);

        if (res.data.status === "offer_generated" && res.data.offer_id) {
          router.replace(`/applications/${id}/offer`);
          return;
        }

        if (!TERMINAL_STATUSES.has(res.data.status)) {
          timer = setTimeout(tick, 2000);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.response?.data?.detail || "Failed to load application");
          setLoading(false);
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id, router]);

  const currentIndex = app ? STEP_ORDER.indexOf(app.current_step) : -1;

  return (
    <AppShell requireAuth>
      <div className="max-w-lg mx-auto px-4 py-8">
        <Link
          href="/dashboard"
          className="text-sm text-gray-500 hover:text-gray-900"
        >
          ← Dashboard
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mt-4 mb-1">
          Application
        </h1>
        <p className="text-gray-500 mb-6 text-sm font-mono">
          {id.slice(0, 8)}…
        </p>

        {loading && (
          <div className="text-gray-400 text-sm">Loading…</div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {app && app.status === "rejected" && (
          <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-danger/10 flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-danger"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <h2 className="font-semibold text-gray-900 mb-2">
              Application declined
            </h2>
            <p className="text-sm text-gray-600 mb-1">
              Reason: <span className="font-medium">{app.decline_reason?.replace(/_/g, " ")}</span>
            </p>
            {app.decline_details && (
              <p className="text-sm text-gray-500">{app.decline_details}</p>
            )}
            <Link
              href="/dashboard"
              className="mt-6 block w-full text-center py-3 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition"
            >
              Back to dashboard
            </Link>
          </div>
        )}

        {app && app.status === "human_review" && (
          <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-warning/10 flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
            </div>
            <h2 className="font-semibold text-gray-900 mb-2">Pending review</h2>
            <p className="text-sm text-gray-600">
              Your application needs a quick human check. We'll text you when it's done — usually under 30 minutes.
            </p>
          </div>
        )}

        {app && !TERMINAL_STATUSES.has(app.status) && (
          <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
            <h2 className="font-semibold text-gray-900 mb-1">
              {STEP_LABELS[app.current_step] || "Processing…"}
            </h2>
            <p className="text-sm text-gray-500 mb-6">
              This usually takes under 60 seconds.
            </p>

            <ol className="space-y-3">
              {STEP_ORDER.map((step, i) => {
                const stepIndex = STEP_ORDER.indexOf(app.current_step);
                const isDone = i < stepIndex;
                const isActive = i === stepIndex;
                return (
                  <li key={step} className="flex items-center gap-3">
                    <span
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold ${
                        isDone
                          ? "bg-success text-white"
                          : isActive
                          ? "bg-brand-500 text-white animate-pulse"
                          : "bg-gray-100 text-gray-400"
                      }`}
                    >
                      {isDone ? "✓" : i + 1}
                    </span>
                    <span
                      className={`text-sm ${
                        isActive
                          ? "text-gray-900 font-medium"
                          : isDone
                          ? "text-gray-700"
                          : "text-gray-400"
                      }`}
                    >
                      {STEP_LABELS[step] || step}
                    </span>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </div>
    </AppShell>
  );
}
