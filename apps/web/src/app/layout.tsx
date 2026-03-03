import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OMR Checker",
  description: "マークシート自動採点システム — Optical Mark Recognition",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-screen bg-[var(--bg)]">
        {/* Navigation */}
        <nav className="sticky top-0 z-50 glass border-b border-[var(--border)]">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
            <a
              href="/"
              className="flex items-center gap-2.5 text-[var(--text)] hover:text-[var(--text)] group"
            >
              <div className="w-8 h-8 rounded-lg bg-[var(--gradient-brand)] flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="white"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M9 11l3 3L22 4" />
                  <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                </svg>
              </div>
              <span className="text-[0.9375rem] font-semibold tracking-tight">
                OMR Checker
              </span>
            </a>
            <div className="flex items-center gap-0.5">
              <a
                href="/"
                className="px-3.5 py-1.5 text-[0.8125rem] font-medium text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--accent-light)] rounded-lg transition-all"
              >
                採点
              </a>
              <a
                href="/admin"
                className="px-3.5 py-1.5 text-[0.8125rem] font-medium text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--accent-light)] rounded-lg transition-all"
              >
                管理
              </a>
              <a
                href="/scores"
                className="px-3.5 py-1.5 text-[0.8125rem] font-medium text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--accent-light)] rounded-lg transition-all"
              >
                履歴
              </a>
            </div>
          </div>
        </nav>
        <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
        {/* Minimal footer */}
        <footer className="border-t border-[var(--border)] mt-16">
          <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between text-xs text-[var(--text-tertiary)]">
            <span className="font-medium">OMR Checker v2.0</span>
            <span>Next.js + FastAPI + Neon</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
