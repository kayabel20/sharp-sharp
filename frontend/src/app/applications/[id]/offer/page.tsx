"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import { applicationApi } from "@/lib/api";

interface Offer {
  id: string;
  approved_amount: number;
  tenure_days: number;
  interest_rate_monthly: number;
  total_repayment: number;
  installment_amount: number;
  repayment_frequency: string;
  risk_tier_name: string | null;
  first_repayment_date: string | null;
  expires_at: string;
}

const formatNaira = (amount: number) =>
  `₦${amount?.toLocaleString("en-NG", { maximumFractionDigits: 0 }) || "0"}`;

const formatDate = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-NG", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export default function OfferReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [offer, setOffer] = useState<Offer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    applicationApi
      .getOffer(id)
      .then((res) => setOffer(res.data))
      .catch((err) =>
        setError(err.response?.data?.detail || "No offer available")
      )
      .finally(() => setLoading(false));
  }, [id]);

  const handleAccept = async () => {
    setError("");
    setAccepting(true);
    try {
      const res = await applicationApi.acceptOffer(id);
      if (res.data.status === "disbursed") {
        router.push(`/loans/${res.data.loan_id}?welcome=1`);
      } else if (res.data.status === "expired") {
        setError("This offer has expired. Please apply again.");
      } else {
        setError(res.data.message || "Disbursement failed — please retry");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Could not accept offer");
    } finally {
      setAccepting(false);
    }
  };

  if (loading) {
    return (
      <AppShell requireAuth>
        <div className="max-w-lg mx-auto px-4 py-8 text-gray-400 text-sm">
          Loading offer…
        </div>
      </AppShell>
    );
  }

  if (error && !offer) {
    return (
      <AppShell requireAuth>
        <div className="max-w-lg mx-auto px-4 py-8">
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
          <Link
            href="/dashboard"
            className="mt-4 inline-block text-brand-500 hover:underline text-sm"
          >
            ← Back to dashboard
          </Link>
        </div>
      </AppShell>
    );
  }

  if (!offer) return null;

  const ratePct = (offer.interest_rate_monthly * 100).toFixed(2);
  const expired = new Date(offer.expires_at) < new Date();

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
          Your loan offer
        </h1>
        <p className="text-gray-500 mb-6 text-sm">
          {offer.risk_tier_name && (
            <>
              Risk tier: <span className="font-medium">{offer.risk_tier_name}</span>
              {" · "}
            </>
          )}
          Expires {formatDate(offer.expires_at)}
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        <div className="bg-gradient-to-br from-brand-500 to-brand-700 text-white rounded-2xl p-6 mb-4 shadow-lg">
          <p className="text-sm opacity-80 mb-1">You'll receive</p>
          <p className="text-4xl font-bold mb-4">
            {formatNaira(offer.approved_amount)}
          </p>
          <div className="border-t border-white/20 pt-4 grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="opacity-70 text-xs">Tenure</p>
              <p className="font-semibold">{offer.tenure_days} days</p>
            </div>
            <div>
              <p className="opacity-70 text-xs">Monthly rate</p>
              <p className="font-semibold">{ratePct}%</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-200 mb-4">
          <h3 className="font-semibold text-gray-900 mb-3">Repayment</h3>
          <div className="space-y-2 text-sm">
            <Row
              label={`${capitalize(offer.repayment_frequency)} payment`}
              value={formatNaira(offer.installment_amount)}
            />
            <Row
              label="First payment due"
              value={formatDate(offer.first_repayment_date)}
            />
            <Row
              label="Total repayment"
              value={formatNaira(offer.total_repayment)}
              bold
            />
            <Row
              label="Total interest"
              value={formatNaira(offer.total_repayment - offer.approved_amount)}
              muted
            />
          </div>
        </div>

        <label className="flex items-start gap-3 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            className="mt-1 w-4 h-4 accent-brand-500"
          />
          <span className="text-xs text-gray-600 leading-relaxed">
            I agree to the loan terms above. I authorise Sharp Sharp to disburse{" "}
            {formatNaira(offer.approved_amount)} and to debit{" "}
            {formatNaira(offer.installment_amount)} {offer.repayment_frequency}
            {" "}for repayment. APR and full T&Cs disclosed in the loan agreement.
          </span>
        </label>

        <button
          onClick={handleAccept}
          disabled={accepting || !agreed || expired}
          className="w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
        >
          {expired
            ? "Offer expired"
            : accepting
            ? "Disbursing…"
            : "Accept and disburse"}
        </button>
        <button
          onClick={() => router.push("/dashboard")}
          className="mt-3 w-full py-3 text-gray-600 hover:text-gray-900 transition"
        >
          Decline
        </button>
      </div>
    </AppShell>
  );
}

function Row({
  label,
  value,
  bold,
  muted,
}: {
  label: string;
  value: string;
  bold?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <span className={muted ? "text-gray-400" : "text-gray-600"}>{label}</span>
      <span
        className={`${bold ? "font-bold text-gray-900" : "text-gray-900"} ${
          muted ? "text-gray-400 font-normal" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
