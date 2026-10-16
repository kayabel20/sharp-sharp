"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { userApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";

interface AppShellProps {
  children: React.ReactNode;
  requireAuth?: boolean;
  requireKyc?: boolean;
}

export default function AppShell({
  children,
  requireAuth = true,
  requireKyc = false,
}: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isAuthenticated, setUser, logout } = useAuthStore();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;

    if (!token && requireAuth) {
      router.replace(`/auth/login?next=${encodeURIComponent(pathname)}`);
      return;
    }

    if (token && !user) {
      userApi
        .getProfile()
        .then((res) => setUser(res.data))
        .catch(() => {
          logout();
          if (requireAuth) router.replace("/auth/login");
        })
        .finally(() => setChecking(false));
    } else {
      setChecking(false);
    }
  }, [pathname, requireAuth, router, setUser, logout, user]);

  useEffect(() => {
    if (!checking && requireKyc && user && user.kyc_status !== "fully_verified") {
      router.replace("/onboarding/kyc");
    }
  }, [checking, requireKyc, user, router]);

  if (requireAuth && checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400 text-sm">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link href="/dashboard" className="font-bold text-brand-600 text-lg">
            Sharp Sharp
          </Link>
          {isAuthenticated && (
            <nav className="flex items-center gap-5 text-sm">
              <Link
                href="/dashboard"
                className={
                  pathname === "/dashboard"
                    ? "text-brand-600 font-semibold"
                    : "text-gray-600 hover:text-gray-900"
                }
              >
                Dashboard
              </Link>
              <Link
                href="/apply"
                className={
                  pathname === "/apply"
                    ? "text-brand-600 font-semibold"
                    : "text-gray-600 hover:text-gray-900"
                }
              >
                Apply
              </Link>
              <Link
                href="/profile"
                className={
                  pathname === "/profile"
                    ? "text-brand-600 font-semibold"
                    : "text-gray-600 hover:text-gray-900"
                }
              >
                Profile
              </Link>
              <button
                onClick={() => {
                  logout();
                  router.push("/auth/login");
                }}
                className="text-gray-500 hover:text-danger"
              >
                Sign out
              </button>
            </nav>
          )}
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
