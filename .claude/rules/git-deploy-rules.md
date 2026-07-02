# Git & Deploy — Стоп-правила

Дашборд = GitHub Pages, источник `main` / `(root)`. Pages пересобирается автоматически на каждый push в `main`.

## Правила

- **В ресёрч-прогоне коммитить данные прогона:** `findings.json` + `findings-index.json` (производный индекс —
  держать в синхроне, его регенерирует `radar.py`) + `dismissed.json` и `preferences.json`, **если менялись**.
  Не тащить в коммит `index.html` / `README` / прочее без причины. (`findings-index.json`/`dismissed.json` для
  Pages безвредны — статические файлы; дашборд читает только `findings.json`.)
- **НЕ редактировать `findings.json` руками** — все правки через `radar.py` (синхронит индекс, не ломает схему).
- **Пушить в `main`.** В Routine должно быть включено **Allow unrestricted branch pushes** — иначе пуш уйдёт
  в ветку `claude/…`, и Pages НЕ обновится.
- **Сообщение коммита прогона:** `idea-radar: <YYYY-MM-DD> +N новых находок`.
- **Перед коммитом** — `python3 .claude/scripts/radar.py validate` (схема + согласованность индекса → `OK`).

## Проверка деплоя

- `gh api repos/tanchuev/idea-radar/pages/builds/latest --jq .status` → `built`.
- `https://tanchuev.github.io/idea-radar/` и `…/findings.json` отдают `200`.
- Первый деплой Pages может занять несколько минут (шаг `deploy` в workflow `pages-build-deployment`).

## НИКОГДА

- **НИКОГДА `git reset --hard` / `git checkout -- <file>` / `git restore <file>`** — убивает незакоммиченные правки.
- Откат — только точечной правкой через редактор.

## Зачем

Pages обслуживает строго `main`. Пуш в чужую ветку = зелёный статус Routine, но дашборд не обновился —
самая частая «тихая» поломка пайплайна.
