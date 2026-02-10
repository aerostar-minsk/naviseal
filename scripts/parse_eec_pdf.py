import sys, json, re
from datetime import datetime

import pdfplumber

# Optional: pdfminer (часто уже установлен как зависимость)
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None

# Optional: PyMuPDF (fitz). Если не установлен — просто не используем.
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


# ----------------- Regexes -----------------
RE_PREFIX = re.compile(r"^\s*из\s+(\d[\d\s]{3,13})\s*$", re.IGNORECASE)
RE_RANGE = re.compile(r"^\s*(\d[\d\s]{3,13})\s*[-–—]\s*(\d[\d\s]{3,13})\s*$")

RE_DATE = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{2,4}\s*$")
RE_DATE_RANGE = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{2,4}\s*[-–—]\s*\d{1,2}\.\d{1,2}\.\d{2,4}\s*$")
RE_ANY_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")

RE_SPLIT = re.compile(r"[;,]\s*|\n+")

HEADER_HINTS = [
    "тн вэд", "тнвэд", "tnved", "tn ved",
    "код тн", "код тнвэд", "код товара", "код",
]

# Фрагменты с цифрами и разделителями -> нормализуем в digits-only
RE_CHUNK_NUMBERS = re.compile(r"(?<!\d)\d[\d\s\u00A0\u2009\u202F\-–—]{2,60}\d(?!\d)")
RE_SOLID_10 = re.compile(r"(?<!\d)\d{10}(?!\d)")


# ----------------- Helpers -----------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def is_date_like(raw: str) -> bool:
    raw = (raw or "").strip()
    return bool(RE_DATE.match(raw) or RE_DATE_RANGE.match(raw) or RE_ANY_DATE.search(raw))

def is_probably_tnved(code: str, raw: str) -> bool:
    if not code:
        return False
    if is_date_like(raw):
        return False
    # Разрешаем только 4/6/10
    if len(code) not in (4, 6, 10):
        return False
    # Отсекаем DDMMYYYY.. (на всякий)
    if re.match(r"^(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(19|20)\d{2}$", code):
        return False
    return True

def detect_code_col_by_header(header_row):
    if not header_row:
        return None
    hs = [norm(c).lower() for c in header_row]
    for i, h in enumerate(hs):
        if not h:
            continue
        for hint in HEADER_HINTS:
            if hint in h:
                return i
    return None

def table_cols_count(table):
    if not table:
        return 0
    return max(len(r) for r in table if r)


def extract_tables_robust(page):
    """
    Пробуем разные стратегии извлечения таблиц, выбираем вариант с максимумом таблиц.
    """
    settings_list = [
        None,
        {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 5,
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "edge_min_length": 10,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        },
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "intersection_tolerance": 5,
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        },
        {
            "vertical_strategy": "lines",
            "horizontal_strategy": "text",
            "intersection_tolerance": 5,
            "snap_tolerance": 3,
            "join_tolerance": 3,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        },
    ]

    best = []
    for s in settings_list:
        try:
            tables = page.extract_tables(table_settings=s) if s else (page.extract_tables() or [])
        except Exception:
            tables = []
        if tables and len(tables) > len(best):
            best = tables
    return best or []


def page_lines_from_words(page, y_tol=3):
    """
    Собираем "строки" из words (pdfplumber) по координате top.
    """
    words = page.extract_words(use_text_flow=True) or []
    if not words:
        return []
    words = sorted(words, key=lambda w: (round(w["top"] / y_tol), w["x0"]))

    lines = []
    cur_key = None
    cur = []

    for w in words:
        key = round(w["top"] / y_tol)
        if cur_key is None or key == cur_key:
            cur.append(w["text"])
            cur_key = key
        else:
            lines.append(" ".join(cur))
            cur = [w["text"]]
            cur_key = key
    if cur:
        lines.append(" ".join(cur))
    return lines


def extract_codes10_any(text: str):
    """
    Оставлено для совместимости, но ниже используем универсальный extract_codes_any_4_6_10.
    """
    if not text:
        return set()

    out = set()
    for m in RE_CHUNK_NUMBERS.finditer(text):
        chunk = m.group(0)
        code = re.sub(r"\D", "", chunk)
        if len(code) == 10:
            if re.match(r"^(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(19|20)\d{2}", code):
                continue
            out.add(code)

    for m in RE_SOLID_10.finditer(text):
        out.add(m.group(0))

    return out


def extract_codes_any_4_6_10(text: str):
    """
    Достаём коды 4/6/10 из текста (works для words/text).
    Берём фрагменты с цифрами+разделителями, нормализуем до digits-only.
    """
    if not text:
        return set()

    out = set()

    for m in RE_CHUNK_NUMBERS.finditer(text):
        chunk = m.group(0)
        code = re.sub(r"\D", "", chunk)
        if len(code) in (4, 6, 10):
            # отсекаем даты типа 31122023
            if re.match(r"^(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(19|20)\d{2}$", code):
                continue
            out.add(code)

    # плюс слитные коды (часто встречаются)
    for mm in re.finditer(r"(?<!\d)\d{4}(?!\d)", text):
        out.add(mm.group(0))
    for mm in re.finditer(r"(?<!\d)\d{6}(?!\d)", text):
        out.add(mm.group(0))
    for mm in re.finditer(r"(?<!\d)\d{10}(?!\d)", text):
        out.add(mm.group(0))

    return out


def filter_short_codes_if_covered_by_10(codes: set):
    """
    Убираем 4/6-значные коды ТОЛЬКО если они являются префиксом
    хотя бы одного 10-значного кода из того же набора.
    """
    if not codes:
        return set()

    tens = [c for c in codes if len(c) == 10]
    if not tens:
        return codes

    out = set(codes)
    for c in list(out):
        if len(c) in (4, 6):
            for t in tens:
                if t.startswith(c):
                    out.discard(c)
                    break
    return out


def add_code_to_rules(code: str, *, exact: set, prefix_objects: dict):
    """
    10 цифр -> exact
    4/6 -> prefixObjects (префикс-правило)
    """
    if not code:
        return
    if len(code) == 10:
        exact.add(code)
    elif len(code) in (4, 6):
        if code not in prefix_objects:
            prefix_objects[code] = {"prefix": code, "raw": None}


def extract_codes_from_page_words_pdfplumber(page):
    """
    Берем строки из words и извлекаем 4/6/10 ПОСТРОЧНО,
    чтобы точный фильтр (short covered by 10) работал корректно.
    """
    found = set()
    for line in page_lines_from_words(page):
        line_codes = extract_codes_any_4_6_10(line)
        line_codes = filter_short_codes_if_covered_by_10(line_codes)
        found |= line_codes
    return found


def extract_codes_any_from_pdfminer_page(pdf_path: str, page_i: int):
    if pdfminer_extract_text is None:
        return set()
    try:
        txt = pdfminer_extract_text(pdf_path, page_numbers=[page_i - 1]) or ""
    except Exception:
        txt = ""
    codes = extract_codes_any_4_6_10(txt)
    # pdfminer даёт весь текст страницы одним куском — фильтр здесь менее точный, но безопасный:
    # убираем 4/6 только если они покрываются 10 в этом куске
    return filter_short_codes_if_covered_by_10(codes)


def extract_codes_any_from_pymupdf_page(pdf_path: str, page_i: int):
    if fitz is None:
        return set()

    found = set()
    try:
        doc = fitz.open(pdf_path)
        p = doc[page_i - 1]

        # 1) простой текст страницы
        txt = p.get_text("text") or ""
        codes = extract_codes_any_4_6_10(txt)
        found |= filter_short_codes_if_covered_by_10(codes)

        # 2) words -> построчно (более точная фильтрация)
        words = p.get_text("words") or []
        lines = {}
        for w in words:
            key = (w[5], w[6])  # (block, line)
            lines.setdefault(key, []).append(w)
        for _, ws in lines.items():
            ws = sorted(ws, key=lambda x: x[0])  # x0
            line_text = " ".join([x[4] for x in ws])
            line_codes = extract_codes_any_4_6_10(line_text)
            line_codes = filter_short_codes_if_covered_by_10(line_codes)
            found |= line_codes

        doc.close()
    except Exception:
        pass

    return found


# ----------------- Table continuation memory -----------------
LAST_SHAPE = None  # (cols_count, code_col)

def choose_code_col(table):
    """
    1) Ищем колонку кода по заголовку.
    2) Если заголовка нет, допускаем продолжение таблицы (same cols count).
    """
    global LAST_SHAPE
    header = table[0] if table else None

    by_header = detect_code_col_by_header(header)
    if by_header is not None:
        LAST_SHAPE = (table_cols_count(table), by_header)
        return by_header

    if LAST_SHAPE:
        last_cols, last_col = LAST_SHAPE
        cols = table_cols_count(table)
        # допускаем +-1 колонку (часто из-за объединённых ячеек)
        if cols == last_cols or cols == last_cols + 1 or cols + 1 == last_cols:
            return last_col

    return None


def parse_code_cell(cell: str):
    """
    Возвращает список элементов:
      ("prefixObj", {"prefix":"8703","raw":"из 8703"})
      ("prefix", "8207")               # если реально отдельное 4/6
      ("exact", "8207506000")          # 10
      ("range", {...})
    """
    out = []
    raw_cell = (cell or "").strip()
    if not raw_cell:
        return out
    if is_date_like(raw_cell):
        return out

    parts = [p.strip() for p in RE_SPLIT.split(raw_cell) if p.strip()]

    # Сначала соберём exact(10) из этой ячейки, чтобы потом точнее отфильтровать 4/6 “обломки”
    exact_in_cell = set()

    tmp_items = []
    for p in parts:
        if is_date_like(p):
            continue

        m = RE_PREFIX.match(p)
        if m:
            code = digits(m.group(1))
            if is_probably_tnved(code, p):
                if len(code) == 10:
                    tmp_items.append(("exact", code))
                    exact_in_cell.add(code)
                else:
                    # явный префикс "из ####" — это настоящее правило, НЕ фильтруем
                    tmp_items.append(("prefixObj", {"prefix": code, "raw": f"из {code}"}))
            continue

        m = RE_RANGE.match(p)
        if m:
            a_raw = m.group(1)
            b_raw = m.group(2)
            a = digits(a_raw)
            b = digits(b_raw)
            if not (is_probably_tnved(a, a_raw) and is_probably_tnved(b, b_raw)):
                continue
            if len(a) != len(b):
                continue
            L = len(a)
            if L in (4, 6):
                tmp_items.append(("range", {"from": a, "to": b, "len": L, "mode": "prefix", "raw": p}))
            elif L == 10:
                tmp_items.append(("range", {"from": a, "to": b, "len": L, "mode": "numeric", "raw": p}))
            continue

        d = digits(p)
        if is_probably_tnved(d, p):
            if len(d) == 10:
                tmp_items.append(("exact", d))
                exact_in_cell.add(d)
            else:
                tmp_items.append(("prefix", d))
            continue

    # Теперь точная фильтрация: если prefix (4/6) является префиксом exact(10) в этой ЖЕ ячейке,
    # то это почти наверняка “обломок” записи 10-значного кода -> выкидываем.
    for kind, value in tmp_items:
        if kind == "prefix":
            p = value
            if exact_in_cell and any(x.startswith(p) for x in exact_in_cell):
                continue  # отбрасываем ложный prefix из 10-значной записи
        out.append((kind, value))

    return out


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/parse_eec_pdf.py <input.pdf> <output.json>")
        sys.exit(2)

    pdf_path = sys.argv[1]
    out_path = sys.argv[2]

    prefix_objects = {}  # prefix -> {"prefix":..., "raw":...} raw only if реально было "из ####"
    exact = set()
    ranges = set()  # (from,to,len,mode,raw)

    debug_hits = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_i, page in enumerate(pdf.pages, start=1):
            page_found_any = False

            # ✅ Page scan (pdfplumber words): 4/6/10 построчно
            page_codes_words = extract_codes_from_page_words_pdfplumber(page)
            for c in page_codes_words:
                add_code_to_rules(c, exact=exact, prefix_objects=prefix_objects)
                debug_hits.append({
                    "page": page_i, "table": None, "row": None,
                    "kind": "code_page_words_pdfplumber",
                    "value": c, "rawCell": None, "descCell": None
                })

            # ✅ Дополнительно пробуем pdfminer (если доступен)
            codes_pdfminer = extract_codes_any_from_pdfminer_page(pdf_path, page_i)
            for c in codes_pdfminer:
                add_code_to_rules(c, exact=exact, prefix_objects=prefix_objects)
                debug_hits.append({
                    "page": page_i, "table": None, "row": None,
                    "kind": "code_pdfminer",
                    "value": c, "rawCell": None, "descCell": None
                })

            # ✅ Дополнительно пробуем PyMuPDF (если доступен)
            codes_pymupdf = extract_codes_any_from_pymupdf_page(pdf_path, page_i)
            for c in codes_pymupdf:
                add_code_to_rules(c, exact=exact, prefix_objects=prefix_objects)
                debug_hits.append({
                    "page": page_i, "table": None, "row": None,
                    "kind": "code_pymupdf",
                    "value": c, "rawCell": None, "descCell": None
                })

            # --- robust tables ---
            tables = extract_tables_robust(page)
            if not tables:
                tables = []

            for t_i, t in enumerate(tables, start=1):
                table = [[(c or "").strip() for c in row] for row in t if row]
                if not table or len(table) < 2:
                    continue

                code_col = choose_code_col(table)
                if code_col is None:
                    continue

                # sanity-check (мягкий): таблица не отбрасывается, только помечается как сомнительная
                hits = 0
                for test_row in table[1:11]:
                    if test_row and code_col < len(test_row):
                        if parse_code_cell(test_row[code_col] or ""):
                            hits += 1
                table_suspicious = hits < 2

                desc_col = code_col - 1 if code_col - 1 >= 0 else None

                for r_i, row in enumerate(table[1:], start=2):
                    if not row or code_col >= len(row):
                        continue

                    code_cell = row[code_col] or ""
                    desc_cell = (row[desc_col] or "") if (desc_col is not None and desc_col < len(row)) else ""

                    # ✅ страховка row_scan: только если таблица сомнительная, и строго по строке
                    codes_row = set()
                    row_text = None
                    if table_suspicious:
                        row_text = " ".join([c for c in row if c])
                        codes_row = extract_codes_any_4_6_10(row_text)
                        codes_row = filter_short_codes_if_covered_by_10(codes_row)

                    for c in codes_row:
                        add_code_to_rules(c, exact=exact, prefix_objects=prefix_objects)
                        page_found_any = True
                        debug_hits.append({
                            "page": page_i, "table": t_i, "row": r_i,
                            "kind": "code_row_scan",
                            "value": c,
                            "rawCell": row_text,
                            "descCell": desc_cell
                        })

                    # Основной разбор ячейки кода
                    items = parse_code_cell(code_cell)

                    for kind, value in items:
                        if kind == "prefixObj":
                            p = value["prefix"]
                            raw = value.get("raw")
                            if p not in prefix_objects:
                                prefix_objects[p] = {"prefix": p, "raw": raw}
                            else:
                                if prefix_objects[p].get("raw") is None and raw is not None:
                                    prefix_objects[p]["raw"] = raw
                            page_found_any = True
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "prefixObj", "value": prefix_objects[p],
                                "rawCell": code_cell, "descCell": desc_cell
                            })

                        elif kind == "prefix":
                            p = value
                            if p not in prefix_objects:
                                prefix_objects[p] = {"prefix": p, "raw": None}
                            page_found_any = True
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "prefix", "value": {"prefix": p, "raw": None},
                                "rawCell": code_cell, "descCell": desc_cell
                            })

                        elif kind == "exact":
                            exact.add(value)
                            page_found_any = True
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "exact", "value": value,
                                "rawCell": code_cell, "descCell": desc_cell
                            })

                        elif kind == "range":
                            ranges.add((value["from"], value["to"], value["len"], value["mode"], value.get("raw")))
                            page_found_any = True
                            debug_hits.append({
                                "page": page_i, "table": t_i, "row": r_i,
                                "kind": "range", "value": value,
                                "rawCell": code_cell, "descCell": desc_cell
                            })

            # ✅ FALLBACK after tables: если таблицы были, но мы не извлекли НИ ОДНОГО правила из таблиц
            if not page_found_any:
                # 1) extract_text
                txt = page.extract_text() or ""
                codes_any = extract_codes_any_4_6_10(txt)
                codes_any = filter_short_codes_if_covered_by_10(codes_any)

                # 2) words lines построчно (точнее)
                if not codes_any:
                    for line in page_lines_from_words(page):
                        line_codes = extract_codes_any_4_6_10(line)
                        line_codes = filter_short_codes_if_covered_by_10(line_codes)
                        codes_any |= line_codes

                # 3) pdfminer
                codes_any |= extract_codes_any_from_pdfminer_page(pdf_path, page_i)

                # 4) pymupdf
                codes_any |= extract_codes_any_from_pymupdf_page(pdf_path, page_i)

                for c in codes_any:
                    add_code_to_rules(c, exact=exact, prefix_objects=prefix_objects)
                    debug_hits.append({
                        "page": page_i,
                        "table": None,
                        "row": None,
                        "kind": "code_fallback_after_tables",
                        "value": c,
                        "rawCell": None,
                        "descCell": None
                    })

    # ❗ ВАЖНО: exact НЕ удаляем, даже если они покрыты prefix.
    # Иначе теряются точные 10-значные коды.

    # --- post-clean: убрать ложные префиксы (raw=None), которые "появились сами",
    # если уже есть точные 10-значные коды, начинающиеся с этого префикса.
    # Это лечит кейс: "3306 10 000 0" -> exact=3306100000, но где-то отдельно вылезает "3306".
    exact_list = [c for c in exact if len(c) == 10]

    # считаем, сколько exact начинается с каждого 4/6 префикса
    cover4 = {}
    cover6 = {}
    for c in exact_list:
        p4 = c[:4]
        p6 = c[:6]
        cover4[p4] = cover4.get(p4, 0) + 1
        cover6[p6] = cover6.get(p6, 0) + 1

    # пороги: для 4-значного префикса достаточно 1 попадания (как в 3306),
    # для 6-значного можно тоже 1
    TH4 = 1
    TH6 = 1

    drop = []
    for p, obj in prefix_objects.items():
        # Если префикс задан как "из ####" -> это настоящее правило, не трогаем
        if obj.get("raw") is not None:
            continue

        if len(p) == 4 and cover4.get(p, 0) >= TH4:
            drop.append(p)
        elif len(p) == 6 and cover6.get(p, 0) >= TH6:
            drop.append(p)

    for p in drop:
        prefix_objects.pop(p, None)

    out = {
        "source": "EEC registry — robust parser (tables + words + fallbacks), 4/6/10 aware",
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "rules": {
            "prefixObjects": sorted(prefix_objects.values(), key=lambda x: x["prefix"]),
            "exact": sorted(exact),
            "ranges": [
                {"from": a, "to": b, "len": L, "mode": mode, "raw": raw}
                for (a, b, L, mode, raw) in sorted(ranges)
            ],
        },
        "stats": {
            "prefixObjects": len(prefix_objects),
            "exact": len(exact),
            "ranges": len(ranges),
        },
        "debug": {
            "note": "Первые 5000 совпадений для проверки откуда взято.",
            "hitsSample": debug_hits[:5000],
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("OK:", out_path, out["stats"])


if __name__ == "__main__":
    main()
# ❗ ВАЖНО: exact НЕ удаляем, даже если они покрыты prefix.
# Иначе теряются точные 10-значные коды.
