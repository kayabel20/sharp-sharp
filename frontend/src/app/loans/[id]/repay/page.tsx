"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { loanApi } from "@/lib/api";

const formatNaira = (n: number) =>
  `₦${(n || 0).toLocaleString("en-NG", { maximumFractionDigits: 0 })}`;

export default function RepayPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [loan, setLoan] = useState<any>(null);
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    loanApi
      .get(id)
      .then((res) => {
        setLoan(res.data);
        setAmount(String(Math.round(res.data.total_outstanding)));
      })
      .catch((err) =>
        setError(err.response?.data?.detail || "Failed to load loan")
      )
      .finally(() => setLoading(false));
  }, [id]);

  const handlePay = async () => {
    setError("");
    const amt = Number(amount);
    if (!amt || amt <= 0) {
      setError("Enter a valid amount");
      return;
    }
    setSubmitting(true);
    try {
      const res = await loanApi.initiateRepayment(id, { amount: amt });
      setResult(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Could not initiate payment");
    } finally {
      setSubmitting(false);
    }
  };

  const setQuick = (pct: number) => {
    if (!loan) return;
    setAmount(String(Math.round(loan.total_outstanding * pct)));
  };

  if (loading) {
    return (
      <AppShell requireAuth>
        <div className="max-w-lg mx-auto px-4 py-8 text-gray-400 text-sm">
          Loading…
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell requireAuth>
      <div className="max-w-lg mx-auto px-4 py-8">
        <Link
          href={`/loans/${id}`}
          className="text-sm text-gray-500 hover:text-gray-900"
        >
          ← Loan
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mt-4 mb-1">Pay now</h1>
        <p className="text-gray-500 text-sm mb-6">
          Outstanding: {loan && formatNaira(loan.total_outstanding)}
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {result ? (
          <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
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
            <h2 className="font-semibold text-gray-900 mb-2">
              Payment initiated
            </h2>
            <p className="text-sm text-gray-600 mb-1">
              Amount: {formatNaira(result.amount)}
            </p>
            <p className="text-sm text-gray-600 mb-1">
              Reference:{" "}
              <span className="font-mono text-xs">{result.reference}</span>
            </p>
            {result.note && (
              <p className="mt-3 text-xs text-warning bg-warning/10 p-2 rounded">
                {result.note}
              </p>
            )}
            <button
              onClick={() => router.push(`/loans/${id}`)}
              className="mt-6 w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 transition"
            >
              Back to loan
            </button>
          </div>
        ) : (
          <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Amount to pay
            </label>
            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-lg">
                ₦
              </span>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                inputMode="numeric"
                className="w-full pl-9 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none text-lg"
              />
            </div>

            <div className="grid grid-cols-3 gap-2 mt-3">
              <button
                onClick={() => setQuick(0.25)}
                className="py-2 text-sm border border-gray-200 rounded-lg hover:border-brand-500 transition"
              >
                25%
              </button>
              <button
                onClick={() => setQuick(0.5)}
                className="py-2 text-sm border border-gray-200 rounded-lg hover:border-brand-500 transition"
              >
                50%
              </button>
              <button
                onClick={() => setQuick(1)}
                className="py-2 text-sm border border-gray-200 rounded-lg hover:border-brand-500 transition"
              >
                Full
              </button>
            </div>

            <button
              onClick={handlePay}
              disabled={submitting}
              className="mt-6 w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
            >
              {submitting ? "Initiating…" : "Pay with card / bank"}
            </button>
            <p className="text-xs text-gray-400 mt-3 text-center">
              Powered by Flutterwave (sandboxed in dev)
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
