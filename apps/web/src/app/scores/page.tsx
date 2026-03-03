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
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">採点履歴</h1>

      {scores.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-[var(--text-secondary)]">まだ採点履歴がありません。</p>
          <a href="/" className="btn btn-primary mt-4 inline-flex">
            採点を始める
          </a>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <table>
            <thead>
              <tr>
                <th>日時</th>
                <th>教科</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s) => (
                <tr key={s.id} className="hover:bg-[var(--border)]/30 transition-colors">
                  <td className="text-sm">
                    {s.timestamp
                      ? new Date(s.timestamp).toLocaleString("ja-JP")
                      : "—"}
                  </td>
                  <td>{s.subject_name || "—"}</td>
                  <td className="text-right">
                    <a href={`/scores/${s.id}`} className="btn btn-secondary text-xs py-1 px-3">
                      詳細
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
