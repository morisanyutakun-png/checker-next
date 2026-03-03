"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { getConfig, generatePdf, type SubjectData } from "@/lib/api";

export default function SheetPage() {
  const params = useParams();
  const idx = Number(params.idx);
  const [subject, setSubject] = useState<SubjectData | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [digits, setDigits] = useState(Array(10).fill(""));
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        if (cfg.subjects && idx < cfg.subjects.length) {
          setSubject(cfg.subjects[idx]);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [idx]);

  function handleDigitChange(pos: number, val: string) {
    const next = [...digits];
    next[pos] = val.slice(-1);
    setDigits(next);
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setGenerating(true);
    setError(null);
    try {
      const exam_number = digits.join("").replace(/\s/g, "");
      const res = await generatePdf(idx, { name, exam_number });
      if (res.success && res.pdf_url) {
        setPdfUrl(res.pdf_url);
      } else {
        setError(res.logs || res.error || "PDF生成に失敗しました");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  }

  function openPdfInNewTab() {
    if (pdfUrl) window.open(pdfUrl, "_blank");
  }

  if (loading)
    return (
      <div className="flex items-center justify-center py-24">
        <div className="spinner" />
      </div>
    );

  if (!subject)
    return (
      <div className="text-center py-20">
        <h1 className="text-xl font-semibold mb-2">教科が見つかりません</h1>
        <a href="/admin">管理画面で教科を追加</a>
      </div>
    );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{subject.name}</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-0.5">マークシート プレビュー</p>
        </div>
        <a href="/" className="btn btn-secondary text-sm">
          ← 戻る
        </a>
      </div>

      {/* Form */}
      <form onSubmit={handleGenerate} className="card space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">氏名</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="氏名を入力"
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">受験番号</label>
            <div className="flex gap-1.5">
              {digits.map((d, i) => (
                <input
                  key={i}
                  type="text"
                  maxLength={1}
                  inputMode="numeric"
                  value={d}
                  onChange={(e) => handleDigitChange(i, e.target.value)}
                  className="w-8 h-10 text-center text-sm"
                />
              ))}
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button type="submit" disabled={generating} className="btn btn-primary">
            {generating ? "生成中..." : "PDF プレビュー"}
          </button>
          {pdfUrl && (
            <button type="button" onClick={openPdfInNewTab} className="btn btn-secondary">
              新しいタブで開く
            </button>
          )}
        </div>
      </form>

      {/* Error */}
      {error && (
        <div className="card border-[var(--danger)]/30 bg-[var(--danger)]/5">
          <h3 className="font-semibold text-[var(--danger)] mb-2">エラー</h3>
          <pre className="text-xs whitespace-pre-wrap overflow-auto max-h-80 text-[var(--text-secondary)]">{error}</pre>
        </div>
      )}

      {/* PDF Preview */}
      {pdfUrl && (
        <div className="relative">
          <iframe
            ref={iframeRef}
            src={pdfUrl}
            className="w-full rounded-xl border border-[var(--border)]"
            style={{ height: "80vh" }}
          />
        </div>
      )}
    </div>
  );
}
