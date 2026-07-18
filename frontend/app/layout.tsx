import './globals.css';
import type { Metadata } from 'next';
import { ClerkProvider } from '@clerk/nextjs';
import { Toaster } from '@/components/ui/toaster';
import ErrorBoundary from '@/components/ErrorBoundary';
import { AppShell } from '@/components/layout/AppShell';

export const metadata: Metadata = {
  title: 'GemmaFin OS — Financial Compliance & Risk Triage',
  description: 'Gemma-powered compliance and risk-triage platform: analyses transactions, invoices, and onboarding documents to detect anomalies, assess risk, and generate audit-ready reports.',
  keywords: ['financial compliance', 'Gemma', 'AI', 'risk triage', 'AML', 'KYC', 'anomaly detection', 'SME compliance'],
  authors: [{ name: 'GemmaFin OS Team' }],
  creator: 'GemmaFin OS',
  metadataBase: new URL('https://gemmafin.os'),
  openGraph: {
    title: 'GemmaFin OS — Financial Compliance & Risk Triage',
    description: 'Gemma-powered anomaly detection, risk scoring, and audit-ready compliance reporting for finance teams, auditors, and CFOs.',
    type: 'website',
    locale: 'en_IN',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en" suppressHydrationWarning>
        <body className="min-h-screen bg-cream-50 text-brown-900 font-body antialiased" suppressHydrationWarning>
          <ErrorBoundary>
            <AppShell>
              <main className="flex-1">{children}</main>
            </AppShell>
            <Toaster />
          </ErrorBoundary>
        </body>
      </html>
    </ClerkProvider>
  );
}
