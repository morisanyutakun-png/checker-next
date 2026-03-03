import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OMR Checker",
  description: "Optical Mark Recognition grading system",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-[var(--bg)]">
        {/* Global nav */}
        <nav className="sticky top-0 z-50 backdrop-blur-xl bg-[var(--bg)]/80 border-b border-[var(--border)]">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
            <a href="/" className="text-lg font-semibold tracking-tight text-[var(--text)]">
              OMR Checker
            </a>
            <div className="flex items-center gap-6 text-sm font-medium text-[var(--text-secondary)]">
              <a href="/" className="hover:text-[var(--text)] transition-colors">
                ホーム
              </a>
              <a href="/admin" className="hover:text-[var(--text)] transition-colors">
                管理
              </a>
              <a href="/scores" className="hover:text-[var(--text)] transition-colors">
                履歴
              </a>
            </div>
          </div>
        </nav>
        <main className="max-w-6xl mx-auto px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
