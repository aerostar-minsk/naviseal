import fs from "node:fs";
import path from "node:path";
import { parse } from "csv-parse/sync";

type CsvRow = {
  kind: "exact" | "range";
  from: string;
  to?: string;
  tag?: string;
  note?: string;
};

type RulesJson = {
  version: number;
  updatedAt: string;
  exact: Array<{ code: string; tag?: string; note?: string }>;
  ranges: Array<{ from: string; to: string; tag?: string; note?: string }>;
};

const projectRoot = process.cwd();
const csvPath = path.join(projectRoot, "data", "rules.csv");
const outPath = path.join(projectRoot, "data", "rules.json");

function onlyDigits(s: string): string {
  return (s ?? "").toString().trim().replace(/\D/g, "");
}

function assertNonEmpty(name: string, v: string) {
  if (!v || v.trim().length === 0) throw new Error(`CSV: поле "${name}" пустое`);
}

function main() {
  if (!fs.existsSync(csvPath)) {
    throw new Error(`Не найден файл: ${csvPath}`);
  }

  const csvRaw = fs.readFileSync(csvPath, "utf-8");
  const rows = parse(csvRaw, {
    columns: true,
    skip_empty_lines: true,
    trim: true
  }) as CsvRow[];

  const exact: RulesJson["exact"] = [];
  const ranges: RulesJson["ranges"] = [];

  for (const [i, r] of rows.entries()) {
    const rowNum = i + 2; // с учетом заголовка
    if (r.kind !== "exact" && r.kind !== "range") {
      throw new Error(`CSV строка ${rowNum}: kind должен быть exact|range`);
    }

    const from = onlyDigits(r.from);
    assertNonEmpty("from", from);

    const tag = r.tag?.trim() || undefined;
    const note = r.note?.trim() || undefined;

    if (r.kind === "exact") {
      exact.push({ code: from, tag, note });
      continue;
    }

    const to = onlyDigits(r.to ?? "");
    assertNonEmpty("to", to);

    const a = BigInt(from);
    const b = BigInt(to);
    if (a > b) {
      throw new Error(`CSV строка ${rowNum}: from > to (${from} > ${to})`);
    }

    ranges.push({ from, to, tag, note });
  }

  // дедуп exact по коду (последний побеждает)
  const dedup = new Map<string, RulesJson["exact"][number]>();
  for (const e of exact) dedup.set(e.code, e);

  const out: RulesJson = {
    version: 1,
    updatedAt: new Date().toISOString(),
    exact: Array.from(dedup.values()).sort((a, b) => a.code.localeCompare(b.code)),
    ranges: ranges.sort((a, b) => a.from.localeCompare(b.from))
  };

  fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf-8");
  console.log(`OK: записано ${outPath}`);
  console.log(`exact: ${out.exact.length}, ranges: ${out.ranges.length}`);
}

main();
