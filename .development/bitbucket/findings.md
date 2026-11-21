# Bitbucket Server 5.10 — проверенные особенности

Всё ниже подтверждено запросами к `https://git.platform-s.com` (5.10.0, build 5010000),
2026-11-18. Справочник по эндпоинтам — `rest-5.10/` (125 эндпоинтов, 42 файла).
Исследование MCP vs библиотека vs REST с замерами — `research.md`.

## Diff: только JSON

`GET …/pull-requests/{id}/diff` **не отдаёт текст**: `Accept: text/plain`, `text/*`,
`application/x-diff`, `application/x-patch`, суффикс `.diff`, `/commits/{hash}/diff` и
`/diff/{path}?since=&until=` — все возвращают **406 Not Acceptable**. 200 — только с
`application/json` (или без Accept).

Поэтому unified diff рендерится на клиенте: `bbk.pr_diff()` / `bbk.md.render_diff()`.
Сжатие на PR #192 (6 файлов): JSON по умолчанию 80 820 Б → JSON с
`withComments=false&contextLines=2&whitespace=ignore-all` 43 193 Б → unified diff 12 848 Б.

Если сервер обрезал ответ (`truncated: true`), `pr_diff` сам переходит на по-файловые запросы;
проверено, что `pr_diff(..., paths=[...])` даёт байт-в-байт тот же текст, что и один общий запрос.

## `/raw/{path}`: 500 при Accept: application/json

Файл отдаётся только как `text/plain`. `bbk.file_at` и `bbk.pr_file` передают нужный Accept;
при JSON-запросе сервер отвечает 500, а не 400 — легко принять за поломку сервера.

## `/changes` возвращает `values[]`, а не `diffs[]`

У `/pull-requests/{id}/changes` структура `{fromHash, toHash, values[]}`, где `values[i]` —
`{path, type, nodeType, …}`, и **`path` — объект** `{components, parent, name, toString}`.
Парсер, общий с `/diff`, молча даёт 0 файлов. `bbk.pr_files` нормализует это в `{path, type, node}`.

## Поиск: кросс-проектный только через POST

`POST /rest/search/latest/search` с телом
`{"query": "...", "entities": {"code": {"start": 0, "limit": 100}}}`; `GET` → 405.
Ограничения: default branch, только проиндексированные файлы, точные термы, `count` — файлы.
Индекс отдаёт максимум **999 файлов** на запрос.

- `ext:py` — **0 результатов**, поле не поддерживается. `path:*.py` ведёт себя как текст
  (возвращает `.yml`). Ищите по содержимому: `python`, `"def "`, имя класса.
- Диапазон/склейка: `python` → 280 файлов, `"def "` → 3 759 (на момент проверки).
- MCP `search_code` жёстко ограничен проектом (в схеме обязателен `workspace`), поэтому
  глобальные вопросы решаются только POST'ом без `project:`.

## Параметры, которые «не работают»

`?withAttributes=false` на `/pull-requests` **не меняет размер** ответа: 8 938 Б и с ним, и без.
Экономию дают `withComments=false`, `contextLines`, `whitespace` на `/diff` и клиентское сжатие
(`bbk.md.compact`: минус `links`, `avatarUrl`, `permittedOperations`, `properties` …).

## Инвентаризация репозиториев

Поиска по расширению нет, поэтому «где вообще есть Python» — это обход
`projects → repos → /files`: 40 проектов, 551 репозиторий, ~74 с, ~600 вызовов при 8 потоках.
Результат: 19 репозиториев в 13 проектах. Функция: `bbk.repos_with_extension(".py")`.
Часть репозиториев упирается в лимит страницы 1000 файлов — таких было 16.

## Прочее, что пригодилось

- PR и комментарии изменяются с обязательным `version` из предыдущего GET, иначе 409.
- `get_pull_requests()` / `project_list()` / `repo_all_list()` в atlassian-python-api 5.0.5
  возвращают **генераторы** (обёртка `list()`), а `search_code(team, …)` — сигнатура Cloud,
  на Server она бесполезна.
- Пользователь не найден/репозитория нет → 404; нет прав → 403; формат не поддержан → 406.
  Тело ошибки не печатаем: прокси может вернуть заголовки запроса.

## Дополнения (проверено 2026-11-18, вторая итерация)

**Архив репозитория: Accept решает всё.** `GET …/archive?format=zip` отдаёт 200 только при
`Accept: application/octet-stream` (или `*/*`, или без заголовка). На `application/zip` и
`application/x-zip-compressed` — **406**. Поэтому `bbk.repo.grep` использует octet-stream,
а при недоступности архива переходит на по-файловую докачку (fanout).

**Merge-коммиты пустые.** У merge-коммита (`Merge pull request #192 …`) `/commits/{id}/changes`
и `/commits/{id}/diff` возвращают 0 файлов и 0 байт; у обычного коммита — 3 файла и 4 119 Б.
Проверки на merge-коммите вакуумны: selftest специально ищет коммит с изменениями.

**Dashboard вместо «списка моих PR».** `/rest/api/1.0/pull-requests?role=AUTHOR` → 404.
Работает `/rest/api/1.0/dashboard/pull-requests`:
`state` только `OPEN|MERGED|DECLINED` (`ALL` → 400), `role=AUTHOR|REVIEWER`,
`order=NEWEST|OLDEST`, `participantStatus=UNAPPROVED|NEEDS_WORK|APPROVED`.
Обёртка — `bbk.my_prs(state, role=…)`.

**Уволенные пользователи скрыты из `/users`.** `GET /users` вернул 172 записи, все `active=true`;
уволенный виден только в `active=false` внутри PR (`reviewers`/`participants`) — так и был найден
`t.dolnikova` в старых PR проекта TP. Фильтровать «кто уволен» через список пользователей нельзя.

**grep: три движка у MCP, два у нас.** MCP держит тёплый snapshot (кэш 256 МБ по умолчанию),
потоковый архив и fanout. В bbk — архив + fanout: агент делает одиночные запросы, кэш дал бы
устаревание. Полезное, что перенесено: режим листинга без `query`, бюджет времени (`timeout_s`),
пропуск строк длиннее 16 КиБ, флаг `partial` в результате.

**Confluence: комментарий — не `/child/comment`.** `POST /rest/api/content/{id}/child/comment`
отвечает **405**; работает `POST /rest/api/content` с `{"type":"comment","container":{...},
"body":{"storage":{...}}}`.

> Bitbucket MCP удалён 2026-11-18: все его инструменты и обходные пути перенесены в `bbk`
> (проверка — `tests/coverage_mcp.py`, 25/25). Старая утилита `bb-search.*` и патч
> `~/.local/opt/bitbucket-mcp-diff-fix` также удалены; поиск по всем проектам — `bbk search`.
