# CLAUDE.md — Idea Radar

## Что это

Idea Radar v2 — система поиска стартап-идей («алмазов»: растущий спрос × слабое предложение).
Облачный **Claude Code Routine** по расписанию запускает ресёрч силами саб-агентов, находит
возможности с доказательствами, дописывает их в `findings.json` и коммитит в `main`.
Статический дашборд (`index.html` на GitHub Pages) читает `findings.json` и рисует карточки,
Diamond Score и scatter-график. **Данные отделены от вида.**

- **Дашборд:** https://tanchuev.github.io/idea-radar/
- **Routine docs:** https://code.claude.com/docs/en/routines
- **Claude Code on the web:** https://code.claude.com/docs/en/claude-code-on-the-web

## Архитектура

```
Routine (облако Anthropic, по расписанию)
   ├─ клонирует репозиторий
   ├─ саб-агенты: ресёрч в открытой сети (WebSearch / WebFetch)
   ├─ дописывает findings.json и коммитит в main
   └─ git push
GitHub Pages пересобирает сайт → index.html подтягивает свежий findings.json
```

## Файлы

| Файл | Роль | Кто меняет |
|------|------|-----------|
| `findings.json` | данные находок (schema `idea-radar-findings-v2`) | **только** Routine / ресёрч-прогон |
| `index.html` | дашборд, читает findings.json | человек, редко; схему данных НЕ менять |
| `preferences.json` | петля вкуса (👍/👎 → ниши/методы) | оркестратор / ручной экспорт |
| `ROUTINE_PROMPT.md` | промпт для облачного Routine | человек |
| `README.md` | инструкция по развёртыванию | человек |

## Инварианты (детали — `.claude/rules/`)

- **Не менять `index.html` и схему `findings.json`.** Дашборд читает фиксированный набор полей;
  поломка схемы = пустой/сломанный дашборд на проде. → `findings-data-rules.md`
- **Каждая находка — с доказательством:** реальный открытый URL + дословная цитата в `ev[]`,
  без выдумок, триангуляция ≥2 источников. → `evidence-rules.md`
- **Diamond Score не считать руками** — дашборд вычисляет его из осей `s{}` (`index.html`, функция
  `diamond()`: веса `gap .18 / reach .16 / trend .16 / wtp .16 / ease .14 / severity .12 / frequency .08`, ×20).
  Проставляй только оси 1–5.
- **Коммитить только `findings.json` в `main`** (Pages обслуживает main / root). → `git-deploy-rules.md`

## Схема находки (`findings.json`)

Top-level: `schema`, `updated` (YYYY-MM-DD), `excluded_niches`, `count`, `findings[]`.

Элемент `findings[]`:

```json
{
  "id": 23,
  "niche": "...",
  "method": "спрос | боль | идея",
  "conf": "high | medium | low",
  "kano": "basic | performance | delight",
  "status": "NEW | REPEAT | GROWING | IDEA",
  "title": "...", "segment": "...", "jtbd": "...", "pain": "...",
  "demand": "...",
  "existing": "...", "idea": "...",
  "s": {"severity": 3, "frequency": 5, "wtp": 3, "reach": 4, "gap": 4, "trend": 3, "ease": 2},
  "ev": [{"q": "дословная цитата", "u": "https://...", "t": "стор | форум | отзыв | github | статья | новости | обзор | отчёт"}]
}
```

- `id` = (максимальный существующий id) + 1, уникальный.
- `demand` — опционально (для метода «спрос»). Оси `s{}` — целые 1–5.
- После правок: обнови `count` (= длине `findings`) и `updated`; проверь валидность JSON парсингом.

## Команды

- **Локальный просмотр дашборда:** `python3 -m http.server` в корне → http://localhost:8000
  (через `file://` браузер блокирует `fetch('findings.json')`).
- **Проверка JSON:** `python3 -m json.tool findings.json >/dev/null && echo OK`
- **Деплой:** `git add findings.json && git commit -m "idea-radar: <дата> +N новых находок" && git push origin main`
  — Pages пересоберётся сам.
- **Статус Pages:** `gh api repos/tanchuev/idea-radar/pages/builds/latest --jq .status` (`built` = готово).

## Язык

Контент (находки, дашборд, промпты) — на русском. Отвечать и писать — на русском.

## Skills

- `idea-radar-research` — запуск ресёрч-прогона (оркестрация саб-агентов → находки → коммит).
- `findings-validate` — валидация и безопасное редактирование `findings.json`.
