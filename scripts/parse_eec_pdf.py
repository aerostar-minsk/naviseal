import sys, json, re
from datetime import datetime

import pdfplumber

def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

RE_PREFIX = re.compile(r"\bиз\s+(\d[\d\s]{3,13})\b", re.IGNORECASE)
RE_RANGE = re.compile(r"\b(\d[\d\s]{3,13})\s*[-–—]\s*(\d[\d\s]{3,13})\b")
RE_CODE = re.compile(r"\b\d[\d\s]{3,13}\b")

def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/parse_eec_pdf.py <input.pdf> <output.json>")
        sys.exit(2)

    pdf_path = sys.argv[1]
    out_path = sys.argv[2]

    text_all = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_all.append(t)

    text = "\n".join(text_all)

    prefixes = set()
    ranges = set()
    exact = set()

    for m in RE_PREFIX.finditer(text):
        code = only_digits(m.group(1))
        if len(code) >= 4:
            prefixes.add(code)

    for m in RE_RANGE.finditer(text):
        a = only_digits(m.group(1))
        b = only_digits(m.group(2))
        if len(a) >= 4 and len(b) >= 4:
            ranges.add((a, b))

    bad_years = set(str(y) for y in range(1990, 2035))
    for m in RE_CODE.finditer(text):
        code = only_digits(m.group(0))
        if not (4 <= len(code) <= 10):
            continue
        if code in bad_years:
            continue
        if len(code) == 4:
            prefixes.add(code)
        else:
            exact.add(code)

    def covered_by_prefix(c: str) -> bool:
        for p in prefixes:
            if c.startswith(p):
                return True
        return False

    exact = {c for c in exact if not covered_by_prefix(c)}

    out = {
        "source": "EEC registry (special economic measures)",
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "rules": {
            "prefix": sorted(prefixes),
            "ranges": [{"from": a, "to": b} for (a, b) in sorted(ranges)],
            "exact": sorted(exact)
        },
        "stats": {
            "prefix": len(prefixes),
            "ranges": len(ranges),
            "exact": len(exact)
        }
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("OK:", out_path, out["stats"])

if __name__ == "__main__":
    main()
