---
name: findings-validate
description: >-
  Валидация и безопасное редактирование findings.json Idea Radar — проверка схемы idea-radar-findings-v2,
  уникальность id, перечисления method/conf/kano/status/ev.t, обязательные оси s{} 1–5 и пруфы ev[], пересчёт count,
  обновление updated, парсинг JSON перед коммитом. Use when — правится findings.json, добавляется/удаляется находка,
  "проверь данные", "валиден ли findings.json", перед коммитом находок.
---

# findings.json — валидация и правка

Перед коммитом любой правки `findings.json` прогнать проверки ниже. Полный контракт — `.claude/rules/findings-data-rules.md`.

> **Правь через `radar.py`, а не руками.** `findings.json` большой (~120K токенов) — не загружай его в контекст
> целиком. Все мутации делает служебный CLI `.claude/scripts/radar.py`, он же держит в синхроне производный
> компактный индекс `findings-index.json` (внешняя память для дедупа) и блоклист `dismissed.json`:
> - `radar.py add <new.json>` — дописать новые находки (id/run/added/count/runs/индекс — автоматически);
> - `radar.py dismiss --ids .. --why ..` / `--taste ..` — перенести «мимо» в `dismissed.json` и убрать из данных;
> - `radar.py merge --keep K --drop a,b` — слить дубли (оставить K→GROWING, вобрать ev);
> - `radar.py set-status` / `set-niche` — сменить статус/нишу; `radar.py get <id>` — посмотреть находку;
> - `radar.py index` — пересобрать индекс; **`radar.py validate`** — проверка ниже одной командой.
>
> Один прогон проверки: `python3 .claude/scripts/radar.py validate` (печатает `OK` или ошибки и согласованность
> индекса). Ручной скрипт ниже оставлен как справочник того, что именно проверяется.

## Чек-лист

1. **JSON валиден:** `python3 -m json.tool findings.json >/dev/null`.
2. **Top-level:** есть `schema` (== `idea-radar-findings-v2`), `updated`, `excluded_niches`, `count`, `findings`.
3. **id:** все уникальны; новый = max+1.
4. **`count` == len(`findings`)**; `updated` = сегодня (`YYYY-MM-DD`), если данные менялись.
5. **Каждый элемент** содержит обязательные поля и валидные перечисления:
   - `method` ∈ {спрос, боль, идея}; `conf` ∈ {high, medium, low}; `kano` ∈ {basic, performance, delight};
     `status` ∈ {NEW, REPEAT, GROWING, IDEA}.
   - `s` — ровно 7 осей (severity, frequency, wtp, reach, gap, trend, ease), каждая — целое 1–5.
   - `ev` — непустой массив; в каждом `q` (цитата), `u` (http/https URL), `t` — непустая строка-метка типа
     источника (свободная: стор, маркетплейс, форум, обсуждение, отзыв, github, статья, новости, обзор, отчёт, …).
6. **Не добавлено лишних top-level полей и score не вычислен руками** (его считает дашборд).

## Скрипт проверки

```bash
python3 - <<'PY'
import json
ENUM = {"method": {"спрос", "боль", "идея"}, "conf": {"high", "medium", "low"},
        "kano": {"basic", "performance", "delight"}, "status": {"NEW", "REPEAT", "GROWING", "IDEA"}}
AXES = {"severity", "frequency", "wtp", "reach", "gap", "trend", "ease"}
data = json.load(open("findings.json"))
errors = []
if data.get("schema") != "idea-radar-findings-v2":
    errors.append("schema != idea-radar-findings-v2")
ids = [finding["id"] for finding in data["findings"]]
if len(ids) != len(set(ids)):
    errors.append("duplicate id")
if data.get("count") != len(data["findings"]):
    errors.append(f"count {data.get('count')} != len {len(data['findings'])}")
for finding in data["findings"]:
    for key, allowed in ENUM.items():
        if finding.get(key) not in allowed:
            errors.append(f"id{finding['id']} {key}={finding.get(key)!r}")
    axes = finding.get("s", {})
    if set(axes) != AXES or not all(isinstance(axes[a], int) and 1 <= axes[a] <= 5 for a in AXES):
        errors.append(f"id{finding['id']} bad s{{}}")
    evidence = finding.get("ev") or []
    if not evidence or any(not str(item.get("q", "")).strip() or not str(item.get("u", "")).startswith("http")
                           or not str(item.get("t", "")).strip() for item in evidence):
        errors.append(f"id{finding['id']} bad ev")
print("OK" if not errors else "ERRORS:\n" + "\n".join(errors))
PY
```

Скрипт печатает `OK` или список конкретных проблем по `id`. Гонять перед каждым коммитом находок.
