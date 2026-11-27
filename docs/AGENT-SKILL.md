# AGENT-SKILL — AtlaWire за 5 минут

AtlaWire — read-only CLI к Jira, Confluence, Bitbucket. Никаких записей и переходов:
собирай доказательства, предложение по изменению готовит владелец.

Правила:
- Источник истины по командам и флагам — `atlawire --catalog` и `atlawire <cmd> --help`.
  `--json` принимает каждая команда, кроме `attachment-get` (там `--base64`/`--out`);
  где JSON и так единственный вывод, флаг ничего не меняет.
- Нет типизированной команды под задачу — есть реестр: `atlawire operations` печатает
  317 операций без сети, `atlawire --describe <id>` — аргументы и готовый argv,
  `atlawire read <id> --params '{"k":"v"}'` выполняет одну операцию и печатает
  `{"ok": true, ...}` или JSON-ошибку.
- `api-get`/`api-request` больше не обходят реестр: они вызывают только маршрут, который
  в реестре уже объявлен (`read`- или `admin`-операция того же метода). Незнакомый путь
  отвергается до запроса с сообщением «add it there with evidence that it only reads».
  Причина: denylist сегментов не доказывает, что неизвестный маршрут только читает.
  Если маршрута не хватает — его добавляют в реестр с доказательством, а не обходят.
- `--describe` показывает `scope`: `read` — обычное чтение, `admin` — административный
  маршрут. `read` отказывает админской операции, пока не передан `--allow-admin`; отказ
  происходит до запроса. Оба слоя (реестр и транспорт) проверяют это независимо.
- `--describe` перечисляет каждое query-поле с `source`: `server-wadl` — параметр взят из
  описания API самого сервера (имя и тип оттуда), `atlawire` — объявлен вручную и несёт
  дополнительные ограничения (enum, форма пути, «ровно один из»). Оба вида `read` принимает.
- `--describe` отдаёт `query_documented`: `true` — query-поля объявлены и их имена есть в
  `query`; `null` — query-поверхность ещё не сверена с документацией версии, значит `read`
  отвергнет любой query-параметр. Если нужный параметр документирован, но в `query` его нет,
  вызывайте `atlawire api-get <product> <path> --params '{...}'` по тому же пути, который
  объявлен в реестре, — это один запрос без объявленного набора query-полей и без гарантии
  полноты ответа. Незнакомый путь `api-get` не примет.
- Реестр — это инвентарь, а не доказательство живого чтения. Что реально проверялось на
  стенде, написано в [LIVE-READ-ONLY.md](LIVE-READ-ONLY.md); отсутствие строки там
  означает «не проверено», а не «не работает».
- Переходишь с BBK — [MIGRATION-FROM-BBK.md](MIGRATION-FROM-BBK.md): карта функций,
  отличия по кредам и ретраям, что реально читается на живом стенде.
- Read — один ограниченный ответ; строка поиска это lead, а не доказательство.
- Списочные команды принимают `--limit` (сколько строк вернуть) и `--max-pages`
  (сколько страниц прочитать); оба независимы, обрезка видна в `truncated`/`complete`.
- `--json` — проекция для агента, `--raw` — сырой ответ сервера (где флаг есть).
- Токен не передаётся аргументом и не печатается; ошибки без трейсбека и без токена
  (stderr; у `read` — JSON-конверт).

| Задача | Команда | Что вернётся |
|---|---|---|
| Найти мои задачи | `atlawire mine --limit 20 --json` | JSON-массив коротких строк: `key`, `status`, `type`, `priority`, `assignee`, `updated`, `summary` |
| Статус и название задачи | `atlawire jql "key = DEMO-42" --json` | одна короткая строка с `status` и `summary`; полная карточка — `atlawire issue DEMO-42` (сырой JSON с `fields` + `renderedFields`) |
| Комментарии и история задачи | `atlawire issue-comments DEMO-42 --json`; `atlawire issue-changelog DEMO-42` | `{"rows": [...], "truncated": bool, "total": int}`; changelog — сырой документ `{startAt, maxResults, total, histories}`, одна серверная страница |
| Комментарии страницы Confluence | `atlawire page-comments 12345 --json` | `{"rows": [...], "truncated": bool, "total": int}`; в библиотеке — `confluence.get_page_comments` |
| Версии страницы Confluence | `atlawire page-history 12345 --json`; `atlawire page-version 12345 --version 4 --json` | список версий со сводками; одна запрошенная версия отдельно; в библиотеке — `confluence.get_page_history`, `get_page_version` |
| PR и diff | `atlawire pr DEMO/widgets 7 show`; `atlawire pr-files DEMO/widgets 7 --json`; `atlawire pr DEMO/widgets 7 diff`; `atlawire pr-diff-complete DEMO/widgets 7 --json` | карточка PR; список изменённых файлов; review-view diff (не патч); `{fallback, fallback_reason, diff, files}` с fallback по файлам только при объявленной обрезке |
| Diff по нескольким файлам PR одним вызовом | `atlawire pr DEMO/widgets 7 diff src/a.py src/b.py src/c.py` (в библиотеке — `get_pull_request_diffs`, текст — `get_pull_request_diffs_text`) | один вызов N файлов в порядке аргументов; `--json` — массив объектов diff; из библиотеки один вызов возвращает список |
| Файл в репозитории | `atlawire file DEMO/widgets src/app.py --at main` | точный UTF-8 текст файла на ревизии; список путей — `files` / `ls` |
| Кто менял файл (blame) | `atlawire blame DEMO/widgets src/app.py --at main --json` | массив `{line, author, email, date, commit}` по строкам |
| Поиск по коду | `atlawire grep DEMO/widgets "WidgetService" --at main --glob '*.java' --json`; `atlawire search "WidgetService" --repo DEMO/widgets --json` | `grep`: `GrepResult` с `hits`, `truncated`, `complete`, `status`; `search`: индексные строки с `matchEvidence` (`highlight` — совпадение, `context-only`/`none` — нет; индекс обычно только default-ветка). `grep` читает каждый файл по HTTP и потому линеен по объёму репозитория: на одном стенде полный репозиторий занял ~35 с, тогда как индексный `search` — доли секунды. Для поиска «где встречается» сначала `search`/`repo-search --engine index`, а `grep` — когда нужен точный regex или файл вне индекса; сужайте `--glob`/PATH |
| Поиск по многим репозиториям | `atlawire repo-search "WidgetService" --project DEMO --engine index --json`; `atlawire repo-search "Widget\\w+" --max-repos 10 --engine bytes --json` | `{rows, engine, status, truncated, complete, repositories_scanned, repositories_total, budget}`; `index` — один быстрый поиск плагина, `bytes` — regex по default-веткам, `--fetch archive` — один zip на репозиторий |
| Страница Confluence в Markdown | `atlawire page 12345 --markdown` | Markdown со ссылками, картинками и параметрами макросов; сырой storage XHTML — `--storage`, JSON — по умолчанию |
| Проверить доступ | `atlawire whoami --json` (алиас `atlawire selftest --json`) | по записи на продукт; exit 0 только если все три `ok: true`, иначе 1 |
| Что делать при обрезке | смотри `truncated`, `complete`, `total`, `status` в JSON | `truncated=true` / `complete=false` значит «могло быть больше»: сузь запрос, подними `--limit`/`--max-pages`, для постраничных команд передай следующий `--start`; короткий список без признака обрезки не доказывает полноту |

## Реальные вызовы

```shell
# мои открытые задачи
atlawire mine --limit 20 --json

# сузить поиск по смыслу и обновлению
atlawire jql 'project = DEMO AND text ~ "WidgetService" ORDER BY updated DESC' --limit 20 --json

# regex-поиск по закреплённому коммиту
atlawire grep DEMO/widgets "WidgetService" --at main --glob '*.java' --json

# страница Confluence в Markdown
atlawire page 12345 --markdown

# diff PR для ревью (один файл или несколько за один вызов)
atlawire pr DEMO/widgets 7 diff
atlawire pr DEMO/widgets 7 diff src/app.py src/service.py

# комментарии и версии страницы
atlawire page-comments 12345 --json
atlawire page-history 12345 --json
```

Гарантия: **ни одна объявленная операция не меняет состояние**. `tools/check_read_only.py`
проверяет это двумя способами: метод (только GET плюс три аудированных семантических POST) и
первое слово документации («Returns» — чтение, «Delete»/«Move»/«Create» — нет). Маршруты с
изменяющим GET (например `subtask/move`) в реестр не попадают вовсе.

Ошибка сервера приходит с его собственной причиной — второй строкой после общей, и без
тела ответа, и без токена:

```
HTTP 400: request failed.
Field 'nosuchfield' does not exist or you do not have permission to view it.
```

В библиотеке та же причина лежит в `error.detail`, а `str(error)` остаётся общим, чтобы логи
и трейсбеки не публиковали содержимое ответа. Заполняется только для `400`; остальные 4xx
остаются общими, потому что их причина не про твои входные данные. Слой адаптера
(`api-get`/`api-request`) отдаёт ту же причину в `detail`, а полное тело — программно в
`SdkRequestError.body`; само тело никогда не печатается.

## Exit-коды

`0` — успех; `2` — ошибка валидации/использования (неизвестный флаг, плохой `--params`,
конфликт `--json`/`--raw`); `1` — ошибка чтения (HTTP, транспорт, неполная выдача).
