"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AppShell from "@/components/AppShell";
import { userApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

type Step = "bvn" | "nin" | "selfie" | "done";

const steps: { key: Step; title: string; subtitle: string }[] = [
  { key: "bvn", title: "BVN", subtitle: "Bank Verification Number" },
  { key: "nin", title: "NIN", subtitle: "National Identification Number" },
  { key: "selfie", title: "Selfie", subtitle: "Liveness check" },
];

export default function KycPage() {
  const router = useRouter();
  const { user, setUser } = useAuthStore();
  const [step, setStep] = useState<Step>("bvn");
  const [bvn, setBvn] = useState("");
  const [nin, setNin] = useState("");
  const [selfieFile, setSelfieFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const submitBvn = async () => {
    setError("");
    if (!/^\d{11}$/.test(bvn)) {
      setError("BVN must be 11 digits");
      return;
    }
    setLoading(true);
    try {
      await userApi.submitKYC({ bvn });
      setStep("nin");
    } catch (err: any) {
      setError(err.response?.data?.detail || "BVN submission failed");
    } finally {
      setLoading(false);
    }
  };

  const submitNin = async () => {
    setError("");
    if (!/^\d{11}$/.test(nin)) {
      setError("NIN must be 11 digits");
      return;
    }
    setLoading(true);
    try {
      await userApi.submitKYC({ nin });
      setStep("selfie");
    } catch (err: any) {
      setError(err.response?.data?.detail || "NIN submission failed");
    } finally {
      setLoading(false);
    }
  };

  const submitSelfie = async () => {
    setError("");
    if (!selfieFile) {
      setError("Please capture or upload a selfie");
      return;
    }
    setLoading(true);
    try {
      await userApi.uploadSelfie(selfieFile);
      const profile = await userApi.getProfile();
      setUser(profile.data);
      setStep("done");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Selfie upload failed");
    } finally {
      setLoading(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setSelfieFile(file);
    setPreviewUrl(file ? URL.createObjectURL(file) : null);
  };

  const stepIndex = steps.findIndex((s) => s.key === step);

  return (
    <AppShell requireAuth>
      <div className="max-w-lg mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Verify your identity
        </h1>
        <p className="text-gray-500 mb-6">
          We need this to comply with CBN rules and protect you.
        </p>

        {/* progress dots */}
        {step !== "done" && (
          <div className="flex items-center gap-2 mb-6">
            {steps.map((s, i) => (
              <div key={s.key} className="flex-1">
                <div
                  className={`h-1.5 rounded-full ${
                    i <= stepIndex ? "bg-brand-500" : "bg-gray-200"
                  }`}
                />
                <p
                  className={`text-xs mt-1 ${
                    i === stepIndex
                      ? "text-brand-600 font-semibold"
                      : "text-gray-400"
                  }`}
                >
                  {s.title}
                </p>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {step === "bvn" && (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h2 className="font-semibold text-gray-900 mb-1">
              Enter your BVN
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Dial *565*0# on your registered SIM if you don't know it.
            </p>
            <input
              type="text"
              value={bvn}
              onChange={(e) => setBvn(e.target.value.replace(/\D/g, ""))}
              placeholder="11-digit BVN"
              maxLength={11}
              inputMode="numeric"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none text-lg tracking-widest"
            />
            <button
              onClick={submitBvn}
              disabled={loading || bvn.length !== 11}
              className="mt-4 w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
            >
              {loading ? "Verifying…" : "Continue"}
            </button>
          </div>
        )}

        {step === "nin" && (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h2 className="font-semibold text-gray-900 mb-1">
              Enter your NIN
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Find this on your National ID slip or in the NIMC app.
            </p>
            <input
              type="text"
              value={nin}
              onChange={(e) => setNin(e.target.value.replace(/\D/g, ""))}
              placeholder="11-digit NIN"
              maxLength={11}
              inputMode="numeric"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent outline-none text-lg tracking-widest"
            />
            <div className="flex gap-3 mt-4">
              <button
                onClick={() => setStep("bvn")}
                className="flex-1 py-3 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition"
              >
                Back
              </button>
              <button
                onClick={submitNin}
                disabled={loading || nin.length !== 11}
                className="flex-1 py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
              >
                {loading ? "Verifying…" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {step === "selfie" && (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h2 className="font-semibold text-gray-900 mb-1">Take a selfie</h2>
            <p className="text-sm text-gray-500 mb-4">
              Make sure your face is clearly visible. We'll match against your BVN photo.
            </p>

            <div className="aspect-square w-full max-w-xs mx-auto rounded-xl border-2 border-dashed border-gray-300 overflow-hidden flex items-center justify-center bg-gray-50 mb-4">
              {previewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={previewUrl}
                  alt="Selfie preview"
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="text-gray-400 text-sm text-center px-4">
                  No image yet
                </div>
              )}
            </div>

            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="user"
              onChange={onFileChange}
              className="hidden"
            />
            <button
              onClick={() => fileRef.current?.click()}
              className="w-full py-3 border border-brand-500 text-brand-600 font-semibold rounded-lg hover:bg-brand-50 transition mb-3"
            >
              {selfieFile ? "Retake" : "Open camera / upload"}
            </button>

            <div className="flex gap-3">
              <button
                onClick={() => setStep("nin")}
                className="flex-1 py-3 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition"
              >
                Back
              </button>
              <button
                onClick={submitSelfie}
                disabled={loading || !selfieFile}
                className="flex-1 py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 disabled:opacity-50 transition"
              >
                {loading ? "Uploading…" : "Submit"}
              </button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 text-center">
            <div className="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-4">
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
            <h2 className="font-semibold text-gray-900 text-lg mb-2">
              Identity verified
            </h2>
            <p className="text-sm text-gray-500 mb-6">
              {user?.kyc_status === "fully_verified"
                ? "You're fully verified. You can now apply for a loan."
                : "We've recorded your details. You can apply now — final checks run during decisioning."}
            </p>
            <button
              onClick={() => router.push("/apply")}
              className="w-full py-3 bg-brand-500 text-white font-semibold rounded-lg hover:bg-brand-600 transition"
            >
              Apply for a loan
            </button>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-3 w-full py-3 text-gray-600 hover:text-gray-900 transition"
            >
              Go to dashboard
            </button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
