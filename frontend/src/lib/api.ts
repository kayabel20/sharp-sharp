/**
 * API client for the Sharp Sharp Lending Platform backend.
 */
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle 401 → refresh token or redirect to login
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      window.location.href = "/auth/login";
    }
    return Promise.reject(error);
  }
);

// ── Auth ──
export const authApi = {
  signup: (data: {
    phone_number: string;
    email?: string;
    first_name: string;
    last_name: string;
    password: string;
  }) => api.post("/auth/signup", data),

  login: (data: { phone_number: string; password: string }) =>
    api.post("/auth/login", data),

  refresh: (refresh_token: string) =>
    api.post("/auth/refresh", { refresh_token }),
};

// ── Users ──
export const userApi = {
  getProfile: () => api.get("/users/me"),
  submitKYC: (data: { bvn?: string; nin?: string }) =>
    api.post("/users/kyc/submit", data),
  uploadSelfie: (file: File) => {
    const fd = new FormData();
    fd.append("selfie", file);
    return api.post("/users/kyc/selfie", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  updateEmployment: (data: Record<string, unknown>) =>
    api.put("/users/employment", data),
  getLadderInfo: () => api.get("/users/ladder"),
};

// ── Bank linking (Mono / Okra) ──
export const bankApi = {
  // Frontend config: which providers are enabled, public key for Mono widget.
  getConfig: () =>
    api.get<{
      mono_public_key: string | null;
      mono_configured: boolean;
      okra_configured: boolean;
      statement_period: string;
    }>("/users/bank/config"),
  // Server-side exchange of Mono Connect `code` for an account_id.
  linkAccount: (data: { provider: "mono" | "okra"; public_token: string }) =>
    api.post("/users/bank/link", data),
  listLinked: () => api.get("/users/bank/accounts"),
  unlink: (provider: "mono" | "okra") =>
    api.delete(`/users/bank/${provider}`),
};

// ── Applications ──
export const applicationApi = {
  submit: (data: {
    requested_amount: number;
    requested_tenure_days: number;
    loan_purpose?: string;
    disbursement_account_number: string;
    disbursement_bank_code: string;
  }) => api.post("/applications/", data),

  list: () => api.get("/applications/"),
  get: (id: string) => api.get(`/applications/${id}`),
  getOffer: (id: string) => api.get(`/applications/${id}/offer`),
  acceptOffer: (id: string) => api.post(`/applications/${id}/accept`),
};

// ── Loans ──
export const loanApi = {
  list: () => api.get("/loans/"),
  getActive: () => api.get("/loans/active"),
  get: (id: string) => api.get(`/loans/${id}`),
  getSchedule: (id: string) => api.get(`/loans/${id}/schedule`),
  getRepayments: (id: string) => api.get(`/loans/${id}/repayments`),
  initiateRepayment: (id: string, data: { amount: number }) =>
    api.post(`/loans/${id}/repay`, data),
};

// ── Admin ──
export const adminApi = {
  getPortfolio: () => api.get("/admin/portfolio"),
  getReviewQueue: () => api.get("/admin/review-queue"),
  reviewApplication: (id: string, decision: { decision: string; reason?: string }) =>
    api.post(`/admin/review/${id}`, decision),
  getRiskTiers: () => api.get("/admin/risk-tiers"),
};

export default api;
