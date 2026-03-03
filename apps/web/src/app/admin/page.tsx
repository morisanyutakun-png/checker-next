"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getConfig,
  saveConfig,
  type ConfigData,
  type SubjectData,
} from "@/lib/api";

export default function AdminPage() {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setConfig(cfg);
        if (cfg.subjects.length > 0) setCurrentIdx(0);
      })
      .catch(console.error);
  }, []);

  const showFlash = useCallback((msg: string) => {
    setFlash(msg);
    setTimeout(() => setFlash(null), 3000);
  }, []);

  if (!config)
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );

  const subjects = config.subjects || [];
  const current = subjects[currentIdx] || null;

  function updateSubject(idx: number, patch: Partial<SubjectData>) {
    if (!config) return;
    const next = { ...config };
    next.subjects = [...next.subjects];
    next.subjects[idx] = { ...next.subjects[idx], ...patch };
    setConfig(next);
  }

  function addSubject() {
    if (!config) return;
    const name = prompt("教科名を入力してください", `Subject ${subjects.length + 1}`);
    if (name === null) return;
    const next = { ...config };
    next.subjects = [
      ...next.subjects,
      { name: name.trim() || `Subject ${subjects.length + 1}`, questions: [], sheet_template: "default" },
    ];
    setConfig(next);
    setCurrentIdx(next.subjects.length - 1);
  }

  function removeSubject() {
    if (!config || !current) return;
    if (!confirm(`「${current.name}」を削除しますか？`)) return;
    const next = { ...config };
    next.subjects = next.subjects.filter((_, i) => i !== currentIdx);
    setConfig(next);
    setCurrentIdx(Math.max(0, currentIdx - 1));
  }

  function addQuestion() {
    if (!config || !current) return;
    const qs = [...(current.questions || [])];
    qs.push({ id: qs.length + 1, label: `Q${qs.length + 1}`, choices: [], answer: null });
    updateSubject(currentIdx, { questions: qs });
  }

  function bulkGenerate(count: number, choicesPer: number) {
    if (!config || !current) return;
    const qs: Record<string, unknown>[] = [];
    for (let i = 0; i < count; i++) {
      qs.push({
        id: i + 1,
        label: `Q${i + 1}`,
        choices: [],
        answer: null,
        num_choices: choicesPer > 0 ? choicesPer : undefined,
      });
    }
    updateSubject(currentIdx, { questions: qs });
  }

  async function handleSave() {
    if (!config) return;
    setSaving(true);
    try {
      const saved = await saveConfig(config);
      setConfig(saved);
      showFlash("設定を保存しました");
    } catch (err: unknown) {
      showFlash("保存に失敗しました: " + (err instanceof Error ? err.message : err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">管理設定</h1>
        <div className="flex gap-2">
          <a href={current ? `/sheet/${currentIdx}` : "#"} className="btn btn-secondary text-sm">
            プレビュー
          </a>
          <button onClick={handleSave} disabled={saving} className="btn btn-primary text-sm">
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>

      {flash && (
        <div className="bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20 rounded-xl px-4 py-2.5 text-sm font-medium">
          {flash}
        </div>
      )}

      {/* Threshold */}
      <div className="card">
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
          閾値 (threshold)
        </label>
        <input
          type="number"
          step="0.01"
          min="0"
          max="1"
          value={config.threshold}
          onChange={(e) => setConfig({ ...config, threshold: parseFloat(e.target.value) || 0.35 })}
          className="w-48"
        />
      </div>

      {/* Subject selector */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <select
            value={currentIdx}
            onChange={(e) => setCurrentIdx(Number(e.target.value))}
            className="flex-1 min-w-40"
          >
            {subjects.length === 0 && <option value={-1}>（教科がありません）</option>}
            {subjects.map((s, i) => (
              <option key={i} value={i}>
                {s.name || `Subject ${i + 1}`}
              </option>
            ))}
          </select>
          <button onClick={addSubject} className="btn btn-secondary text-sm">
            + 教科追加
          </button>
          {current && (
            <button onClick={removeSubject} className="btn btn-danger text-sm">
              削除
            </button>
          )}
        </div>

        {current && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">教科名</label>
                <input
                  type="text"
                  value={current.name}
                  onChange={(e) => updateSubject(currentIdx, { name: e.target.value })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">テンプレート</label>
                <select
                  value={current.sheet_template || "default"}
                  onChange={(e) => updateSubject(currentIdx, { sheet_template: e.target.value })}
                  className="w-full"
                >
                  <option value="default">片面（default）</option>
                  <option value="math_double">数学（2ページ）</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bulk actions */}
      {current && (
        <div className="card">
          <h3 className="font-semibold mb-3">一括操作</h3>
          <BulkControls onGenerate={bulkGenerate} questionCount={current.questions.length} />
        </div>
      )}

      {/* Questions */}
      {current && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">問題一覧（{current.questions.length}問）</h3>
            <button onClick={addQuestion} className="btn btn-secondary text-sm">
              + 問題追加
            </button>
          </div>

          {current.questions.length === 0 ? (
            <p className="text-[var(--text-secondary)] text-center py-6">
              問題がありません。「一括生成」または「+ 問題追加」で作成してください。
            </p>
          ) : (
            <div className="space-y-3">
              {current.questions.map((q, qi) => (
                <QuestionRow
                  key={qi}
                  q={q as Record<string, unknown>}
                  idx={qi}
                  onUpdate={(patch) => {
                    const qs = [...current.questions];
                    qs[qi] = { ...qs[qi], ...patch };
                    updateSubject(currentIdx, { questions: qs });
                  }}
                  onRemove={() => {
                    const qs = current.questions.filter((_, i) => i !== qi);
                    updateSubject(currentIdx, { questions: qs });
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Bulk Controls ───────────────────────────────────────── */

function BulkControls({
  onGenerate,
  questionCount,
}: {
  onGenerate: (count: number, choices: number) => void;
  questionCount: number;
}) {
  const [count, setCount] = useState(questionCount || 10);
  const [choices, setChoices] = useState(5);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label className="block text-sm text-[var(--text-secondary)] mb-1">問題数</label>
        <input
          type="number"
          min={0}
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="w-24"
        />
      </div>
      <div>
        <label className="block text-sm text-[var(--text-secondary)] mb-1">選択肢/問</label>
        <input
          type="number"
          min={0}
          value={choices}
          onChange={(e) => setChoices(Number(e.target.value))}
          className="w-24"
        />
      </div>
      <button onClick={() => onGenerate(count, choices)} className="btn btn-secondary text-sm">
        一括生成
      </button>
    </div>
  );
}

/* ── Question Row ──────────────────────────────────────── */

function QuestionRow({
  q,
  idx,
  onUpdate,
  onRemove,
}: {
  q: Record<string, unknown>;
  idx: number;
  onUpdate: (patch: Record<string, unknown>) => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  const numChoices = (q.num_choices as number) || (q.choices as unknown[])?.length || 0;
  const answer = q.answer as number | null | undefined;

  return (
    <div className="border border-[var(--border)] rounded-xl px-4 py-3">
      <div className="flex items-center justify-between">
        <button onClick={() => setOpen(!open)} className="flex items-center gap-2 text-left flex-1">
          <span className="text-sm font-mono text-[var(--text-secondary)] w-8">
            {open ? "▼" : "▶"}
          </span>
          <span className="font-medium">{(q.label as string) || `Q${idx + 1}`}</span>
          <span className="text-sm text-[var(--text-secondary)]">
            — {numChoices} 択 {answer != null ? `(正解: ${answer + 1})` : ""}
          </span>
        </button>
        <button onClick={onRemove} className="text-xs text-[var(--danger)] hover:underline ml-4">
          削除
        </button>
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-[var(--border)] grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-[var(--text-secondary)]">Label</label>
            <input
              type="text"
              value={(q.label as string) || ""}
              onChange={(e) => onUpdate({ label: e.target.value })}
              className="w-full text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)]">選択肢数</label>
            <input
              type="number"
              min={0}
              max={20}
              value={numChoices}
              onChange={(e) => onUpdate({ num_choices: Number(e.target.value) })}
              className="w-full text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)]">正解 (0-based)</label>
            <input
              type="number"
              min={0}
              value={answer ?? ""}
              onChange={(e) => onUpdate({ answer: e.target.value ? Number(e.target.value) : null })}
              className="w-full text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)]">Y位置</label>
            <input
              type="number"
              step="0.01"
              value={(q.y as number) ?? 0.2}
              onChange={(e) => onUpdate({ y: parseFloat(e.target.value) })}
              className="w-full text-sm"
            />
          </div>
        </div>
      )}
    </div>
  );
}
