"use client";

import { useEffect, useState } from "react";
import { getScores, type ScoreEntry } from "@/lib/api";

export default function ScoresPage() {
  const [scores, setScores] = useState<ScoreEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getScores()
      .then(setScores)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="flex items-center justify-center py-24">
        <div className="spinner" />
      </div>
    );

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">採点履歴</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            {scores.length} 件の採点結果
          </p>
        </div>
        <a href="/" className="btn btn-primary text-sm">
          新しい採点
        </a>
      </div>

      {scores.length === 0 ? (
        <div className="card empty-state">
          <div className="empty-state__icon">📊</div>
          <p className="empty-state__title">まだ採点履歴がありません</p>
          <p className="empty-state__description">
            マークシートPDFをアップロードして採点を始めましょう。
          </p>
          <a href="/" className="btn btn-primary mt-4 inline-flex">
            採点を始める
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          {scores.map((s) => (
            <a
              key={s.id}
              href={`/scores/${s.id}`}
              className="card group flex items-center gap-4 hover:border-[var(--accent)] cursor-pointer transition-all"
            >
              <div className="w-10 h-10 rounded-xl bg-[var(--accent-light)] flex items-center justify-center">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">
                  {s.subject_name || "採点結果"}
                </p>
                <p className="text-xs text-[var(--text-tertiary)]">
                  {s.timestamp
                    ? new Date(s.timestamp).toLocaleString("ja-JP", {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—"}
                </p>
              </div>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="2" className="group-hover:translate-x-1 transition-transform">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
