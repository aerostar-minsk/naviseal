import fs from "node:fs";
import path from "node:path";

const EEC_PDF =
  "https://eec.eaeunion.org/upload/files/dep_tamoj_infr/0i191/RLC191_GPU0_SEM_Special_Economic_Measures.pdf";

type Generated = {
  rules: {
    // prefix теперь объекты
    prefix: Array<{ prefix: string; source: "static" | "eec"; raw?: string; tag?: string; note?: string }>;
    // exact только 10-значные
    exact: Array<{ code: string; tag?: string; note?: string; source?: string }>;
    // ranges могут быть из static (4-значные) или eec (len/mode)
    ranges: Array<{ from: string; to: string; tag?: string; note?: string; len?: number; mode?: "prefix" | "numeric"; source?: string }>;
  };
  sources?: any;
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
    return { rules: { exact: [], ranges: [], prefix: [] }, sources: { warning: "rules.generated.json missing" } };
  }
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

export function checkTnved(codeRaw: string):
  | { ok: true; reason: string; matched: any; eec?: { raw: string; title: string; url: string } }
  | { ok: false; reason: string } {
  const code = onlyDigits(codeRaw);
  if (!code) return { ok: false, reason: "Введите код ТН ВЭД (только цифры)" };

  const g = loadGenerated();

  // 1) exact (10-значные)
  const exact = g.rules.exact.find((e) => e.code === code);
  if (exact) {
    return {
      ok: true,
      reason: `Требуется пломба: точный код ${exact.code}`,
      matched: { type: "exact", ...exact }
    };
  }

 // 2) prefix (совместим и со string и с object)
for (const item of g.rules.prefix as any[]) {
  const p = String(item.prefix ?? "");
  if (!p) continue;

  if (code.startsWith(p)) {
    const isEec = item.source === "eec" && typeof item.raw === "string" && item.raw.toLowerCase().startsWith("из ");

    return {
      ok: true,
      reason: isEec
        ? `Требуется пломба: попадает под правило ${item.raw}`
        : `Требуется пломба: попадает под префикс ${p}`,
      matched: { type: "prefix", prefix: p, source: item.source, raw: item.raw },
      eec: isEec
        ? {
            raw: item.raw,
            title: "Реестр ЕЭК (специальные экономические меры)",
            url: EEC_PDF
          }
        : undefined
    };
  }
}

  // 3) ranges (универсально: 4/6 = prefix-range, 10 = numeric)
  for (const r of g.rules.ranges) {
    const from = String(r.from ?? "");
    const to = String(r.to ?? "");

    // prefix-range: если from/to 4 или 6 и одинаковой длины
    if ((from.length === 4 || from.length === 6) && from.length === to.length) {
      const L = from.length;
      if (code.length >= L) {
        const head = code.slice(0, L);
        if (head >= from && head <= to) {
          return {
            ok: true,
            reason: `Требуется пломба: диапазон ${from}–${to} (по префиксу ${L})`,
            matched: { type: "range_prefix", from, to, len: L, source: r.source }
          };
        }
      }
      continue;
    }

    // numeric-range: 10
    if (from.length === 10 && to.length === 10) {
      if (cmpBig(code, from) >= 0 && cmpBig(code, to) <= 0) {
        return {
          ok: true,
          reason: `Требуется пломба: диапазон ${from}–${to}`,
          matched: { type: "range_numeric", from, to, source: r.source }
        };
      }
    }
  }

  return { ok: false, reason: "По текущим правилам (этап 1) пломба не требуется" };
}
