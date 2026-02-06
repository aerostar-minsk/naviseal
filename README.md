# seal-checker (template)

Шаблон Next.js приложения для проверки необходимости навигационной пломбы (Этап 1) по коду ТН ВЭД.

## Что внутри

- UI: поле ввода кода → запрос в API → ответ (нужно/не нужно).
- API: `/api/check` читает `data/rules.generated.json`.
- Источники правил:
  - `data/rules.csv` — статичные правила (алкоголь/табак/одежда/обувь/техника/никотин).
  - Реестр ЕЭК (спецэкономмеры) — обновляется автоматически через GitHub Actions (PDF → JSON).

## Быстрый старт (локально)

1) Установи зависимости:
```bash
npm install
python -m pip install pdfplumber
```

2) Сгенерируй правила:
```bash
npm run update:rules
```

3) Запусти:
```bash
npm run dev
```

Открой: http://localhost:3000

## Автообновление на GitHub

В репозитории уже есть workflow:
- `.github/workflows/update-rules.yml`

Он раз в сутки:
- скачивает актуальный PDF реестра ЕЭК,
- парсит его в `data/eec_rules.json`,
- мерджит в `data/rules.generated.json`,
- коммитит изменения.

## Деплой на Vercel

1) Импортируй репозиторий в Vercel
2) Deploy

Vercel будет деплоить обновления после того, как GitHub Actions закоммитит новые правила.
