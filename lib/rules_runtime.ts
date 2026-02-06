import fs from "node:fs";
import path from "node:path";

type Generated = {
  version: number;
  generatedAt: string;
  sources: unknown;
  rules: {
    exact: Array<{ code: string; tag?: string; note?: string; source?: string }>;
    ranges: Array<{ from: string; to: string; tag?: string; note?: string; source?: string }>;
    prefix: string[];
  };
};

function onlyDigits(s: string): string {
  return (s ?? "").toString().trim().replace(/\D/g, "");
}

function cmpBig(a: string, b: string): number {
  const x = BigInt(a);
  const y = BigInt(b);
  return x === y ? 0 : x < y ? -1 : 1;
}

function loadGenerated(): Generated {
  const p = path.join(process.cwd(), "data", "rules.generated.json");
  if (!fs.existsSync(p)) {
    throw new Error(
      "Нет data/rules.generated.json. Запусти: npm run update:rules (или сначала npm run import:csv, затем обновление)."
    );
  }
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

export function checkTnved(codeRaw: string) {
  const code = onlyDigits(codeRaw);
  if (!code) return { ok: false as const, reason: "Введите код ТН ВЭД (цифры)" };

  const g = loadGenerated();

  // 1) exact
  const exact = g.rules.exact.find((e) => e.code === code);
  if (exact) {
    return {
      ok: true as const,
      reason: `Требуется пломба: точный код ${exact.code}`,
      matched: { type: "exact" as const, ...exact }
    };
  }

  // 2) prefix ("из 8517" -> любое значение, начинающееся с 8517)
  for (const p of g.rules.prefix) {
    if (code.startsWith(p)) {
      return {
        ok: true as const,
        reason: `Требуется пломба: попадает под префикс "из ${p}"`,
        matched: { type: "prefix" as const, prefix: p }
      };
    }
  }

 // 3) ranges (универсально)
for (const r of g.rules.ranges as any[]) {
  const from = String(r.from ?? "");
  const to = String(r.to ?? "");

  // если from/to 4 или 6 знаков — это префиксный диапазон
  if ((from.length === 4 || from.length === 6) && from.length === to.length) {
    const L = from.length;
    if (code.length >= L) {
      const head = code.slice(0, L);
      if (head >= from && head <= to) {
        return {
          ok: true,
          reason: `Требуется пломба: диапазон ${from}–${to} (по префиксу ${L})`,
          matched: { type: "range_prefix", from, to, len: L }
        };
      }
    }
    continue;
  }

  // если from/to 10 знаков — числовой диапазон
  if (from.length === 10 && to.length === 10) {
    if (cmpBig(code, from) >= 0 && cmpBig(code, to) <= 0) {
      return {
        ok: true,
        reason: `Требуется пломба: диапазон ${from}–${to}`,
        matched: { type: "range_numeric", from, to }
      };
    }
  }
}


  return { ok: false as const, reason: "По текущим правилам (этап 1) пломба не требуется" };
}
