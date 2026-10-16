"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { userApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

const EMPLOYMENT_OPTIONS = [
  { value: "salaried", label: "Salaried (private sector)" },
  { value: "public_sector", label: "Public sector" },
  { value: "self_employed", label: "Self-employed / business owner" },
  { value: "nysc", label: "NYSC corps member" },
  { value: "student", label: "Student" },
  { value: "unemployed", label: "Unemployed" },
];

export default function ProfilePage() {
  const { user, setUser } = useAuthStore();
  const [form, setForm] = useState({
    employment_status: "",
    employer_name: "",
    employer_address: "",
    monthly_income: "",
    ippis_number: "",
    state_payroll_id: "",
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    userApi.getProfile().then((res) => {
      setUser(res.data);
    });
  }, [setUser]);

  const save = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload: Record<string, unknown> = {};
      if (form.employment_status) payload.employment_status = form.employment_status;
      if (form.employer_name) payload.employer_name = form.employer_name;
      if (form.employer_address) payload.employer_address = form.employer_address;
      if (form.monthly_income) payload.monthly_income = Number(form.monthly_income);
      if (form.ippis_number) payload.ippis_number = form.ippis_number;
      if (form.state_payroll_id) payload.state_payroll_id = form.state_payroll_id;

      await userApi.updateEmployment(payload);
      setMessage("Saved");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const isPublicSector =
    form.employment_status === "public_sector" ||
    form.employment_status === "salaried";

  return (
    <AppShell requireAuth>
      <div className="max-w-lg mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Your profile</h1>
        <p className="text-gray-500 text-sm mb-6">
          {user?.first_name} {user?.last_name} · {user?.phone_number}
        </p>

        <div className="bg-white rounded-xl p-5 border border-gray-200 mb-6">
          <h2 className="font-semibold text-gray-900 mb-3">Identity</h2>
          <Row label="Tier" value={user?.tier?.replace("tier_", "Tier ") || "—"} />
          <Row label="KYC status" value={user?.kyc_status?.replace(/_/g, " ") || "—"} />
          <Row label="Persona" value={user?.persona?.replace(/_/g, " ") || "—"} />
          <Row
            label="Ladder tier"
            value={String(user?.ladder_tier || 1)}
          />
          <Row
            label="Loans taken"
            value={String(user?.total_loans_taken || 0)}
          />
        </div>

        <div className="bg-white rounded-xl p-5 border border-gray-200">
          <h2 className="font-semibold text-gray-900 mb-1">Employment</h2>
          <p className="text-xs text-gray-500 mb-4">
            Affects affordability and pricing.
          </p>

          {error && (
            <div className="mb-3 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
              {error}
            </div>
          )}
          {message && (
            <div className="mb-3 p-3 bg-success/10 border border-success/30 text-success rounded-lg text-sm">
              {message}
            </div>
          )}

          <Field label="Employment status">
            <select
              value={form.employment_status}
              onChange={(e) =>
                setForm({ ...form, employment_status: e.target.value })
              }
              className="w-full px-4 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="">Select…</option>
              {EMPLOYMENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Employer name">
            <input
              value={form.employer_name}
              onChange={(e) =>
                setForm({ ...form, employer_name: e.target.value })
              }
              className="w-full px-4 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
            />
          </Field>

          <Field label="Monthly income (₦)">
            <input
              type="number"
              inputMode="numeric"
              value={form.monthly_income}
              onChange={(e) =>
                setForm({ ...form, monthly_income: e.target.value })
              }
              className="w-full px-4 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
            />
          </Field>

          {isPublicSector && (
            <>
              <Field label="IPPIS number (federal employees)">
                <input
                  value={form.ippis_number}
                  onChange={(e) =>
                    setForm({ ...form, ippis_number: e.target.value })
                  }
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                />
              </Field>
              <Field label="State payroll ID (state employees)">
                <input
                  value={form.state_payroll_id}
                  onChange={(e) =>
                    setForm({ ...form, state_payroll_id: e.target.value })
                  }
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-brand-500"
                />
              </Field>
            </>
          )}

          <button
            onClick={save}
            disabled={saving}
            className="w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </AppShell>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1.5 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-900 font-medium capitalize">{value}</span>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-3">
      <label className="block text-xs font-medium text-gray-600 mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}
