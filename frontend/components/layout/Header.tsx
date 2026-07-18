"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SignInButton, SignUpButton, UserButton, useUser } from "@clerk/nextjs";
import {
  Menu, X, ChevronDown,
  ShieldCheck, Clock, BarChart2,
  FileText, ArrowLeftRight, Building2, BookOpen,
  Bot, Calculator, BookMarked, Database,
  ClipboardList, Search, CheckSquare, LayoutDashboard,
  Plug,
} from "lucide-react";

const NAV_GROUPS = [
  {
    label: "Compliance",
    items: [
      { href: "/compliance", label: "New Assessment", desc: "Run ML + agent triage", icon: ShieldCheck },
      { href: "/compliance/invoices", label: "Invoices", desc: "Upload & detect duplicates", icon: FileText },
      { href: "/compliance/transactions", label: "Transactions", desc: "AML/CFT analysis", icon: ArrowLeftRight },
      { href: "/compliance/vendors", label: "Vendor KYC", desc: "Onboarding & PEP checks", icon: Building2 },
      { href: "/compliance/policies", label: "Policies", desc: "Document library", icon: BookOpen },
      { href: "/compliance/assessments", label: "History", desc: "Past pipeline results", icon: Clock },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/agent", label: "Agent Console", desc: "FinTriage AI chat", icon: Bot },
      { href: "/compliance/penalty-sim", label: "Penalty Simulator", desc: "Estimate regulatory fines", icon: Calculator },
      { href: "/compliance/rules", label: "Rule Catalogue", desc: "40 compliance rules", icon: BookMarked },
      { href: "/memory", label: "Knowledge Base", desc: "RAG Q&A", icon: Database },
    ],
  },
  {
    label: "Outputs",
    items: [
      { href: "/compliance/report", label: "Audit Report", desc: "Generated reports", icon: ClipboardList },
      { href: "/compliance/audit", label: "Audit Log", desc: "Full event history", icon: Search },
      { href: "/approvals", label: "Approvals", desc: "Pending action queue", icon: CheckSquare },
      { href: "/dashboard", label: "Dashboard", desc: "Role-based overview", icon: LayoutDashboard },
    ],
  },
];

const SINGLE_LINKS = [
  { href: "/integrations", label: "Integrations", icon: Plug },
];

function NavDropdown({ group, pathname }: { group: typeof NAV_GROUPS[0]; pathname: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isGroupActive = group.items.some(
    (i) => pathname === i.href || pathname?.startsWith(i.href + "/")
  );

  function handleMouseEnter() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(true);
  }

  function handleMouseLeave() {
    timeoutRef.current = setTimeout(() => setOpen(false), 120);
  }

  useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); }, []);

  return (
    <div ref={ref} className="relative" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-1 font-body text-sm px-3 py-2 rounded-lg transition-colors ${
          isGroupActive
            ? "text-brown-900 bg-gold-500/15 font-medium"
            : "text-brown-700 hover:text-brown-900 hover:bg-brown-900/5"
        }`}
      >
        {group.label}
        <ChevronDown size={13} className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute top-[calc(100%+4px)] left-0 w-60 rounded-xl bg-white border border-stone-200 shadow-xl shadow-brown-900/10 py-1.5 z-[200]"
          style={{ pointerEvents: "auto" }}
        >
          {group.items.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 mx-1 rounded-lg transition-colors ${
                  active
                    ? "bg-gold-500/12 text-brown-900"
                    : "hover:bg-stone-50 text-brown-700 hover:text-brown-900"
                }`}
              >
                <div className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 ${active ? "bg-gold-500/20" : "bg-stone-100"}`}>
                  <Icon size={14} className={active ? "text-gold-600" : "text-brown-500"} />
                </div>
                <div className="min-w-0">
                  <p className="font-body text-sm font-medium leading-tight">{item.label}</p>
                  <p className="font-body text-[11px] text-brown-400 leading-tight">{item.desc}</p>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Header() {
  const { isSignedIn } = useUser();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 w-full bg-cream-100/95 backdrop-blur-sm border-b border-stone-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16 gap-4">
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <span className="font-display text-xl font-bold text-brown-900 tracking-tight">
              GemmaFin<span className="text-gold-500"> OS</span>
            </span>
          </Link>

          {isSignedIn && (
            <nav className="hidden lg:flex items-center gap-0.5">
              {NAV_GROUPS.map((group) => (
                <NavDropdown key={group.label} group={group} pathname={pathname ?? ""} />
              ))}
              {SINGLE_LINKS.map((link) => {
                const active = pathname === link.href;
                const Icon = link.icon;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`flex items-center gap-1.5 font-body text-sm px-3 py-2 rounded-lg transition-colors ${
                      active
                        ? "text-brown-900 bg-gold-500/15 font-medium"
                        : "text-brown-700 hover:text-brown-900 hover:bg-brown-900/5"
                    }`}
                  >
                    <Icon size={14} />
                    {link.label}
                  </Link>
                );
              })}
            </nav>
          )}

          <div className="flex items-center gap-3 shrink-0">
            {isSignedIn ? (
              <>
                <button
                  className="lg:hidden p-2 text-brown-700"
                  onClick={() => setMobileOpen((v) => !v)}
                  aria-label="Toggle navigation"
                >
                  {mobileOpen ? <X size={20} /> : <Menu size={20} />}
                </button>
                <UserButton afterSignOutUrl="/" />
              </>
            ) : (
              <>
                <SignInButton>
                  <button className="font-body text-sm text-brown-700 hover:text-brown-900 px-3 py-2 transition-colors">
                    Sign In
                  </button>
                </SignInButton>
                <SignUpButton>
                  <button className="font-body text-sm bg-brown-900 hover:bg-brown-700 text-cream-50 px-4 py-2 rounded-lg border border-gold-500/40 transition-colors">
                    Get Started
                  </button>
                </SignUpButton>
              </>
            )}
          </div>
        </div>

        {isSignedIn && mobileOpen && (
          <nav className="lg:hidden pb-4 flex flex-col gap-0.5 border-t border-stone-200 pt-3">
            {NAV_GROUPS.flatMap((g) => g.items).concat(SINGLE_LINKS as any[]).map((link) => {
              const Icon = link.icon;
              const active = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center gap-2.5 font-body text-sm px-3 py-2.5 rounded-lg transition-colors ${
                    active
                      ? "bg-gold-500/15 text-brown-900 font-medium"
                      : "text-brown-700 hover:text-brown-900 hover:bg-brown-900/5"
                  }`}
                >
                  <Icon size={15} className={active ? "text-gold-600" : "text-brown-400"} />
                  {link.label}
                </Link>
              );
            })}
          </nav>
        )}
      </div>
    </header>
  );
}
