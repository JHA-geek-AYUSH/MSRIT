"use client";

/**
 * Was a second, competing navigation shell (fixed-width sidebar, "GemmaFinOS" branding,
 * emoji icons, generic shadcn dark theme) wrapping every non-landing page in
 * app/layout.tsx — stacked on top of each page's own <Header/>. That's what was
 * causing the duplicate nav bars, the layout shift, and the leftover "GemmaFinOS"
 * branding you're seeing regardless of what individual pages had been fixed to.
 *
 * Every app page already renders <Header/> (components/layout/Header.tsx) itself,
 * with the real GemmaFin OS nav, theme, and auth state. AppShell now only decides
 * page background/base layout — it renders no navigation of its own.
 */

export function AppShell({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-cream-50">{children}</div>;
}
