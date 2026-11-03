import type { ReactNode } from "react";
import { Link, NavLink } from "react-router";

import { SettingsProvider } from "../lib/settings";
import { HealthBanner } from "./HealthBanner";

const NAV_LINK = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-2 py-1 text-sm ${isActive ? "bg-slate-100 font-medium dark:bg-slate-800" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`;

export function Layout({ children }: { children: ReactNode }) {
  return (
    <SettingsProvider>
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-4">
            <Link to="/" className="font-semibold tracking-tight">
              Vestigo Media Forensics
            </Link>
            <nav aria-label="Main" className="flex items-center gap-1">
              <NavLink to="/" end className={NAV_LINK}>
                Library
              </NavLink>
              <NavLink
                to="/upload"
                className={({ isActive }) =>
                  `rounded-md px-3 py-1 text-sm font-medium ${
                    isActive
                      ? "bg-slate-700 text-white dark:bg-slate-300 dark:text-slate-900"
                      : "bg-slate-900 text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
                  }`
                }
              >
                Upload
              </NavLink>
              <NavLink to="/settings" className={NAV_LINK}>
                Settings
              </NavLink>
            </nav>
          </div>
          <span className="text-xs text-slate-500 dark:text-slate-400">Local analysis · evidence, not verdicts</span>
        </div>
      </header>
      <HealthBanner />
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
    </SettingsProvider>
  );
}
