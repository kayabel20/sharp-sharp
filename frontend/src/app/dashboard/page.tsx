"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { userApi, loanApi, applicationApi } from "@/lib/api";

interface LoanSummary {
  id: string;
  principal_amount: number;
  total_outstanding: number;
  status: string;
  days_past_due: number;
}

interface LadderInfo {
  current_tier: number;
  total_loans: number;
  on_time_repayments: number;
  next_tier: number | null;
}

export default function DashboardPage() {
  const [profile, setProfile] = useState<any>(null);
  const [activeLoan, setActiveLoan] = useState<LoanSummary | null>(null);
  const [ladder, setLadder] = useState<LadderInfo | null>(null);
  const [applications, setApplications] = useState<any[]>([]);

  useEffect(() => {
    Promise.all([
      userApi.getProfile(),
      loanApi.getActive(),
      userApi.getLadderInfo(),
      applicationApi.list(),
    ]).then(([profileRes, loanRes, ladderRes, appRes]) => {
      setProfile(profileRes.data);
      setActiveLoan(loanRes.data);
      setLadder(ladderRes.data);
      setApplications(appRes.data);
    });
  }, []);

  const formatNaira = (amount: number) =>
    `\u20A6${amount?.toLocaleString("en-NG") || "0"}`;

  return (
    <AppShell requireAuth>
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome back, {profile?.first_name || "..."}
          </h1>
          <p className="text-gray-500">
            Tier {profile?.tier?.replace("tier_", "")} &middot; Ladder Level{" "}
            {ladder?.current_tier || 1}
          </p>
        </div>
        <Link
          href="/apply"
          className="px-6 py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 transition"
        >
          Apply for Loan
        </Link>
      </div>

      {/* Active Loan Card */}
      {activeLoan ? (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200 mb-6">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm text-gray-500 mb-1">Active Loan</p>
              <p className="text-3xl font-bold text-gray-900">
                {formatNaira(activeLoan.total_outstanding)}
              </p>
              <p className="text-sm text-gray-500 mt-1">outstanding</p>
            </div>
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${
                activeLoan.days_past_due > 0
                  ? "bg-red-100 text-red-700"
                  : "bg-green-100 text-green-700"
              }`}
            >
              {activeLoan.days_past_due > 0
                ? `${activeLoan.days_past_due} days overdue`
                : "On track"}
            </span>
          </div>
          <Link
            href={`/loans/${activeLoan.id}`}
            className="mt-4 inline-block text-brand-500 hover:underline text-sm"
          >
            View Details &rarr;
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200 mb-6 text-center">
          <p className="text-gray-500">No active loan</p>
          <Link
            href="/apply"
            className="mt-2 inline-block text-brand-500 hover:underline"
          >
            Apply now
          </Link>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200 text-center">
          <p className="text-2xl font-bold text-brand-500">
            {ladder?.current_tier || 1}
          </p>
          <p className="text-sm text-gray-500">Ladder Tier</p>
        </div>
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200 text-center">
          <p className="text-2xl font-bold text-gray-900">
            {ladder?.total_loans || 0}
          </p>
          <p className="text-sm text-gray-500">Total Loans</p>
        </div>
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200 text-center">
          <p className="text-2xl font-bold text-success">
            {ladder?.on_time_repayments || 0}
          </p>
          <p className="text-sm text-gray-500">On-Time Repayments</p>
        </div>
      </div>

      {/* Recent Applications */}
      {applications.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <div className="p-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">Recent Applications</h2>
          </div>
          {applications.slice(0, 5).map((app: any) => (
            <Link
              key={app.id}
              href={`/applications/${app.id}`}
              className="p-4 border-b border-gray-50 last:border-0 flex justify-between items-center hover:bg-gray-50 transition"
            >
              <div>
                <p className="font-medium text-gray-900">
                  {formatNaira(app.requested_amount)}
                </p>
                <p className="text-sm text-gray-500">
                  {app.requested_tenure_days} days
                </p>
              </div>
              <span
                className={`px-3 py-1 rounded-full text-xs font-medium ${
                  app.status === "offer_generated"
                    ? "bg-green-100 text-green-700"
                    : app.status === "rejected"
                    ? "bg-red-100 text-red-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {app.status.replace(/_/g, " ")}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
    </AppShell>
  );
}
