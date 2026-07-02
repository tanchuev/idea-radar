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
   ├─ ПАМЯТЬ: radar.py summary/check — НЕ читает большой findings.json (экономия контекста)
   ├─ саб-агенты: ресёрч в открытой сети (WebSearch / WebFetch)
   ├─ дописывает находки через radar.py add (+ findings-index.json), коммитит в main
   └─ git push
GitHub Pages пересобирает сайт → index.html подтягивает свежий findings.json
```

**Внешняя память (экономия токенов).** `findings.json` большой (~120K токенов). Прогон НЕ читает его целиком —
это дорого и провоцирует повторы («lost in the middle»). Вместо этого работает через служебный CLI
`.claude/scripts/radar.py`: компактная карта `summary`, дедуп `check` (фразонезависимый концепт-ключ,
без эмбеддингов), деталь по id `get`, мутации `add`/`dismiss`/`merge`/`set-status`. Большой файл правит только
скрипт; он же держит в синхроне производный индекс `findings-index.json`. Детали — `.claude/rules/findings-data-rules.md`.

## Файлы

| Файл | Роль | Кто меняет |
|------|------|-----------|
| `findings.json` | данные находок (schema `idea-radar-findings-v2`) | **только** `radar.py` (Routine / прогон) |
| `findings-index.json` | производный компактный индекс (`idea-radar-index-v1`) — внешняя память для дедупа | **только** `radar.py` (авто-регенерация) |
| `dismissed.json` | реестр «мимо» (`idea-radar-dismissed-v1`) — блоклист отвергнутых идей; удалены из findings | `radar.py dismiss` |
| `.claude/scripts/radar.py` | служебный CLI: summary/check/add/dismiss/merge/get/set-status/validate | человек, редко |
| `index.html` | дашборд, читает findings.json | человек, редко; схему данных НЕ менять |
| `preferences.json` | петля вкуса v2 (👍/👎 + причины → аттракторы/репеллеры/гео) | скилл `idea-radar-taste` / прогон |
| `idea-radar-taste.json` | экспорт отметок из дашборда (`idea-radar-taste-export-v1`), вход для разбора вкуса | дашборд (кнопка «⬇ Экспорт вкуса»), временный |
| `ROUTINE_PROMPT.md` | промпт для облачного Routine | человек |
| `README.md` | инструкция по развёртыванию | человек |

## Инварианты (детали — `.claude/rules/`)

- **Не менять `index.html` и схему `findings.json`.** Дашборд читает фиксированный набор полей;
  поломка схемы = пустой/сломанный дашборд на проде. → `findings-data-rules.md`
- **Правь данные только через `radar.py`, не загружая весь `findings.json` в контекст.** Дедуп —
  `radar.py check` (фразонезависимый концепт-ключ), а не «нормализованный title + niche» (он пропускал
  переформулированные дубли). → `findings-data-rules.md`
- **Каждая находка — с доказательством:** реальный открытый URL + дословная цитата в `ev[]`,
  без выдумок, триангуляция ≥2 источников. → `evidence-rules.md`
- **Diamond Score не считать руками** — дашборд вычисляет его из осей `s{}` (`index.html`, функция
  `diamond()`: веса `gap .18 / reach .16 / trend .16 / wtp .16 / ease .14 / severity .12 / frequency .08`, ×20).
  Проставляй только оси 1–5. (`radar.py` использует ту же формулу для поля `sc` в индексе — производное, в данные не пишется.)
- **Массовость:** ищем продукты, полезные МНОГИМ (массовая B2C/SMB-аудитория), НЕ узкий dev/ML/LLM-тулинг
  (он отвергнут — `dismissed.json` + репеллер в `preferences.json`). → `taste-loop-rules.md`
- **Коммитить в `main` данные прогона:** `findings.json` + `findings-index.json` (+ `dismissed.json`,
  `preferences.json` если менялись). Pages обслуживает main / root. → `git-deploy-rules.md`
- **Петля вкуса:** отметки 👍/👎 + причины из дашборда выгружаются кнопкой «⬇ Экспорт вкуса», скилл
  `idea-radar-taste` превращает их в аттракторы/репеллеры/гео в `preferences.json`; 👎«мимо» дополнительно
  уходят в `dismissed.json` (блоклист) и удаляются из `findings.json`. Прогон этим управляет.
  Гео по умолчанию — РФ ИЛИ локацио-независимое; вкус без реальных отметок НЕ выдумывать. → `taste-loop-rules.md`

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

- `id`, `run`, `added`, `count`, `updated`, запись в `runs` — проставляет `radar.py add` (id = high-water+1,
  не переиспользуется даже после удалений). Руками не считать.
- `demand` — опционально (для метода «спрос»). Оси `s{}` — целые 1–5.
- После любых правок данных: `radar.py validate` (схема + согласованность индекса) перед коммитом.

## Команды

- **Карта памяти (для планирования):** `python3 .claude/scripts/radar.py summary`
- **Дедуп кандидата:** `python3 .claude/scripts/radar.py check "<3–6 слов сути>" --niche "<ниша>"`
- **Дописать находки:** `python3 .claude/scripts/radar.py add new-findings.json --label "<тема>"`
- **Отвергнуть «мимо»:** `python3 .claude/scripts/radar.py dismiss --taste idea-radar-taste.json`
  (или `--ids 1,2 --why "..."`) — убирает из `findings.json`, добавляет в `dismissed.json`.
- **Проверка:** `python3 .claude/scripts/radar.py validate` (схема + согласованность индекса → `OK`).
- **Локальный просмотр дашборда:** `python3 -m http.server` в корне → http://localhost:8000
  (через `file://` браузер блокирует `fetch('findings.json')`).
- **Деплой:** `git add findings.json findings-index.json dismissed.json preferences.json` (что менялось)
  `&& git commit -m "idea-radar: <дата> +N новых находок" && git push origin main` — Pages пересоберётся сам.
- **Статус Pages:** `gh api repos/tanchuev/idea-radar/pages/builds/latest --jq .status` (`built` = готово).

## Язык

Контент (находки, дашборд, промпты) — на русском. Отвечать и писать — на русском.

## Skills

- `idea-radar-research` — запуск ресёрч-прогона (оркестрация саб-агентов → находки → коммит).
- `idea-radar-taste` — разбор вкуса: экспорт 👍/👎 + причины из дашборда → аттракторы/репеллеры/гео → `preferences.json`.
- `findings-validate` — валидация и безопасное редактирование `findings.json`.
