import fs from "node:fs";
import path from "node:path";

type StaticRules = {
  version: number;
  updatedAt: string;
  exact: Array<{ code: string; tag?: string; note?: string }>;
  ranges: Array<{ from: string; to: string; tag?: string; note?: string }>;
};

type EecRules = {
  source?: string;
  generatedAt?: string;
  rules: {
    prefixObjects?: Array<{ prefix: string; raw?: string | null }>;
    exact?: string[];
    ranges?: Array<{ from: string; to: string; len?: number; mode?: "prefix" | "numeric"; raw?: string }>;
  };
};

type PrefixRule = {
  prefix: string;
  source: "static" | "eec";
  raw?: string;
  tag?: string;
  note?: string;
};

function readJson<T>(p: string): T {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

function main() {
  const dataDir = path.join(process.cwd(), "data");
  const staticPath = path.join(dataDir, "rules.json");
  const eecPath = path.join(dataDir, "eec_rules.json");
  const outPath = path.join(dataDir, "rules.generated.json");

  if (!fs.existsSync(staticPath)) throw new Error("Нет data/rules.json — сначала npm run import:csv");
  if (!fs.existsSync(eecPath)) throw new Error("Нет data/eec_rules.json — сначала парсинг PDF");

  const staticRules = readJson<StaticRules>(staticPath);
  const eec = readJson<EecRules>(eecPath);

  // -------- exact: берём статичные и ЕЭК, но в итог кладём только 10-значные --------
  const exactMap = new Map<string, { code: string; tag?: string; note?: string; source: "static" | "eec" }>();

  for (const e of staticRules.exact) exactMap.set(e.code, { ...e, source: "static" });
  for (const code of eec.rules.exact ?? []) if (!exactMap.has(code)) exactMap.set(code, { code, source: "eec" });

  // -------- prefix: по уму --------
  const prefixByValue = new Map<string, PrefixRule>();

  // (A) ЕЭК prefixObjects — источник eec + raw только если реально есть "из ..."
  for (const it of eec.rules.prefixObjects ?? []) {
    const p = String(it.prefix ?? "").trim();
    if (!p) continue;
    prefixByValue.set(p, {
      prefix: p,
      source: "eec",
      raw: it.raw ?? undefined
    });
  }

  // (B) переносим 4/6 из exact (static/eec) в prefix, если их ещё нет
  for (const e of exactMap.values()) {
    if (e.code.length === 4 || e.code.length === 6) {
      if (!prefixByValue.has(e.code)) {
        prefixByValue.set(e.code, { prefix: e.code, source: e.source });
      }
    }
  }

  // -------- ranges --------
  const rangeKey = (r: any) => `${r.from}..${r.to}..${r.len ?? ""}..${r.mode ?? ""}..${r.raw ?? ""}..${r.tag ?? ""}..${r.note ?? ""}`;
  const rangeMap = new Map<string, any>();

  for (const r of staticRules.ranges) rangeMap.set(rangeKey(r), { ...r, source: "static" });

  for (const r of eec.rules.ranges ?? []) {
    const rr = { from: r.from, to: r.to, len: r.len, mode: r.mode, raw: r.raw, source: "eec" };
    const k = rangeKey(rr);
    if (!rangeMap.has(k)) rangeMap.set(k, rr);
  }

  // -------- финал --------
  const exact10 = Array.from(exactMap.values())
    .filter((x) => x.code.length === 10)
    .sort((a, b) => a.code.localeCompare(b.code));

  const prefix = Array.from(prefixByValue.values()).sort((a, b) => a.prefix.localeCompare(b.prefix));
  const ranges = Array.from(rangeMap.values()).sort((a, b) => String(a.from).localeCompare(String(b.from)));

  const out = {
    version: 1,
    generatedAt: new Date().toISOString(),
    sources: {
      eec: eec.source ?? "EEC registry",
      eecGeneratedAt: eec.generatedAt ?? null,
      staticUpdatedAt: staticRules.updatedAt
    },
    rules: {
      prefix,   // <-- объекты с source/raw
      exact: exact10,
      ranges
    }
  };

  fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf-8");
  console.log("OK:", outPath);
  console.log(`prefix: ${prefix.length}, exact10: ${exact10.length}, ranges: ${ranges.length}`);
}

main();
