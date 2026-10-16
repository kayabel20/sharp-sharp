"use client";

import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-brand-500 to-brand-800 text-white">
      <div className="text-center max-w-2xl px-6">
        <h1 className="text-5xl font-bold mb-4">Sharp Sharp</h1>
        <p className="text-xl mb-2 opacity-90">Instant Loans. Smart Rates.</p>
        <p className="text-lg mb-8 opacity-75">
          Get up to &#8358;1,000,000 in minutes with our AI-powered lending platform.
          Fair rates based on your unique profile.
        </p>

        <div className="flex gap-4 justify-center">
          <Link
            href="/auth/login"
            className="px-8 py-3 bg-white text-brand-600 font-semibold rounded-lg hover:bg-gray-100 transition"
          >
            Log In
          </Link>
          <Link
            href="/auth/signup"
            className="px-8 py-3 bg-brand-400 text-white font-semibold rounded-lg border border-white/30 hover:bg-brand-300 transition"
          >
            Get Started
          </Link>
        </div>

        <div className="mt-16 grid grid-cols-3 gap-8 text-center">
          <div>
            <div className="text-3xl font-bold">5 min</div>
            <div className="text-sm opacity-75">Application to Offer</div>
          </div>
          <div>
            <div className="text-3xl font-bold">3%</div>
            <div className="text-sm opacity-75">Starting Monthly Rate</div>
          </div>
          <div>
            <div className="text-3xl font-bold">7 Tiers</div>
            <div className="text-sm opacity-75">Loyalty Ladder</div>
          </div>
        </div>
      </div>
    </div>
  );
}
