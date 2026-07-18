'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Header } from '@/components/layout/Header';
import { cn } from '@/lib/utils';
import {
  ShieldCheck, Clock, BarChart2,
  FileText, ArrowLeftRight, Building2, BookOpen,
  Calculator, BookMarked,
  ClipboardList, Search,
} from 'lucide-react';

const SIDEBAR_SECTIONS = [
  {
    label: 'Compliance Triage',
    items: [
      { href: '/compliance', label: 'New Assessment', icon: ShieldCheck, desc: 'Run compliance check' },
      { href: '/compliance/history', label: 'Triage History', icon: Clock, desc: 'Past triage runs' },
      { href: '/compliance/assessments', label: 'Full Assessments', icon: BarChart2, desc: 'Pipeline results' },
    ],
  },
  {
    label: 'FinOps Workflows',
    items: [
      { href: '/compliance/invoices', label: 'Invoices', icon: FileText, desc: 'Upload & detect duplicates' },
      { href: '/compliance/transactions', label: 'Transactions', icon: ArrowLeftRight, desc: 'AML/CFT analysis' },
      { href: '/compliance/vendors', label: 'Vendor KYC', icon: Building2, desc: 'Onboarding checks' },
      { href: '/compliance/policies', label: 'Policies', icon: BookOpen, desc: 'Document library' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { href: '/compliance/penalty-sim', label: 'Penalty Simulator', icon: Calculator, desc: 'Estimate fines' },
      { href: '/compliance/rules', label: 'Rule Catalogue', icon: BookMarked, desc: '40 compliance rules' },
    ],
  },
  {
    label: 'Outputs',
    items: [
      { href: '/compliance/report', label: 'Audit Report', icon: ClipboardList, desc: 'Generated reports' },
      { href: '/compliance/audit', label: 'Audit Log', icon: Search, desc: 'Full event history' },
    ],
  },
];

const PATH_TITLES: Record<string, string> = {
  '/compliance': 'New Assessment',
  '/compliance/history': 'Triage History',
  '/compliance/assessments': 'Full Assessments',
  '/compliance/invoices': 'Invoices',
  '/compliance/transactions': 'Transactions',
  '/compliance/vendors': 'Vendor KYC',
  '/compliance/policies': 'Policies',
  '/compliance/penalty-sim': 'Penalty Simulator',
  '/compliance/rules': 'Rule Catalogue',
  '/compliance/report': 'Audit Report',
  '/compliance/audit': 'Audit Log',
};

export default function ComplianceLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const currentTitle = PATH_TITLES[pathname ?? ''] ?? 'Compliance';

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />

      {/* Breadcrumb */}
      <div className="border-b border-stone-200 bg-cream-100/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center h-9 gap-2">
          <Link href="/compliance" className="font-body text-xs text-brown-400 hover:text-brown-700 transition-colors">
            Compliance
          </Link>
          <span className="text-stone-300 text-xs">/</span>
          <span className="font-body text-xs text-brown-900 font-medium">{currentTitle}</span>
        </div>
      </div>

      <div className="flex max-w-7xl mx-auto">
        {/* Desktop Sidebar */}
        <aside className="hidden lg:flex flex-col w-52 shrink-0 border-r border-stone-200 min-h-[calc(100vh-7rem)] bg-cream-100/50 py-5 px-3">
          <nav className="space-y-6">
            {SIDEBAR_SECTIONS.map((section) => (
              <div key={section.label}>
                <p className="font-body text-[10px] font-bold uppercase tracking-widest text-brown-300 mb-1.5 px-2">
                  {section.label}
                </p>
                <ul className="space-y-0.5">
                  {section.items.map((item) => {
                    const isActive = pathname === item.href;
                    const Icon = item.icon;
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          className={cn(
                            'group flex items-center gap-2.5 px-2.5 py-2 rounded-lg transition-all duration-100',
                            isActive
                              ? 'bg-gold-500/12 text-brown-900'
                              : 'text-brown-600 hover:bg-brown-900/5 hover:text-brown-900',
                          )}
                        >
                          <div className={cn(
                            'w-6 h-6 rounded-md flex items-center justify-center shrink-0 transition-colors',
                            isActive ? 'bg-gold-500/20' : 'bg-stone-100 group-hover:bg-stone-200',
                          )}>
                            <Icon size={13} className={isActive ? 'text-gold-600' : 'text-brown-400'} />
                          </div>
                          <div className="min-w-0">
                            <p className={cn('font-body text-xs truncate leading-tight', isActive ? 'font-semibold' : 'font-medium')}>{item.label}</p>
                            <p className={cn('font-body text-[10px] truncate leading-tight', isActive ? 'text-gold-600' : 'text-brown-400')}>{item.desc}</p>
                          </div>
                          {isActive && <div className="ml-auto w-1 h-4 bg-gold-500 rounded-full shrink-0" />}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </aside>

        {/* Mobile horizontal tabs */}
        <div className="lg:hidden w-full overflow-x-auto border-b border-stone-200 bg-cream-100/80 shrink-0">
          <div className="flex gap-1 px-3 py-2">
            {SIDEBAR_SECTIONS.flatMap((s) => s.items).map((item) => {
              const isActive = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition-colors font-body font-medium',
                    isActive
                      ? 'bg-gold-500/15 text-brown-900 border border-gold-500/25'
                      : 'text-brown-600 hover:bg-brown-900/5 hover:text-brown-900',
                  )}
                >
                  <Icon size={12} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>

        {/* Main content — full width on mobile, flex-1 on desktop */}
        <main className="flex-1 min-w-0 py-6 px-4 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
