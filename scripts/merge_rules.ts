import fs from "node:fs";
import path from "node:path";

type StaticRules = {
  version: number;
  updatedAt: string;
  exact: Array<{ code: string; tag?: string; note?: string }>;
  ranges: Array<{ from: string; to: string; tag?: string; note?: string }>;
};

type EecRules = {
  source: string;
  generatedAt: string;
  rules: {
    exact: string[];
    prefix: string[];
    ranges: Array<{ from: string; to: string }>;
  };
  stats?: unknown;
};

function readJson<T>(p: string): T {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

function main() {
  const dataDir = path.join(process.cwd(), "data");
  const staticPath = path.join(dataDir, "rules.json"); // из CSV
  const eecPath = path.join(dataDir, "eec_rules.json"); // из PDF
  const outPath = path.join(dataDir, "rules.generated.json");

  if (!fs.existsSync(staticPath)) throw new Error("Нет data/rules.json — сначала npm run import:csv");
  if (!fs.existsSync(eecPath)) throw new Error("Нет data/eec_rules.json — сначала парсинг PDF");

  const staticRules = readJson<StaticRules>(staticPath);
  const eec = readJson<EecRules>(eecPath);

  const exactMap = new Map<string, { code: string; tag?: string; note?: string; source?: string }>();
  for (const e of staticRules.exact) exactMap.set(e.code, { ...e, source: "static" });
  for (const code of eec.rules.exact) {
    if (!exactMap.has(code)) exactMap.set(code, { code, source: "eec" });
  }

  const rangeKey = (a: string, b: string) => `${a}..${b}`;
  const rangeMap = new Map<string, { from: string; to: string; tag?: string; note?: string; source?: string }>();
  for (const r of staticRules.ranges) rangeMap.set(rangeKey(r.from, r.to), { ...r, source: "static" });
  for (const r of eec.rules.ranges) {
    const k = rangeKey(r.from, r.to);
    if (!rangeMap.has(k)) rangeMap.set(k, { ...r, source: "eec" });
  }

  const prefixSet = new Set<string>([...eec.rules.prefix]);

  const out = {
    version: 1,
    generatedAt: new Date().toISOString(),
    sources: {
      eec: eec.source,
      eecGeneratedAt: eec.generatedAt,
      staticUpdatedAt: staticRules.updatedAt
    },
    rules: {
      exact: Array.from(exactMap.values()).sort((a, b) => a.code.localeCompare(b.code)),
      ranges: Array.from(rangeMap.values()).sort((a, b) => a.from.localeCompare(b.from)),
      prefix: Array.from(prefixSet).sort((a, b) => a.localeCompare(b))
    }
  };

  fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf-8");
  console.log("OK:", outPath);
}

main();
