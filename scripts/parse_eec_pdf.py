import sys, json, re
from datetime import datetime
import pdfplumber

# ----------------- Regexes -----------------
RE_PREFIX = re.compile(r"^\s*из\s+(\d[\d\s]{3,13})\s*$", re.IGNORECASE)
RE_RANGE = re.compile(r"^\s*(\d[\d\s]{3,13})\s*[-–—]\s*(\d[\d\s]{3,13})\s*$")

# даты и “похожее на даты”
RE_DATE = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{2,4}\s*$")
RE_DATE_RANGE = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{2,4}\s*[-–—]\s*\d{1,2}\.\d{1,2}\.\d{2,4}\s*$")
RE_ANY_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")

RE_SPLIT = re.compile(r"[;,]\s*|\n+")

# заголовки колонки с кодом
HEADER_HINTS = [
    "тн вэд", "тнвэд", "tn ved", "tnved",
    "код тн", "код товара", "код", "hs code", "код hs"
]

LAST_TABLE_SHAPE = None  # (cols_count, code_col)
def table_cols_count(table):
    if not table:
        return 0
    # берем максимальную длину строки, так надежнее
    return max(len(r) for r in table if r)

def looks_like_continuation(table, last_shape):
    if not last_shape:
        return False
    last_cols, last_code_col = last_shape
    cols = table_cols_count(table)
    # Продолжение обычно имеет то же число колонок (или отличается на 1 из-за пустой колонки)
    return cols == last_cols or cols == last_cols + 1 or cols + 1 == last_cols


# ----------------- Helpers -----------------
def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def is_date_like(raw: str) -> bool:
    raw = (raw or "").strip()
    if RE_DATE.match(raw) or RE_DATE_RANGE.match(raw):
        return True
    # иногда дата внутри строки
    if RE_ANY_DATE.search(raw):
        return True
    return False

def tnved_len_ok(digits: str) -> bool:
    # Для надёжности: используем только 4/6/10
    return len(digits) in (4, 6, 10)

def is_probably_tnved(digits: str, raw: str) -> bool:
    if not digits:
        return False
    if is_date_like(raw):
        return False
    if not tnved_len_ok(digits):
        return False

    # Жёсткий анти-фильтр “DDMMYYYY..” на 8/10-значных (дата, склеенная в цифры)
    # Пример: 31.12.2023 -> 31122023 (мы 8 не берём, но на всякий случай)
    if re.match(r"^(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(19|20)\d{2}", digits):
        return False

    return True

def detect_code_column_by_header(header_row):
    if not header_row:
        return None
    norms = [normalize_spaces(c).lower() for c in header_row]
    for i, h in enumerate(norms):
        for hint in HEADER_HINTS:
            if hint in h:
                return i
    return None

def choose_code_column(table):
    global LAST_TABLE_SHAPE

    header = table[0] if table else None
    by_header = detect_code_column_by_header(header)

    if by_header is not None:
        # нашли “настоящую” таблицу с заголовком — запоминаем структуру
        LAST_TABLE_SHAPE = (table_cols_count(table), by_header)
        return by_header

    # заголовка нет → возможно продолжение таблицы
    if looks_like_continuation(table, LAST_TABLE_SHAPE):
        return LAST_TABLE_SHAPE[1]

    return None

def parse_code_cell(cell: str):
    """
    Возвращает список правил из одной ячейки:
    - prefix: 4/6 (и иногда 10, но 10 лучше exact)
    - exact: 10
    - range: with len and mode:
        mode="prefix" для 4/6
        mode="numeric" для 10
    """
    out = []
    raw_cell = (cell or "").strip()
    if not raw_cell:
        return out

    # отсекаем ячейки с датой
    if is_date_like(raw_cell):
        return out

    parts = [p.strip() for p in RE_SPLIT.split(raw_cell) if p.strip()]
    for p in parts:
        if is_date_like(p):
            continue

        m = RE_PREFIX.match(p)
        if m:
            d = only_digits(m.group(1))
            if is_probably_tnved(d, p):
                if len(d) == 10:
                    out.append(("exact", d, p))
                else:
                    out.append(("prefix", d, p))
            continue

        m = RE_RANGE.match(p)
        if m:
            a_raw = m.group(1)
            b_raw = m.group(2)
            a = only_digits(a_raw)
            b = only_digits(b_raw)
            if not (is_probably_tnved(a, a_raw) and is_probably_tnved(b, b_raw)):
                continue
            if len(a) != len(b):
                continue  # разные длины — слишком рискованно
            L = len(a)
            if L in (4, 6):
                out.append(("range", {"from": a, "to": b, "len": L, "mode": "prefix"}, p))
            elif L == 10:
                out.append(("range", {"from": a, "to": b, "len": L, "mode": "numeric"}, p))
            continue

        d = only_digits(p)
        if is_probably_tnved(d, p):
            if len(d) == 10:
                out.append(("exact", d, p))
            else:
                out.append(("prefix", d, p))
            continue

    return out

# ----------------- Main -----------------
def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/parse_eec_pdf.py <input.pdf> <output.json>")
        sys.exit(2)

    pdf_path = sys.argv[1]
    out_path = sys.argv[2]

    prefixes = set()
    exact = set()
    ranges = set()  # tuples: (from, to, len, mode)

    debug_hits = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_i, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for t_i, t in enumerate(tables, start=1):
                # нормализуем таблицу
                table = [[(c or "").strip() for c in row] for row in t if row]
                if not table or len(table) < 2:
                    continue

                code_col = choose_code_column(table)
                if code_col is None:
                    continue

                # ---------- SANITY CHECK ----------
                # В первых 10 строках "кодовой" колонки должно быть хотя бы 2 валидных совпадения.
                hits = 0
                for test_row in table[1:11]:
                    if not test_row:
                        continue
                    if code_col < len(test_row):
                        cell = test_row[code_col] or ""
                        if parse_code_cell(cell):
                            hits += 1
                if hits < 2:
                    # значит это не та таблица/не та колонка
                    continue
                # ---------- /SANITY CHECK ----------

                # парсим строки
                for r_i, row in enumerate(table[1:], start=2):
                    if not row or code_col >= len(row):
                        continue

                    raw = row[code_col] or ""
                    items = parse_code_cell(raw)

                    for kind, value, raw_part in items:
                        if kind == "prefix":
                            prefixes.add(value)
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "prefix", "value": value, "raw": raw_part
                            })
                        elif kind == "exact":
                            exact.add(value)
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "exact", "value": value, "raw": raw_part
                            })
                        elif kind == "range":
                            ranges.add((value["from"], value["to"], value["len"], value["mode"]))
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "range", "value": value, "raw": raw_part
                            })

    # exact, покрытые prefix — убираем
    def covered_by_prefix(c: str) -> bool:
        return any(c.startswith(p) for p in prefixes)

    exact = {c for c in exact if not covered_by_prefix(c)}

    out = {
        "source": "EEC registry (special economic measures) — robust table parser",
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "rules": {
            "prefix": sorted(prefixes),
            "exact": sorted(exact),
            "ranges": [
                {"from": a, "to": b, "len": L, "mode": mode}
                for (a, b, L, mode) in sorted(ranges)
            ]
        },
        "stats": {
            "prefix": len(prefixes),
            "exact": len(exact),
            "ranges": len(ranges)
        },
        "debug": {
            "note": "Первые 200 совпадений (для проверки источника строк).",
            "hitsSample": debug_hits[:200]
        }
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("OK:", out_path, out["stats"])

if __name__ == "__main__":
    main()
