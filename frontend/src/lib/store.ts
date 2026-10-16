/**
 * Zustand global state — auth + user profile.
 */
import { create } from "zustand";

interface User {
  id: string;
  phone_number: string;
  email: string | null;
  first_name: string;
  last_name: string;
  status: string | null;
  tier: string | null;
  persona: string | null;
  ladder_tier: number;
  total_loans_taken: number;
  kyc_status: string | null;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setUser: (user: User) => void;
  login: (token: string, refreshToken: string, user: User) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  setUser: (user) => set({ user, isAuthenticated: true }),
  login: (token, refreshToken, user) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("access_token", token);
      localStorage.setItem("refresh_token", refreshToken);
    }
    set({ user, isAuthenticated: true });
  },
  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
    set({ user: null, isAuthenticated: false });
  },
  setLoading: (loading) => set({ isLoading: loading }),
}));
