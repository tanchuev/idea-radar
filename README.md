# Idea Radar — облачная версия (Routine + дашборд из любого места)

Этот бандл переносит Idea Radar в облако: исследование запускает **Claude Code Routine** на инфраструктуре Anthropic (работает с закрытым ноутбуком), а дашборд хостится статически и открывается по ссылке с любого устройства.

## Что внутри

- `index.html` — дашборд. Читает данные из `findings.json` (данные отделены от вида).
- `findings.json` — данные находок (22 шт. на старте). Это единственный файл, который обновляет Routine.
- `ROUTINE_PROMPT.md` — промпт, который вставляется в Routine.
- `preferences.json` — память твоих отметок 👍/👎 (петля обратной связи).
- `README.md` — этот файл.

## Архитектура

```
Routine (облако Anthropic, по расписанию)
   ├─ клонирует этот репозиторий
   ├─ запускает саб-агентов: ресёрч в открытой сети
   ├─ обновляет findings.json и коммитит его в main
   └─ git push
GitHub Pages пересобирает сайт
   └─ index.html подтягивает свежий findings.json
Ты открываешь https://<твой-логин>.github.io/idea-radar/ с телефона/любого компа
```

## Шаг 1. Залить репозиторий на GitHub

1. Создай новый репозиторий на GitHub, например `idea-radar` (можно приватный — для Pages нужен публичный или платный план с приватными Pages).
2. Залей в него все файлы из этого бандла (корень репозитория):
   ```
   git init
   git add .
   git commit -m "Idea Radar: initial"
   git branch -M main
   git remote add origin https://github.com/<твой-логин>/idea-radar.git
   git push -u origin main
   ```

## Шаг 2. Включить GitHub Pages (дашборд по ссылке)

В репозитории: **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main` / `(root)` → Save**.
Через минуту дашборд будет доступен по адресу `https://<твой-логин>.github.io/idea-radar/` — открывается с любого устройства.

## Шаг 3. Создать облачный Routine

Требуется план **Pro, Max, Team или Enterprise** с включённым **Claude Code on the web**.

1. Открой **claude.ai/code/routines** → **New routine** (или в Desktop-приложении: **Routines → New routine → Remote**).
2. **Name:** Idea Radar.
3. **Instructions:** вставь весь промпт из `ROUTINE_PROMPT.md`. Выбери модель.
4. **Repositories:** добавь свой репозиторий `idea-radar`.
5. **Environment:** открой настройки среды и поставь **Network access = Full** (ресёрчу нужен широкий доступ в сеть; на «Trusted» большинство сайтов будут блокироваться с 403). При желании сузишь домены позже.
6. **Permissions:** включи **Allow unrestricted branch pushes** для репозитория — чтобы Routine коммитил `findings.json` прямо в `main` (иначе он пушит в ветку `claude/…`, и Pages не обновится).
7. **Trigger:** Schedule → выбери **Weekdays** или **Daily** (минимальный интервал — раз в час; кастомный cron — через `/schedule update` в CLI).
8. **Connectors:** оставь только нужные (можно убрать все — ресёрч идёт через WebSearch/WebFetch).
9. **Create** → на странице Routine нажми **Run now**, чтобы проверить первый прогон.

## Шаг 4. Проверить

- После прогона открой сессию Routine и убедись, что он реально нашёл находки и закоммитил `findings.json` (зелёный статус = сессия завершилась без инфра-ошибки, но НЕ гарантия, что задача выполнена — посмотри транскрипт).
- Обнови страницу Pages — дашборд покажет новые карточки.

## Дополнительно

- **Запуск откуда угодно по кнопке/из телефона:** добавь Routine ещё и **API-триггер** (Edit routine → Add trigger → API), получишь URL + токен и сможешь дёргать прогон обычным `curl`/шорткатом с телефона.
- **Лимиты:** research preview; есть суточный лимит запусков Routine, расход идёт из лимитов твоего плана. Текущие лимиты — на странице routines.
- **Дашборд локально:** `index.html` тянет `findings.json` через fetch, поэтому локально открывай через http-сервер (`python3 -m http.server`), а не двойным кликом (file:// блокирует fetch). На GitHub Pages всё работает само.
- **Петля вкуса:** отметки 👍/👎 в дашборде сейчас хранятся в браузере (localStorage). Чтобы они влияли на облачный отбор — переноси их в `preferences.json` репозитория (ручной экспорт или отдельная мини-интеграция; могу доделать по запросу).

## Связанная документация Anthropic

- Routines: https://code.claude.com/docs/en/routines
- Claude Code on the web (облачная среда, доступ к сети): https://code.claude.com/docs/en/claude-code-on-the-web
- Хостинг Agent SDK (если захочешь полностью своё облако): https://docs.claude.com/en/docs/agent-sdk/hosting
