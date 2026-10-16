"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { loanApi } from "@/lib/api";

interface Loan {
  id: string;
  principal_amount: number;
  interest_amount: number;
  total_amount_due: number;
  total_outstanding: number;
  outstanding_principal: number;
  outstanding_interest: number;
  total_paid: number;
  status: string;
  tenure_days: number;
  disbursement_date: string | null;
  maturity_date: string | null;
  days_past_due: number;
  interest_rate_monthly: number;
  repayment_frequency: string;
  risk_tier: number | null;
}

interface ScheduleItem {
  installment_number: number;
  due_date: string;
  total_due: number;
  principal_due: number;
  interest_due: number;
  amount_paid: number;
  is_paid: boolean;
}

interface Repayment {
  id: string;
  amount: number;
  payment_date: string;
  payment_method: string | null;
  reference: string | null;
  status: string;
}

const formatNaira = (n: number) =>
  `₦${(n || 0).toLocaleString("en-NG", { maximumFractionDigits: 0 })}`;

const formatDate = (iso: string | null) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-NG", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export default function LoanDetailPage() {
  return (
    <Suspense fallback={null}>
      <LoanDetailInner />
    </Suspense>
  );
}

function LoanDetailInner() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const welcome = params.get("welcome") === "1";

  const [loan, setLoan] = useState<Loan | null>(null);
  const [schedule, setSchedule] = useState<ScheduleItem[]>([]);
  const [repayments, setRepayments] = useState<Repayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = async () => {
    try {
      const [l, s, r] = await Promise.all([
        loanApi.get(id),
        loanApi.getSchedule(id),
        loanApi.getRepayments(id),
      ]);
      setLoan(l.data);
      setSchedule(s.data);
      setRepayments(r.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load loan");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const nextDue = useMemo(
    () => schedule.find((s) => !s.is_paid),
    [schedule]
  );

  const progressPct = useMemo(() => {
    if (!loan) return 0;
    if (loan.total_amount_due === 0) return 0;
    return Math.min(100, (loan.total_paid / loan.total_amount_due) * 100);
  }, [loan]);

  if (loading) {
    return (
      <AppShell requireAuth>
        <div className="max-w-3xl mx-auto px-4 py-8 text-gray-400 text-sm">
          Loading loan…
        </div>
      </AppShell>
    );
  }

  if (error) {
    return (
      <AppShell requireAuth>
        <div className="max-w-3xl mx-auto px-4 py-8">
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        </div>
      </AppShell>
    );
  }

  if (!loan) return null;

  return (
    <AppShell requireAuth>
      <div className="max-w-3xl mx-auto px-4 py-8">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-900">
          ← Dashboard
        </Link>

        {welcome && (
          <div className="mt-4 p-4 bg-success/10 border border-success/30 text-success rounded-lg text-sm">
            🎉 Loan disbursed. Funds are on the way to your bank.
          </div>
        )}

        <h1 className="text-2xl font-bold text-gray-900 mt-4 mb-1">
          Loan {id.slice(0, 8)}…
        </h1>
        <p className="text-gray-500 text-sm mb-6">
          Disbursed {formatDate(loan.disbursement_date)} · Matures{" "}
          {formatDate(loan.maturity_date)}
        </p>

        <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm mb-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-sm text-gray-500">Outstanding</p>
              <p className="text-3xl font-bold text-gray-900">
                {formatNaira(loan.total_outstanding)}
              </p>
            </div>
            <span
              className={`px-3 py-1 rounded-full text-xs font-medium ${
                loan.days_past_due > 0
                  ? "bg-red-100 text-red-700"
                  : loan.status === "paid_off"
                  ? "bg-gray-100 text-gray-700"
                  : "bg-green-100 text-green-700"
              }`}
            >
              {loan.days_past_due > 0
                ? `${loan.days_past_due} DPD`
                : loan.status.replace(/_/g, " ")}
            </span>
          </div>

          <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-1">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mb-6">
            {formatNaira(loan.total_paid)} paid of{" "}
            {formatNaira(loan.total_amount_due)}
          </p>

          {nextDue && loan.total_outstanding > 0 && (
            <div className="border-t border-gray-100 pt-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500">Next payment</p>
                <p className="font-semibold text-gray-900">
                  {formatNaira(nextDue.total_due - nextDue.amount_paid)} ·{" "}
                  {formatDate(nextDue.due_date)}
                </p>
              </div>
              <Link
                href={`/loans/${id}/repay`}
                className="px-5 py-2 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 transition text-sm"
              >
                Pay now
              </Link>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4 mb-6 text-sm">
          <Stat label="Principal" value={formatNaira(loan.principal_amount)} />
          <Stat label="Total interest" value={formatNaira(loan.interest_amount)} />
          <Stat
            label="Monthly rate"
            value={`${(loan.interest_rate_monthly * 100).toFixed(2)}%`}
          />
          <Stat label="Frequency" value={capitalize(loan.repayment_frequency)} />
        </div>

        <h2 className="font-semibold text-gray-900 mb-3">Repayment schedule</h2>
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2">#</th>
                <th className="text-left px-4 py-2">Due</th>
                <th className="text-right px-4 py-2">Amount</th>
                <th className="text-right px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {schedule.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="text-center py-6 text-gray-400 text-sm"
                  >
                    No schedule yet
                  </td>
                </tr>
              ) : (
                schedule.map((s) => (
                  <tr key={s.installment_number} className="border-t border-gray-100">
                    <td className="px-4 py-3 text-gray-500">
                      {s.installment_number}
                    </td>
                    <td className="px-4 py-3 text-gray-900">
                      {formatDate(s.due_date)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-900">
                      {formatNaira(s.total_due)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {s.is_paid ? (
                        <span className="text-success text-xs font-medium">
                          Paid
                        </span>
                      ) : s.amount_paid > 0 ? (
                        <span className="text-warning text-xs font-medium">
                          Partial
                        </span>
                      ) : (
                        <span className="text-gray-400 text-xs">Pending</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {repayments.length > 0 && (
          <>
            <h2 className="font-semibold text-gray-900 mb-3">
              Payment history
            </h2>
            <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
              {repayments.map((r) => (
                <div
                  key={r.id}
                  className="px-4 py-3 flex justify-between items-center text-sm"
                >
                  <div>
                    <p className="text-gray-900">{formatNaira(r.amount)}</p>
                    <p className="text-xs text-gray-500">
                      {formatDate(r.payment_date)} ·{" "}
                      {r.payment_method || "card"}
                      {r.reference && ` · ${r.reference}`}
                    </p>
                  </div>
                  <span
                    className={`text-xs font-medium ${
                      r.status === "successful"
                        ? "text-success"
                        : "text-warning"
                    }`}
                  >
                    {r.status}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl p-4 border border-gray-200">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
