"use client";

import { useEffect, useState } from "react";
import { adminApi } from "@/lib/api";

interface PortfolioStats {
  total_applications: number;
  approved_count: number;
  rejected_count: number;
  pending_review_count: number;
  total_disbursed_amount: number;
  total_outstanding: number;
  active_loans: number;
  delinquent_loans: number;
  default_rate: number;
  average_ml_score: number | null;
}

interface ReviewItem {
  id: string;
  user_name: string;
  phone: string;
  requested_amount: number;
  ml_score: number | null;
  fraud_score: number | null;
  income_estimate: number | null;
  status: string;
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [queue, setQueue] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([adminApi.getPortfolio(), adminApi.getReviewQueue()]).then(
      ([statsRes, queueRes]) => {
        setStats(statsRes.data);
        setQueue(queueRes.data);
        setLoading(false);
      }
    );
  }, []);

  const formatNaira = (n: number) => `\u20A6${n?.toLocaleString("en-NG") || "0"}`;

  const handleReview = async (id: string, decision: string) => {
    await adminApi.reviewApplication(id, { decision });
    setQueue(queue.filter((q) => q.id !== id));
  };

  if (loading) return <div className="p-8 text-center">Loading...</div>;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Admin Dashboard</h1>

      {/* Portfolio Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard label="Total Applications" value={stats.total_applications} />
          <StatCard label="Approved" value={stats.approved_count} color="green" />
          <StatCard label="Rejected" value={stats.rejected_count} color="red" />
          <StatCard label="Pending Review" value={stats.pending_review_count} color="yellow" />
          <StatCard label="Active Loans" value={stats.active_loans} />
          <StatCard label="Delinquent" value={stats.delinquent_loans} color="red" />
          <StatCard label="Total Disbursed" value={formatNaira(stats.total_disbursed_amount)} />
          <StatCard label="Default Rate" value={`${(stats.default_rate * 100).toFixed(1)}%`} />
        </div>
      )}

      {/* Review Queue */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="p-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">
            Manual Review Queue ({queue.length})
          </h2>
        </div>

        {queue.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No applications pending review
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                  <th className="p-3">Applicant</th>
                  <th className="p-3">Amount</th>
                  <th className="p-3">ML Score</th>
                  <th className="p-3">Fraud</th>
                  <th className="p-3">Income</th>
                  <th className="p-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((item) => (
                  <tr key={item.id} className="border-b border-gray-50">
                    <td className="p-3">
                      <div className="font-medium text-gray-900">{item.user_name}</div>
                      <div className="text-xs text-gray-500">{item.phone}</div>
                    </td>
                    <td className="p-3">{formatNaira(item.requested_amount)}</td>
                    <td className="p-3">
                      <span className={`font-medium ${(item.ml_score || 0) >= 500 ? "text-green-600" : "text-red-600"}`}>
                        {item.ml_score?.toFixed(0) || "N/A"}
                      </span>
                    </td>
                    <td className="p-3">{item.fraud_score?.toFixed(0) || "N/A"}</td>
                    <td className="p-3">{item.income_estimate ? formatNaira(item.income_estimate) : "N/A"}</td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleReview(item.id, "approve")}
                          className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm hover:bg-green-200"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleReview(item.id, "reject")}
                          className="px-3 py-1 bg-red-100 text-red-700 rounded text-sm hover:bg-red-200"
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  const colorClasses: Record<string, string> = {
    green: "text-green-600",
    red: "text-red-600",
    yellow: "text-yellow-600",
  };

  return (
    <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${colorClasses[color || ""] || "text-gray-900"}`}>
        {value}
      </p>
    </div>
  );
}
