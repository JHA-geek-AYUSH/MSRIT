"use client";

/**
 * Replaces the previous fake "Connected Apps" grid (Gmail/GitHub/Discord/Twitter
 * icons wired to a setTimeout + localStorage — no real OAuth, nothing actually
 * connected). Real connector management now lives at /integrations (Composio +
 * SAP/direct connectors). This page is just account identity + role, which
 * drives the role-based dashboard (finance_analyst / compliance_officer / cfo / auditor).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useUser, useClerk } from "@clerk/nextjs";
import { Header } from "@/components/layout/Header";
import { getProfile, updateProfile, type UserProfile } from "@/lib/compliance-api";

const ROLES = [
  { value: "finance_analyst", label: "Finance Analyst", desc: "Runs assessments, reviews penalty exposure" },
  { value: "compliance_officer", label: "Compliance Officer", desc: "Reviews critical findings, approves high-risk actions" },
  { value: "auditor", label: "Auditor", desc: "Reviews audit reports and approval history" },
  { value: "cfo", label: "CFO", desc: "Portfolio-level penalty exposure and critical findings" },
];

export default function ProfilePage() {
  const { user } = useUser();
  const { signOut } = useClerk();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile().then(setProfile).catch((e) => setError(e.message));
  }, []);

  async function handleRoleChange(role: string) {
    if (!profile || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateProfile({ role });
      setProfile(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const initials = user?.firstName && user?.lastName ? `${user.firstName[0]}${user.lastName[0]}` : user?.firstName?.[0] || "U";

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />
      <main className="max-w-2xl mx-auto px-6 py-12">
        <p className="font-body text-gold-500 text-sm tracking-widest uppercase mb-2">Account</p>
        <h1 className="font-display text-4xl text-brown-900 mb-8">Profile</h1>

        <div className="bg-stone-200/40 border border-brown-500/15 rounded-2xl p-6 flex items-center gap-5 mb-6">
          <div className="size-14 rounded-full bg-brown-900 flex items-center justify-center text-cream-50 text-lg font-display font-bold shrink-0">
            {initials}
          </div>
          <div>
            <p className="font-body font-medium text-brown-900">{user?.fullName || "User"}</p>
            <p className="font-body text-sm text-brown-500">{user?.primaryEmailAddress?.emailAddress}</p>
          </div>
        </div>

        {error && <div className="bg-error-500/10 border border-error-500/30 rounded-lg p-4 mb-6 font-body text-sm text-error-500">{error}</div>}

        <div className="bg-stone-200/40 border border-brown-500/15 rounded-2xl p-6 mb-6">
          <p className="font-display text-lg text-brown-900 mb-1">Role</p>
          <p className="font-body text-sm text-brown-500 mb-4">Determines which sections show up on your dashboard and whether you can approve high-risk actions.</p>
          <div className="space-y-2">
            {ROLES.map((r) => (
              <button
                key={r.value}
                onClick={() => handleRoleChange(r.value)}
                disabled={saving}
                className={`w-full text-left rounded-lg border px-4 py-3 transition-colors ${
                  profile?.role === r.value ? "border-gold-500 bg-gold-500/10" : "border-brown-500/15 hover:bg-cream-100/60"
                } disabled:opacity-50`}
              >
                <p className="font-body font-medium text-sm text-brown-900">{r.label}</p>
                <p className="font-body text-xs text-brown-500 mt-0.5">{r.desc}</p>
              </button>
            ))}
          </div>
        </div>

        <Link
          href="/integrations"
          className="block bg-stone-200/40 border border-brown-500/15 rounded-2xl p-6 mb-6 hover:border-gold-500/40 transition-colors"
        >
          <p className="font-display text-lg text-brown-900 mb-1">Integrations</p>
          <p className="font-body text-sm text-brown-500">Connect SAP, Outlook, Excel, SharePoint, and Slack via Composio →</p>
        </Link>

        <button
          onClick={() => signOut()}
          className="w-full py-3 rounded-xl border border-error-500/30 text-error-500 font-body text-sm hover:bg-error-500/5 transition-colors"
        >
          Sign Out
        </button>
      </main>
    </div>
  );
}
