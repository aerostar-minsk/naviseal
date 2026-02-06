import fs from "node:fs";
import path from "node:path";

const REGISTRY_PAGE =
  "https://eec.eaeunion.org/comission/department/dep_tamoj_infr/0I191/1Activity_2CID_3RLC_4Goods.php";

function ensureDir(p: string) {
  fs.mkdirSync(p, { recursive: true });
}

async function main() {
  ensureDir(path.join(process.cwd(), "data"));

  const html = await fetch(REGISTRY_PAGE, { cache: "no-store" }).then((r) => r.text());

  // Пытаемся найти ссылку на PDF реестра на странице.
  // Если структура поменяется — это место нужно подправить.
  const match =
    html.match(/href="([^"]+\.pdf)"/i) ||
    html.match(/href="([^"]+upload\/files[^"]+\.pdf)"/i);

  if (!match) {
    throw new Error("Не нашёл ссылку на PDF на странице ЕЭК (структура могла поменяться)");
  }

  const pdfUrl = new URL(match[1], REGISTRY_PAGE).toString();
  const buf = await fetch(pdfUrl, { cache: "no-store" }).then((r) => r.arrayBuffer());

  const pdfPath = path.join(process.cwd(), "data", "eec_registry.pdf");
  fs.writeFileSync(pdfPath, Buffer.from(buf));

  const meta = {
    registryPage: REGISTRY_PAGE,
    pdfUrl,
    fetchedAt: new Date().toISOString()
  };
  fs.writeFileSync(path.join(process.cwd(), "data", "eec_source.json"), JSON.stringify(meta, null, 2));

  console.log("OK:", pdfPath);
  console.log("PDF:", pdfUrl);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
