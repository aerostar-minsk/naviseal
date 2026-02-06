import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { checkTnved } from "../lib/rules_runtime";

function writeRulesGenerated(dir: string) {
  const dataDir = path.join(dir, "data");
  fs.mkdirSync(dataDir, { recursive: true });
  const out = {
    version: 1,
    generatedAt: new Date().toISOString(),
    sources: {},
    rules: {
      exact: [{ code: "2939790000", source: "test" }],
      ranges: [{ from: "220300", to: "220399", source: "test" }],
      prefix: ["8517"]
    }
  };
  fs.writeFileSync(path.join(dataDir, "rules.generated.json"), JSON.stringify(out, null, 2), "utf-8");
}

describe("checkTnved", () => {
  const origCwd = process.cwd;
  let tmp = "";
  let spy: any = null;

  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "seal-"));
    writeRulesGenerated(tmp);
    spy = vi.spyOn(process, "cwd").mockImplementation(() => tmp);
  });

  afterEach(() => {
    try {
      spy?.mockRestore();
    } catch {}
    // best-effort cleanup
    try {
      fs.rmSync(tmp, { recursive: true, force: true });
    } catch {}
  });

  it("matches exact codes", () => {
    const res = checkTnved("2939790000");
    expect(res.ok).toBe(true);
    // @ts-ignore
    expect(res.matched.type).toBe("exact");
  });

  it("matches prefix rules", () => {
    const res = checkTnved("85171234");
    expect(res.ok).toBe(true);
    // @ts-ignore
    expect(res.matched.type).toBe("prefix");
    // @ts-ignore
    expect(res.matched.prefix).toBe("8517");
  });

  it("matches ranges", () => {
    const res = checkTnved("220350");
    expect(res.ok).toBe(true);
    // @ts-ignore
    expect(res.matched.type).toBe("range");
  });

  it("returns not required for unknown codes", () => {
    const res = checkTnved("999999");
    expect(res.ok).toBe(false);
  });

  it("validates input and rejects non-digit-only input", () => {
    const res = checkTnved("");
    expect(res.ok).toBe(false);
    // reason should hint to enter code
    expect((res as any).reason).toMatch(/Введите/);
  });
});
