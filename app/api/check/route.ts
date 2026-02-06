import { NextResponse } from "next/server";
import { checkTnved } from "@/lib/rules_runtime";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as null | { code?: string };
  const code = body?.code ?? "";

  const result = checkTnved(code);

  return NextResponse.json({
    input: code,
    normalized: (code ?? "").toString().replace(/\D/g, ""),
    requiresSeal: result.ok,
    result
  });
}
