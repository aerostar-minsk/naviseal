"use client";

import React, { useMemo, useState } from "react";

type ApiResponse = {
  input: string;
  normalized: string;
  requiresSeal: boolean;
  result:
    | { ok: true; reason: string; matched?: any }
    | { ok: false; reason: string };
};

export default function Page() {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ApiResponse | null>(null);
  const normalizedPreview = useMemo(() => code.replace(/\D/g, ""), [code]);

  async function onCheck() {
    setLoading(true);
    setData(null);
    try {
      const res = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });
      const json = (await res.json()) as ApiResponse;
      setData(json);
    } finally {
      setLoading(false);
    }
  }

  const badge = data
    ? data.requiresSeal
      ? { text: "Требуется пломба", style: { background: "#e7f7ed", borderColor: "#7bd89b" } }
      : { text: "Не требуется", style: { background: "#f4f4f4", borderColor: "#d0d0d0" } }
    : null;

  return (
    <main style={{ maxWidth: 760, margin: "40px auto", padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>Проверка навигационной пломбы по ТН ВЭД (Этап 1)</h1>
      <p style={{ marginTop: 0, opacity: 0.75 }}>
        Введите код ТН ВЭД → получите ответ, подпадает ли товар под отслеживание с навигационной пломбой.
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 18 }}>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Например: 8517 или 220300 или 2939790000"
          style={{
            flex: 1,
            padding: "12px 14px",
            borderRadius: 10,
            border: "1px solid #ddd",
            fontSize: 16
          }}
        />
        <button
          onClick={onCheck}
          disabled={loading}
          style={{
            padding: "12px 14px",
            borderRadius: 10,
            border: "1px solid #ddd",
            fontSize: 16,
            cursor: loading ? "not-allowed" : "pointer"
          }}
        >
          {loading ? "Проверяю…" : "Проверить"}
        </button>
      </div>

      <div style={{ marginTop: 8, fontSize: 13, opacity: 0.7 }}>
        Нормализовано: <b>{normalizedPreview || "—"}</b>
      </div>

      {data && (
        <section
          style={{
            marginTop: 18,
            padding: 16,
            borderRadius: 14,
            border: "1px solid #e5e5e5",
            background: "#fff"
          }}
        >
          {badge && (
            <div
              style={{
                display: "inline-block",
                padding: "6px 10px",
                borderRadius: 999,
                border: "1px solid",
                ...badge.style
              }}
            >
              {badge.text}
            </div>
          )}

          <h2 style={{ margin: "12px 0 6px", fontSize: 18 }}>Результат</h2>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
            <b>Причина:</b> {data.result.reason}
          </div>

          <details style={{ marginTop: 10 }}>
            <summary style={{ cursor: "pointer" }}>Технические детали</summary>
            <pre style={{ marginTop: 10, padding: 12, borderRadius: 12, background: "#f7f7f7", overflowX: "auto" }}>
              {JSON.stringify(data, null, 2)}
            </pre>
          </details>
        </section>
      )}

      <section style={{ marginTop: 20, opacity: 0.8, fontSize: 13, lineHeight: 1.45 }}>
        <p style={{ marginBottom: 6 }}>
          Источник статичных правил: <code>data/rules.csv</code>. Динамический список (санкционные товары) обновляется из реестра ЕЭК через GitHub Actions.
        </p>
      </section>
    </main>
  );
}
