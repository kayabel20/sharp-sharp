"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { applicationApi, bankApi } from "@/lib/api";

const TENURE_OPTIONS = [
  { days: 14, label: "14 days" },
  { days: 30, label: "30 days" },
  { days: 60, label: "60 days" },
  { days: 90, label: "90 days" },
];

export default function ApplyPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    requested_amount: "",
    requested_tenure_days: 30,
    loan_purpose: "",
    disbursement_account_number: "",
    disbursement_bank_code: "",
  });

  // Gate: require a linked bank before submission so bank_service has data.
  useEffect(() => {
    bankApi
      .listLinked()
      .then((res) => {
        if (!res.data || res.data.length === 0) {
          router.replace(
            `/onboarding/bank?next=${encodeURIComponent("/apply")}`
          );
        }
      })
      .catch(() => {
        // If config endpoint fails, don't block — let the user proceed.
      });
  }, [router]);

  const handleSubmit = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await applicationApi.submit({
        requested_amount: Number(form.requested_amount),
        requested_tenure_days: form.requested_tenure_days,
        loan_purpose: form.loan_purpose || undefined,
        disbursement_account_number: form.disbursement_account_number,
        disbursement_bank_code: form.disbursement_bank_code,
      });
      router.push(`/applications/${res.data.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Application failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell requireAuth>
    <div className="max-w-lg mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Apply for a Loan</h1>
      <p className="text-gray-500 mb-8">
        Get an instant decision in minutes.
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
          {error}
        </div>
      )}

      {step === 1 && (
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          <h2 className="font-semibold text-gray-900 mb-4">
            Step 1: Loan Amount
          </h2>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              How much do you need? (&#8358;)
            </label>
            <input
              type="number"
              value={form.requested_amount}
              onChange={(e) =>
                setForm({ ...form, requested_amount: e.target.value })
              }
              placeholder="50000"
              min={5000}
              max={1000000}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none text-lg"
            />
            <p className="text-xs text-gray-400 mt-1">Min: &#8358;5,000 &middot; Max: &#8358;1,000,000</p>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Repayment Period
            </label>
            <div className="grid grid-cols-4 gap-2">
              {TENURE_OPTIONS.map((opt) => (
                <button
                  key={opt.days}
                  onClick={() =>
                    setForm({ ...form, requested_tenure_days: opt.days })
                  }
                  className={`py-2 px-3 rounded-lg text-sm font-medium border transition ${
                    form.requested_tenure_days === opt.days
                      ? "border-brand-500 bg-brand-50 text-brand-600"
                      : "border-gray-200 text-gray-600 hover:border-gray-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Purpose (optional)
            </label>
            <input
              type="text"
              value={form.loan_purpose}
              onChange={(e) =>
                setForm({ ...form, loan_purpose: e.target.value })
              }
              placeholder="e.g., Business expenses, Emergency"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
            />
          </div>

          <button
            onClick={() => setStep(2)}
            disabled={!form.requested_amount || Number(form.requested_amount) < 5000}
            className="w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
          >
            Continue
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
          <h2 className="font-semibold text-gray-900 mb-4">
            Step 2: Bank Details
          </h2>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Account Number
            </label>
            <input
              type="text"
              value={form.disbursement_account_number}
              onChange={(e) =>
                setForm({
                  ...form,
                  disbursement_account_number: e.target.value,
                })
              }
              placeholder="0123456789"
              maxLength={10}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Bank Code
            </label>
            <select
              value={form.disbursement_bank_code}
              onChange={(e) =>
                setForm({ ...form, disbursement_bank_code: e.target.value })
              }
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none"
            >
              <option value="">Select bank</option>
              <option value="044">Access Bank</option>
              <option value="063">Diamond Bank</option>
              <option value="050">Ecobank</option>
              <option value="070">Fidelity Bank</option>
              <option value="011">First Bank</option>
              <option value="058">GTBank</option>
              <option value="030">Heritage Bank</option>
              <option value="082">Keystone Bank</option>
              <option value="076">Polaris Bank</option>
              <option value="221">Stanbic IBTC</option>
              <option value="068">Standard Chartered</option>
              <option value="232">Sterling Bank</option>
              <option value="032">Union Bank</option>
              <option value="033">UBA</option>
              <option value="215">Unity Bank</option>
              <option value="035">Wema Bank</option>
              <option value="057">Zenith Bank</option>
            </select>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => setStep(1)}
              className="flex-1 py-3 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition"
            >
              Back
            </button>
            <button
              onClick={handleSubmit}
              disabled={
                loading ||
                !form.disbursement_account_number ||
                !form.disbursement_bank_code
              }
              className="flex-1 py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
            >
              {loading ? "Submitting..." : "Submit Application"}
            </button>
          </div>
        </div>
      )}
    </div>
    </AppShell>
  );
}
