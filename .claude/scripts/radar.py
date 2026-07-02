#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar.py — служебный CLI Idea Radar.

Зачем: findings.json вырос до ~120K токенов. Читать его целиком каждый прогон —
дорого по контексту И ненадёжно для дедупа («lost in the middle»: модель не держит
весь блоб в внимании и повторно находит уже известные идеи). Этот скрипт даёт
прогону «внешнюю память»: модель работает с КОМПАКТНЫМ индексом (findings-index.json),
а большой файл правит только через команды этого скрипта — НЕ загружая его в контекст.

Файлы данных (в корне репозитория):
  findings.json        — данные находок (читает дашборд). Схема idea-radar-findings-v2.
  findings-index.json  — производный компактный индекс (схема idea-radar-index-v1).
  dismissed.json       — реестр «мимо» (схема idea-radar-dismissed-v1): идеи, отвергнутые
                         пользователем; их НЕ предлагать снова. Удалены из findings.json.

Команды (python3 .claude/scripts/radar.py <cmd> ...):
  index                        пересобрать findings-index.json из findings.json
  check "<текст>" [--niche N]  показать возможные дубли/совпадения в индексе и dismissed
  add <new.json> [--run ID] [--label "..."]
                               дописать НОВЫЕ находки (id/run/added/count/runs — проставит сам),
                               затем пересобрать индекс. Модель пишет только новые находки.
  dismiss (--ids 1,2 --why "..." | --taste <export.json>)
                               перенести находки из findings.json в dismissed.json (блоклист)
  get <id> [id ...]            показать полные находки по id (progressive disclosure)
  merge --keep K --drop a,b,c  слить дубли: оставить K (status→GROWING, вобрать ev), убрать остальные
  set-niche --ids 1,2 --niche "N"   переименовать нишу у находок (канонизация)
  validate                     проверить схему findings.json (+ согласованность индекса)

Все правки сохраняют формат файла: 2 пробела, ensure_ascii=False, без хвостовой пустой строки.
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FINDINGS = os.path.join(ROOT, "findings.json")
INDEX = os.path.join(ROOT, "findings-index.json")
DISMISSED = os.path.join(ROOT, "dismissed.json")

FINDINGS_SCHEMA = "idea-radar-findings-v2"
INDEX_SCHEMA = "idea-radar-index-v1"
DISMISSED_SCHEMA = "idea-radar-dismissed-v1"

# ---- Diamond Score (точная копия index.html, функция diamond()) ----
W = {"gap": .18, "reach": .16, "trend": .16, "wtp": .16, "ease": .14, "severity": .12, "frequency": .08}
AXES = ("severity", "frequency", "wtp", "reach", "gap", "trend", "ease")


def diamond(s):
    return round((s["gap"] * W["gap"] + s["reach"] * W["reach"] + s["trend"] * W["trend"]
                  + s["wtp"] * W["wtp"] + s["ease"] * W["ease"] + s["severity"] * W["severity"]
                  + s["frequency"] * W["frequency"]) * 20)


# ---- Нормализация текста для концепт-ключа и дедупа (без эмбеддингов) ----
STOP = set("""
и в во на для с со из к ко по за от до без про над под при о об у я мы ты вы он она оно они
а но или либо что чтобы как так это эта этот эти тот та те весь вся все всё кто где когда чем
не ни же ли бы то да нет есть быть был была было были будет если уже еще ещё только лишь даже
их его её им них нас вам них свой своя свои наш ваш этого этом этой этих том тех такой такие
очень более менее много мало нужно надо можно нельзя один одна одни два три раз разные раза
the a an of for to in on with without and or not no is are be by as at from your you we they it
this that these those his her its our their app apps про вместо через между перед после около
""".split())

# короткие, но значимые токены (не выкидывать по длине)
KEEP_SHORT = set("ai llm rag ocr crm pdf csv api gps obd ev ui ux seo kpi p2w pms erp sql pkm".split())

# суффиксы RU для лёгкого стемминга (от длинных к коротким); срезаем, если остаётся >=4 символа
SUFFIXES = ["иями", "ями", "ами", "иях", "ях", "ах", "ость", "ости", "ением", "ение", "ения",
            "ировани", "ование", "ования", "ательн", "ост", "ыми", "ими", "ого", "его", "ому",
            "ему", "ыми", "ой", "ей", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ом", "ем",
            "ах", "ях", "ов", "ев", "ам", "ям", "ую", "юю", "ть", "ся", "ешь", "ишь", "ет", "ит",
            "ут", "ют", "ат", "ят", "ы", "и", "а", "я", "о", "е", "у", "ю"]


def stem(tok):
    if any(c.isdigit() for c in tok):
        return tok
    for suf in SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[:-len(suf)]
    return tok


def tokens(text):
    text = (text or "").lower().replace("ё", "е")
    raw = re.split(r"[^a-zа-я0-9]+", text)
    out = set()
    for t in raw:
        if not t or t in STOP:
            continue
        if len(t) < 3 and t not in KEEP_SHORT and not any(c.isdigit() for c in t):
            continue
        out.add(stem(t))
    return out


def concept_key(finding):
    """Фразонезависимый набор токенов идеи (для дедупа). Источник: title+segment+jtbd+idea+pain.
    Берём ПОЛНЫЙ набор стоп-фильтрованных токенов: индекс не грузится в контекст модели
    (его читает скрипт), поэтому recall важнее размера файла. Сопоставление — overlap-коэффициент,
    знаменатель которого — меньший (обычно короткий запрос), так что богатый ключ только повышает recall."""
    text = " ".join(str(finding.get(k, "")) for k in ("title", "segment", "jtbd", "idea", "pain"))
    return " ".join(sorted(tokens(text)))


def overlap(a, b):
    """Коэффициент перекрытия |A∩B| / min(|A|,|B|) — устойчив к разной длине."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---- I/O с сохранением формата ----
def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        # без хвостовой пустой строки — как в исходных файлах


def today():
    return datetime.date.today().isoformat()


def load_dismissed():
    if os.path.exists(DISMISSED):
        return load(DISMISSED)
    return {"schema": DISMISSED_SCHEMA, "updated": today(), "count": 0, "items": []}


# ---- index ----
def build_index(data):
    items = []
    for f in data["findings"]:
        items.append({
            "id": f["id"],
            "n": f.get("niche", ""),
            "m": f.get("method", ""),
            "st": f.get("status", ""),
            "sc": diamond(f["s"]) if isinstance(f.get("s"), dict) and set(f["s"]) == set(AXES) else None,
            "run": f.get("run", ""),
            "k": concept_key(f),
            "t": f.get("title", ""),
        })
    ids = [f["id"] for f in data["findings"]]
    dismissed = load_dismissed()
    dis_ids = [d.get("orig_id", 0) for d in dismissed.get("items", [])]
    prev = load(INDEX)["max_id"] if os.path.exists(INDEX) else 0
    high_water = max([0] + ids + dis_ids + [prev])
    return {
        "schema": INDEX_SCHEMA,
        "note": "Производный компактный индекс findings.json — внешняя память прогона для дедупа. "
                "Регенерируется radar.py index. Прогон ЧИТАЕТ его вместо большого findings.json. "
                "k=концепт-ключ (норм. токены), t=title, n=niche, m=method, st=status, sc=Diamond Score, run=прогон.",
        "updated": data.get("updated", today()),
        "count": len(items),
        "max_id": high_water,
        "items": items,
    }


def cmd_index(args):
    data = load(FINDINGS)
    idx = build_index(data)
    save(INDEX, idx)
    print(f"index: {idx['count']} находок, max_id={idx['max_id']} → {os.path.relpath(INDEX, ROOT)}")


# ---- check ----
DUP_OV, DUP_JA = 0.5, 0.3  # порог «сильного» дубля


def _rank(cand, ks, niche, item_niche):
    ov, ja = overlap(cand, ks), jaccard(cand, ks)
    score = ov + 0.5 * ja
    if niche and item_niche and (niche.lower() in item_niche.lower() or item_niche.lower() in niche.lower()):
        score += 0.2
    return score, ov, ja


def cmd_check(args):
    cand = tokens(args.text)
    if not cand:
        print("пустой запрос — передай 3–6 ключевых слов сути идеи")
        return
    idx = load(INDEX) if os.path.exists(INDEX) else build_index(load(FINDINGS))

    # dismissed — жёсткий блоклист
    dismissed = load_dismissed()
    dhits = []
    for d in dismissed.get("items", []):
        sc, ov, ja = _rank(cand, set((d.get("k") or "").split()), args.niche, d.get("niche", ""))
        if ov >= DUP_OV or ja >= DUP_JA:
            dhits.append((sc, ov, ja, d))
    dhits.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    if dhits:
        print("⛔ DISMISSED (пользователь отверг — НЕ предлагать, иначе DROP):")
        for sc, ov, ja, d in dhits[:5]:
            print(f"   ов={ov:.2f} jac={ja:.2f}  #{d.get('orig_id')} [{d.get('niche')}] {d.get('title')}")
            if d.get("why"):
                print(f"        причина: {d['why']}")

    ranked = []
    for it in idx["items"]:
        sc, ov, ja = _rank(cand, set(it["k"].split()), args.niche, it.get("n", ""))
        ranked.append((sc, ov, ja, it))
    ranked.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    strong = [r for r in ranked if r[1] >= DUP_OV or r[2] >= DUP_JA]
    if strong:
        print("⚠ ВЕРОЯТНЫЙ ДУБЛЬ (есть в findings.json — ставь REPEAT/GROWING на существующую, НЕ плоди новую):")
        for sc, ov, ja, it in strong[:8]:
            print(f"   ов={ov:.2f} jac={ja:.2f}  #{it['id']} [{it['n']}/{it['m']}/{it['st']}] {it['t']}")
    # всегда показываем ближайших соседей — финальное решение NEW/REPEAT за моделью
    print("· ближайшие существующие (для контроля; overlap-коэффициент по концепт-ключу):")
    shown = {it["id"] for _, _, _, it in strong[:8]}
    for sc, ov, ja, it in ranked[:5]:
        if it["id"] in shown:
            continue
        print(f"   ов={ov:.2f} jac={ja:.2f}  #{it['id']} [{it['n']}/{it['m']}/{it['st']}] {it['t']}")
    if not strong and not dhits:
        print("→ сильных совпадений нет; если соседи выше не про то же — кандидат НОВЫЙ. "
              "Сомнения — radar.py get <id> и сравни вручную.")


# ---- add ----
def _validate_finding(f, where):
    errs = []
    req = ("niche", "method", "conf", "kano", "status", "title", "segment", "jtbd", "pain", "existing", "idea")
    for k in req:
        if not str(f.get(k, "")).strip():
            errs.append(f"{where}: пустое поле {k}")
    enums = {"method": {"спрос", "боль", "идея"}, "conf": {"high", "medium", "low"},
             "kano": {"basic", "performance", "delight"}, "status": {"NEW", "REPEAT", "GROWING", "IDEA"}}
    for k, allowed in enums.items():
        if f.get(k) not in allowed:
            errs.append(f"{where}: {k}={f.get(k)!r} не из {allowed}")
    s = f.get("s", {})
    if not isinstance(s, dict) or set(s) != set(AXES) or not all(isinstance(s.get(a), int) and 1 <= s[a] <= 5 for a in AXES):
        errs.append(f"{where}: s{{}} должен содержать ровно {sorted(AXES)}, целые 1–5")
    ev = f.get("ev") or []
    if not ev or any(not str(e.get("q", "")).strip() or not str(e.get("u", "")).startswith("http")
                     or not str(e.get("t", "")).strip() for e in ev):
        errs.append(f"{where}: ev[] непустой, в каждом q + http(s) u + t")
    return errs


def cmd_add(args):
    data = load(FINDINGS)
    new = load(args.file)
    if isinstance(new, dict):
        new = new.get("findings", new.get("items", []))
    if not isinstance(new, list) or not new:
        sys.exit("add: входной файл должен содержать непустой массив находок (или {findings:[...]})")

    errs = []
    for i, f in enumerate(new):
        errs += _validate_finding(f, f"new[{i}] '{str(f.get('title',''))[:40]}'")
    if errs:
        sys.exit("add ОТМЕНЁН — ошибки в новых находках:\n  " + "\n  ".join(errs))

    # id high-water (не переиспользуем id удалённых/dismissed)
    idx = build_index(data)
    next_id = idx["max_id"] + 1

    run_id = args.run or today()
    # авто-суффикс a/b/c если такой run уже есть
    existing_runs = {r["id"] for r in data.get("runs", [])}
    if run_id in existing_runs and not args.run:
        base = run_id
        for suf in "abcdefghij":
            if base + suf not in existing_runs:
                run_id = base + suf
                break
    added_date = today()

    for f in new:
        f2 = dict(f)
        f2["id"] = next_id
        next_id += 1
        f2.setdefault("run", run_id)
        f2.setdefault("added", added_date)
        # порядок ключей как в существующих находках
        data["findings"].append(f2)

    data["count"] = len(data["findings"])
    data["updated"] = added_date
    data.setdefault("runs", [])
    label = args.label or f"Прогон {run_id}"
    # обновить/добавить запись прогона
    run_rec = next((r for r in data["runs"] if r["id"] == run_id), None)
    if run_rec:
        run_rec["count"] = run_rec.get("count", 0) + len(new)
        if args.label:
            run_rec["label"] = label
    else:
        data["runs"].append({"id": run_id, "date": added_date, "label": label, "count": len(new)})

    save(FINDINGS, data)
    save(INDEX, build_index(data))
    print(f"add: +{len(new)} находок (id {next_id-len(new)}..{next_id-1}), run={run_id}, count={data['count']}")
    print("индекс пересобран. Не забудь validate перед коммитом.")


# ---- dismiss ----
def _dismiss_records(data, pairs, default_run):
    """pairs: list of (finding_dict, why). Возвращает записи для dismissed.json."""
    recs = []
    for f, why in pairs:
        recs.append({
            "orig_id": f["id"],
            "niche": f.get("niche", ""),
            "method": f.get("method", ""),
            "title": f.get("title", ""),
            "k": concept_key(f),
            "why": why or "",
            "from_run": f.get("run", ""),
            "dismissed": today(),
        })
    return recs


def cmd_dismiss(args):
    data = load(FINDINGS)
    by_id = {f["id"]: f for f in data["findings"]}
    pairs = []  # (finding, why)

    if args.taste:
        exp = load(args.taste)
        marks = exp.get("marks", [])
        downs = [m for m in marks if m.get("vote") == "down"]
        for m in downs:
            f = by_id.get(m.get("id"))
            if f:
                pairs.append((f, m.get("why", "")))
            else:
                print(f"  ⚠ id {m.get('id')} (vote=down) нет в findings.json — пропущен")
        print(f"taste: {len(downs)} отметок «мимо», найдено в findings.json: {len(pairs)} "
              f"(👍 up={sum(1 for m in marks if m.get('vote')=='up')} — оставлены)")
    elif args.ids:
        ids = [int(x) for x in str(args.ids).replace(" ", "").split(",") if x]
        for i in ids:
            f = by_id.get(i)
            if f:
                pairs.append((f, args.why or ""))
            else:
                print(f"  ⚠ id {i} нет в findings.json — пропущен")
    else:
        sys.exit("dismiss: укажи --ids 1,2,3 [--why ...] или --taste <export.json>")

    if not pairs:
        print("dismiss: нечего переносить")
        return

    dismissed = load_dismissed()
    seen = {d.get("orig_id") for d in dismissed["items"]}
    new_recs = [r for r in _dismiss_records(data, pairs, None) if r["orig_id"] not in seen]
    dismissed["items"].extend(new_recs)
    dismissed["count"] = len(dismissed["items"])
    dismissed["updated"] = today()

    drop_ids = {f["id"] for f, _ in pairs}
    data["findings"] = [f for f in data["findings"] if f["id"] not in drop_ids]
    data["count"] = len(data["findings"])
    data["updated"] = today()

    save(DISMISSED, dismissed)
    save(FINDINGS, data)
    save(INDEX, build_index(data))
    print(f"dismiss: убрано из findings.json {len(drop_ids)}, в dismissed.json теперь {dismissed['count']}.")
    print(f"findings.count={data['count']}. Индекс пересобран. Эти идеи прогон больше НЕ предложит.")


# ---- get ----
def cmd_get(args):
    data = load(FINDINGS)
    by_id = {f["id"]: f for f in data["findings"]}
    out = [by_id[i] for i in args.ids if i in by_id]
    missing = [i for i in args.ids if i not in by_id]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if missing:
        print(f"# не найдены id: {missing}", file=sys.stderr)


# ---- merge ----
def cmd_merge(args):
    data = load(FINDINGS)
    by_id = {f["id"]: f for f in data["findings"]}
    keep = by_id.get(args.keep)
    if not keep:
        sys.exit(f"merge: keep id {args.keep} не найден")
    drop_ids = [int(x) for x in str(args.drop).replace(" ", "").split(",") if x]
    drops = [by_id[i] for i in drop_ids if i in by_id]
    if not drops:
        sys.exit("merge: ни один drop id не найден")

    # вобрать доказательства из дублей (дедуп по URL, кап 6)
    seen_urls = {e.get("u") for e in keep.get("ev", [])}
    for d in drops:
        for e in d.get("ev", []):
            if e.get("u") not in seen_urls and len(keep["ev"]) < 6:
                keep["ev"].append(e)
                seen_urls.add(e.get("u"))
    # рецидив спроса через прогоны — это сигнал «растёт»
    if keep.get("status") in ("NEW", "REPEAT"):
        keep["status"] = "GROWING"

    rm = set(drop_ids)
    data["findings"] = [f for f in data["findings"] if f["id"] not in rm or f["id"] == args.keep]
    data["count"] = len(data["findings"])
    data["updated"] = today()
    save(FINDINGS, data)
    save(INDEX, build_index(data))
    print(f"merge: оставлен #{args.keep} (status={keep['status']}, ev={len(keep['ev'])}), "
          f"убраны {sorted(rm)}. count={data['count']}.")


# ---- set-niche ----
def cmd_set_niche(args):
    data = load(FINDINGS)
    ids = {int(x) for x in str(args.ids).replace(" ", "").split(",") if x}
    n = 0
    for f in data["findings"]:
        if f["id"] in ids:
            f["niche"] = args.niche
            n += 1
    data["updated"] = today()
    save(FINDINGS, data)
    save(INDEX, build_index(data))
    print(f"set-niche: {n} находок → niche='{args.niche}'. Индекс пересобран.")


# ---- validate ----
def cmd_set_status(args):
    if args.status not in {"NEW", "REPEAT", "GROWING", "IDEA"}:
        sys.exit("set-status: status ∈ {NEW, REPEAT, GROWING, IDEA}")
    data = load(FINDINGS)
    ids = {int(x) for x in str(args.ids).replace(" ", "").split(",") if x}
    n = 0
    for f in data["findings"]:
        if f["id"] in ids:
            f["status"] = args.status
            n += 1
    data["updated"] = today()
    save(FINDINGS, data)
    save(INDEX, build_index(data))
    print(f"set-status: {n} находок → status={args.status} (дедуп-повтор: помечай существующую REPEAT/GROWING).")


def cmd_summary(args):
    """Компактная карта памяти для планирования — БЕЗ загрузки findings.json в контекст."""
    data = load(FINDINGS)
    fs = data["findings"]
    from collections import Counter
    byn = Counter(f.get("niche", "") for f in fs)
    bym = Counter(f.get("method", "") for f in fs)
    byst = Counter(f.get("status", "") for f in fs)
    dismissed = load_dismissed()
    print(f"findings: {len(fs)} | updated: {data.get('updated')} | прогонов: {len(data.get('runs', []))}")
    print(f"методы: {dict(bym)} | статусы: {dict(byst)}")
    print(f"dismissed («мимо», не предлагать): {dismissed.get('count', 0)}")
    print("\nПОКРЫТИЕ ПО НИШАМ (ниша → находок) — приоритезируй наименее покрытые:")
    for n, c in sorted(byn.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {c:>3}  {n}")
    runs = data.get("runs", [])[-6:]
    print("\nПОСЛЕДНИЕ ПРОГОНЫ:")
    for r in runs:
        print(f"  {r['id']}: +{r.get('count')} — {r.get('label','')[:70]}")
    if dismissed.get("items"):
        print("\nОТВЕРГНУТЫЕ ТЕМЫ (dismissed — НЕ предлагать снова):")
        dn = Counter(d.get("niche", "") for d in dismissed["items"])
        for n, c in sorted(dn.items(), key=lambda x: -x[1]):
            print(f"  {c:>3}  {n}")
    print("\nДальше: дедуп кандидата — radar.py check \"<суть>\" --niche <ниша>; "
          "детали по id — radar.py get <id>.")


def cmd_validate(args):
    data = load(FINDINGS)
    errs = []
    if data.get("schema") != FINDINGS_SCHEMA:
        errs.append(f"schema != {FINDINGS_SCHEMA}")
    ids = [f["id"] for f in data["findings"]]
    if len(ids) != len(set(ids)):
        errs.append("дубликаты id")
    if data.get("count") != len(data["findings"]):
        errs.append(f"count {data.get('count')} != len {len(data['findings'])}")
    for f in data["findings"]:
        errs += _validate_finding(f, f"id{f['id']}")
    # согласованность индекса (если есть)
    if os.path.exists(INDEX):
        idx = load(INDEX)
        if idx.get("count") != len(data["findings"]):
            errs.append(f"индекс рассинхронизирован: index.count={idx.get('count')} != {len(data['findings'])} (запусти: radar.py index)")
        if idx.get("max_id", 0) < (max(ids) if ids else 0):
            errs.append("index.max_id меньше max(id) — запусти radar.py index")
    print("OK" if not errs else "ERRORS:\n  " + "\n  ".join(errs))
    if errs:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="Idea Radar служебный CLI (внешняя память + дедуп).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="пересобрать findings-index.json").set_defaults(func=cmd_index)
    sub.add_parser("summary", help="компактная карта памяти для планирования").set_defaults(func=cmd_summary)

    c = sub.add_parser("check", help="найти возможные дубли/совпадения")
    c.add_argument("text")
    c.add_argument("--niche", default="")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("add", help="дописать новые находки")
    a.add_argument("file")
    a.add_argument("--run", default="")
    a.add_argument("--label", default="")
    a.set_defaults(func=cmd_add)

    d = sub.add_parser("dismiss", help="перенести «мимо» в dismissed.json")
    d.add_argument("--ids", default="")
    d.add_argument("--why", default="")
    d.add_argument("--taste", default="")
    d.set_defaults(func=cmd_dismiss)

    g = sub.add_parser("get", help="полные находки по id")
    g.add_argument("ids", nargs="+", type=int)
    g.set_defaults(func=cmd_get)

    m = sub.add_parser("merge", help="слить дубли в одну находку")
    m.add_argument("--keep", type=int, required=True)
    m.add_argument("--drop", required=True)
    m.set_defaults(func=cmd_merge)

    sn = sub.add_parser("set-niche", help="переименовать нишу у находок")
    sn.add_argument("--ids", required=True)
    sn.add_argument("--niche", required=True)
    sn.set_defaults(func=cmd_set_niche)

    ss = sub.add_parser("set-status", help="сменить status у находок (дедуп-повтор → REPEAT/GROWING)")
    ss.add_argument("--ids", required=True)
    ss.add_argument("--status", required=True)
    ss.set_defaults(func=cmd_set_status)

    sub.add_parser("validate", help="проверить схему findings.json").set_defaults(func=cmd_validate)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
