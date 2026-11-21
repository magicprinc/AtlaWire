# INDEX — что умеет bbk

Карта возможностей по трём сервисам. Первый столбец — английское имя функции/команды,
второй — что это даёт по-русски. Подробности — в файлах рядом (`auth.md`, `logs.md`,
`bitbucket/`, `jira/`, `confluence/`). Проверка живости: `bbk selftest`.

Вызов: `from bbk import …` или `bbk <команда>` (лаунчер в `~/.local/bin`, Bash — `bbk`).

---

## Bitbucket Server 5.10

### Чтение

| capability | что делает и что даёт |
|---|---|
| `search_code` / `bbk search` | Кросс-проектный поиск по коду через индекс Bitbucket. Единственный способ спросить «где это используется во всех проектах»: MCP так не умеет (ограничен проектом), суффикс `--project/--repo` сужает область. Лимит — файлы, окно индекса 999. |
| `projects` / `bbk projects` | Список доступных проектов: ключ, имя, публичность. С него начинается любая навигация. |
| `repos` / `bbk repos` | Репозитории проекта: slug, имя, состояние. |
| `list_files` / `bbk files` | Все пути файлов репозитория на ветке/коммите. Основа для инвентаризации («где есть .py»). |
| `file_at` / `bbk file` | Текст файла на нужной ветке/коммите. Учитывает квирк 5.10: `/raw` требует `text/plain`, иначе 500. |
| `ls` / `bbk ls` | Содержимое каталога: пути, типы, размеры. Заменяет `list_directory_content` из MCP. |
| `grep` / `bbk grep` | Regex по содержимому репозитория на любой ветке. Скачивает zip-архив и ищет в памяти — один запрос вместо сотни; при недоступности архива докачивает файлы по одному. Без `pattern` — листинг по glob. |
| `grep_ex` | То же с диагностикой: какой движок сработал, сколько файлов просмотрено, `partial` (бюджет времени кончился — результат неполный) и предупреждения. |
| `blame` / `bbk blame` | Автор, дата и коммит по каждой строке файла. Отвечает «кто это написал и когда». |
| `branches` / `bbk branches` | Ветки репозитория с последними коммитами и признаком default. |
| `commits` / `bbk commits` | История коммитов (новые первыми), можно фильтровать по пути и ветке. |
| `commit` | Один коммит целиком: автор, сообщение, родители. |
| `commit_changes` / `bbk commit-changes` | Файлы, изменённые коммитом (порт `get_commit_detail: files`). У merge-коммитов пусто — это нормально. |
| `commit_diff` / `bbk commit-diff` | Unified diff коммита (порт `get_commit_detail: diff`). |
| `pr_commits` | Коммиты, входящие в конкретный PR. |
| `find_repos` / `bbk find-repos` | Поиск репозитория по имени во всех видимых проектах. Заменяет `search_repositories`. |
| `pr` / `bbk pr … show` | Карточка PR: id, версия, состояние, автор, ветки, хеши, ревьюеры, даты. |
| `pr_files` / `bbk pr … files` | Список изменённых файлов. Нормализует квирк 5.10: `/changes` отдаёт `values[]`, а путь — объект. |
| `pr_diff` / `bbk pr … diff` | Unified diff PR. Сервер отдаёт только JSON, поэтому текст рендерится локально; при обрезке автоматически переходит на по-файловые запросы. |
| `pr_file` / `bbk pr … file` | Содержимое файла на стороне PR: `new` — источник (fromRef), `old` — назначение (toRef); чтение из репозитория выбранной стороны на её коммите. |
| `prs` | Список PR репозитория: state OPEN/MERGED/DECLINED/ALL, автор, ветки, дата. Аналог list_pull_requests из MCP, но без ограничения проектом. |
| pr_comments / bk pr … comments | Комментарии ревью: автор, файл, строка, текст. |
| `my_prs` | Мои PR: автор или ревьюер. `state` только OPEN/MERGED/DECLINED (`ALL` сервер не принимает), `role`, `participantStatus`. |
| `review` / `bbk review` | Пакет для ревью PR по одной ссылке: subject, описание, коммиты, файлы с ±, постоянные ссылки на версию файла до/после (`?at=<hash>`), diff, автопроверки (тесты, javadoc, размер и сложность затронутых методов, красные флаги). |
| `pr_compact` | PR без служебных полей (ссылки, аватары, permittedOperations) — для отчётов и экономии контекста. |
| `repos_with_extension` / `bbk scan` | Инвентаризация: в каких репозиториях есть файлы расширения. Дорого (~600 запросов на 551 репозиторий), но другого способа в 5.10 нет. |

### Запись (каждая операция пишется в `logs/`)

| capability | что делает и что даёт |
|---|---|
| `write.pr_comment` | Комментарий в PR. Возвращает id и version — без version удалить нельзя. |
| `write.pr_comment_reply` | Ответ в тред комментария PR. |
| `write.pr_comment_update` | Правка текста комментария (нужна текущая version, иначе 409). |
| `write.pr_comment_delete` | Удаление комментария PR (тоже по version). |
| `write.pr_create` | Создать PR: заголовок, описание, ветки, ревьюеры. |
| `write.pr_update` | Изменить PR; версия подтягивается сама. |
| `write.pr_merge` | Слить PR с выбранной стратегией (merge-commit / squash / fast-forward). |
| `write.pr_decline` | Отклонить PR с сообщением. |
| `write.pr_approve` / `write.pr_unapprove` | Поставить или снять свой approve. |
| `write.branch_create` / `write.branch_delete` | Создать ветку от точки старта / удалить ветку. |
| `write.pr_comment_anchored` | Инлайн-комментарий к строке diff (`path`+`line`, `line_type`) или задача-блокер (`task=True` → severity BLOCKER). |
| `write.attachment_download` / `write.attachment_delete` | Скачать вложение по id / удалить его (удаление пишется в журнал). |

---

## Jira Server 8.22

| capability | что делает и что даёт |
|---|---|
| `jql` / `bbk jql` | Поиск по JQL. Самый частый вход: «что у меня в работе», «что создано за неделю». |
| `jira_rows` | То же, но строки для отчёта: ключ, статус, тип, приоритет, исполнитель, дата, тема. |
| `mine` / `bbk mine` | Мои незакрытые задачи; аргумент — конкретный статус. `statusCategory != Done` закрывает все «завершённые» одним условием. |
| `issue` / `bbk issue` | Задача целиком, включая HTML описания и комментариев (`renderedFields`). |
| `issue_md` | Задача в Markdown: поля карточкой, описание, комментарии. `wiki=True` — компактнее (wiki → md без HTML). |
| `recent_comments` / `bbk comments` | Последние комментарии человека по всему Jira: логин или ФИО (кириллица транслитерируется; неоднозначность — ошибка с логинами), `--days` (окно по дате обновления задачи), `--limit`, `--grep`, `--project`; `--strict` — ошибка вместо предупреждения о неполной выборке; печатает прямую ссылку на комментарий. |
| `transitions` | Доступные переходы статуса задачи: id, действие, целевой статус — чтобы не угадывать имена при смене статуса. |
| `statuses` / `bbk statuses` | Все имена статусов инстанса. Обязательно перед JQL: в этом Jira живут и `In Progress`, и `В работе`, и 50+ других. |
| `jira_me` | Кто мы для Jira (name, displayName, email) — проверка токена. |
| `write.jira_comment` | Комментарий к задаче (wiki-разметка). |
| `write.jira_update_comment` | Правка комментария — фиксируется в журнале как изменение. |
| `write.jira_transition` | Перевести задачу в другой статус (имя или id перехода, необязательный комментарий); пишется в журнал. |
| `write.jira_delete_comment` | Удаление комментария (уборка после проверки). |

---

## Confluence DC

| capability | что делает и что даёт |
|---|---|
| `page` / `bbk page` | Страница целиком: id, title, space, version, ancestors и `body.storage`. |
| `page_storage` | Storage Format (XHTML с `<ac:*>`) — если нужен исходник, а не текст. |
| `page_md` / `bbk page …` | Страница в Markdown: макросы, панели, таблицы, ссылки. `body.view` не запрашивается — в нём UI-мусор. |
| `title` | Заголовок страницы (для отчёта и ссылки). |
| `children` / `bbk children` | Дочерние страницы: id, title, версия. |
| `spaces` / `bbk spaces` | Доступные пространства: ключ, имя, тип. |
| `search_cql` / `bbk cql` | Поиск по CQL: `text ~ "…"`, `space = KEY`, `title ~ "…"`, `ancestor = <id>`. |
| `write.confluence_comment` | Комментарий к странице (создаётся как контент типа `comment` через `POST /rest/api/content`). |
| `write.confluence_delete_comment` | Удаление комментария страницы. |
| `write.confluence_update_page` | Заменить тело страницы, подняв версию (без bump сервер отвечает 409). |

---

## Общее

| capability | что делает и что даёт |
|---|---|
| `BBK_READ_ONLY=1` | Аналог `BITBUCKET_READ_ONLY` у MCP: все пишущие функции отказывают, пока переменная включена. Чтение работает. |
| `idx_search` / `bbk idx "regex"` | Поиск по локальному индексу метаданных (`docs/IDX`): таблицы MSSQL по имени, базы с числом таблиц, проекты Bitbucket с описанием и ссылкой. Без запросов к серверам. |
| `whoami` / `bbk whoami` | Проверка доступа ко всем трём сервисам одной командой: кто мы и живы ли токены. |
| `selftest` / `bbk selftest` | 33 проверки только на чтение: сервисы, поиск, PR, diff, ls, ветки, коммиты, blame, grep, JQL, страница, конвертеры, журнал. Первое, что стоит запускать. |
| `logs` / `bbk logs` | Последние изменения из журнала, с фильтром по тексту. |
| `note` / `bbk note` | Памятка-разбор в `logs/notes.md` (что сломалось, как чинили). |
| `confluence_to_md` | Storage Format → Markdown (конвертер с поддержкой макросов; таблицы остаются pipe-таблицами). |
| `wiki_to_md` | Wiki-разметка Jira → Markdown (дешевле HTML). |
| `html_to_md` | Любой HTML → Markdown (описания Jira, `body.view`). |
| `render_diff` | JSON diff Bitbucket → unified diff (в 5–6 раз меньше токенов). |
| `compact` / `compact_json` | Убрать из JSON ссылки/аватары/служебные поля — компактный отчёт без потери данных. |
| `log_change`, `log_note`, `tail` | Журнал: записать изменение, записать памятку, прочитать последние записи. |
| `credentials`, `service`, `redact`, `Client` | Доступ к токенам (без печати), клиент сервиса, вычищение секретов из текста. |

---

## Команды CLI

| команда | что делает |
|---|---|
| `bbk whoami` | доступ ко всем сервисам |
| `bbk selftest` | самопроверка (только чтение) |
| `bbk search "<query>" [--project K] [--repo K/s] [--limit N] [--all] [--json]` | поиск по коду |
| `bbk projects` / `bbk repos <KEY>` | проекты и репозитории |
| `bbk files <repo> [--at REF]` / `bbk file <repo> <path> [--at REF]` | файлы репозитория |
| `bbk ls <repo> [path] [--at REF]` | каталог |
| `bbk grep <repo> <regex> [--glob] [--path] [--ref]` | поиск по содержимому |
| `bbk blame <repo> <path> [--at]` | авторство строк |
| `bbk branches <repo> [--filter]` | ветки |
| `bbk commits <repo> [--at] [--limit] [--path]` | история |
| `bbk commit-changes <repo> <sha>` / `bbk commit-diff <repo> <sha> [paths…]` | файлы и diff коммита |
| `bbk find-repos <name>` | поиск репозитория |
| `bbk scan [--ext .py]` | инвентаризация по расширению |
| `bbk pr <repo> <id> [show\|files\|diff\|file\|comments]` | всё про PR |
| `bbk review <url\|repo> [--id N] [--root PATH] [--refresh] [--no-diff] [--out FILE]` | пакет для ревью PR (+ обновление истории и индекса) |
| `bbk jql "<JQL>" [--limit] [--json]` / `bbk mine [--status]` | задачи |
| `bbk issue <KEY> [--wiki] [--out FILE]` / `bbk statuses` | карточка и статусы |
| `bbk comments [user] [--days N] [--limit K] [--grep RE] [--project KEY] [--chars N] [--strict] [--json]` | последние комментарии пользователя с прямой ссылкой; `--json` — чистый JSON в stdout, шапка в stderr |
| `bbk page <id\|url> [--html] [--out FILE]` / `bbk spaces` / `bbk cql "<CQL>"` / `bbk children <id>` | Confluence |
| `bbk logs [--tail N] [--grep TEXT]` / `bbk note <title> <body>` | журнал |

---

## Где что лежит

| что | путь |
|---|---|
| документация (эта папка) | `d:/zcache/bbk/docs` = `/d/zcache/bbk/docs` |
| справочник REST 5.10 (125 эндпоинтов) | `docs/bitbucket/rest-5.10/` |
| находки и грабли Bitbucket | `docs/bitbucket/findings.md` |
| исследование MCP vs библиотека vs REST | `docs/bitbucket/research.md` |
| Jira REST/JQL | `docs/jira/api.md` |
| Confluence Storage Format | `docs/confluence/storage.md` |
| токены и PAT | `docs/auth.md` |
| журнал и памятки | `docs/logs.md`, `logs/` |
| ревью PR: пакет, символы, обновление, замечания | `docs/review.md` |
| контрольные проверки | `tests/coverage_mcp.py`, `tests/no_damage_check.py`, `tests/audit_api.py` |
| сводный справочник схемы (MSSQL + Confluence) | `docs/IDX/schema-reference.{json,md}` |
| где репозиторий лежит локально | `bbk local <KEY/slug>` (`docs/local.md`); файлы на диске — `es.exe` (Everything) |
| собрался ли проект в Jenkins / когда последняя сборка | `docs/jenkins.md` — `/view/COMMON/api/json`, `/job/<name>/lastBuild/api/json` |
| последняя версия библиотеки в Maven | `bbk maven group:artifact` (`docs/versions.md`) |
| все наши артефакты в Maven (91, группа com.devinotele) | `docs/IDX/maven-devinotele.json`, обновление `tools/build_maven_index.py` |
| версии каталога против Maven (опубликовано ли) | `python tools/check_catalog_maven.py` (`docs/versions.md`) |
| свежие версии библиотек (локально vs Bitbucket) | `python tools/compare_catalog.py` · разбор — `docs/versions.md` |
| какие топики в Kafka, как читать/искать сообщения | `docs/IDX/kafka-topics.json` (1402 топика), `kcl` / `kafkactl` / kafka-ui API · разбор — `docs/kafka.md` |
| какие subject'ы и стримы в NATS | `docs/IDX/nats.json` (1030 subject, 32 стрима) · разбор — `docs/nats.md` |
| метрики, графики, события (Grafana 11.2.2) | браузерная сессия + `/api/search`, `/api/dashboards/uid` · разбор — `docs/grafana.md` |
| куда сервис реально подключается (БД/Kafka/NATS/Mongo) | `bbk env <сервис>`, `bbk env --addr <host>` · разбор — `docs/dvps.md` |
| письма по теме/тикету (Gmail, read-only) | поиск `mail.google.com/mail/u/0/#search/<запрос>` + reload · разбор — `docs/mail.md` |
| чем занимался коллега вчера/на прошлой неделе | `tools/chat_history.py` (снимки `docs/IDX/chat-dev/`) |
| кто что делает (обзор по людям: чат + Jira) | `tools/who_does_what.py`, таблицы `people_activity` + `jira_status` |
| активные задачи людей и их прогресс (Jira) | `tools/people_status.py`, таблица `jira_status` |
| ежедневный сбор занятости (чат + Jira) | `tools/daily_collect.py` — один прогон, пишет в SQLite |
| кто что делал (задачи из коммитов + статистика) | `tools/collect_commits.py`, `tools/people_report.py`, таблица `people_tasks` |
| занятость коллег: что видно из API по 5 источникам | `docs/colleagues.md` (чат, календарь, коммиты, Jira, people page) |
| кто чем занят сегодня / нарушения статусов | `docs/daily-check.md`, `tools/dev_daily_report.py` (3 правила), `tools/jira_ticket_audit.py` |
| кто чем занят сегодня (кратко) | `docs/daily-check.md`, `tools/jira_ticket_audit.py` |
| обмен между агентами и протокол разногласий | `docs/agent-exchange.md` — exchange, одна претензия на пару, эскалация владельцу |
| один такт агента (чат + exchange) | `tools/tick.py` — джиттер, захват, непрочитанные |
| история чата и обмен между агентами | `chat_messages`, `exchange` в `logs/tech/bbk.db` (`docs/chat-send.md`) |
| отправить уведомление владельцу в Google Chat | `docs/chat-send.md` — пространство FinkLab, только туда |
| рабочие чаты (Google Chat) | поиск по чатам: `chat.google.com/u/0/app/search?q=…` · разбор — `docs/chat.md` |
| Google API из Python (календарь, почта, диск, YouTube) | `bbk gcal`, `bbk gmail` · настройка — `docs/google-api.md` |
| календари коллег / встреча → тикет → коммиты | `docs/calendar-colleagues.md` — что доступно, варианты доступа A–E |
| календарь (встречи) | `bbk cal <тикет>` · настройка — `docs/calendar.md` |
| публичное API (как видят клиенты) | <https://docs.devino.online/0.2.0/ru/> · разбор — `docs/api/public-api.md` |
| копии статей Confluence | `docs/db/` (`eap.md`, `manifest.json`, обновление `tools/refresh_docs.py`) |
| **новому агенту: с чего начать** | [`docs/AGENT-START.md`](AGENT-START.md) — убрать MCP, что использовать, правила |
| какой индекс для какого вопроса (Everything / basemind / codebase-memory / IDX) | `docs/indexes.md` |
| локальные копии репозиториев (526) | `docs/IDX/local-repos.json`, обновление `tools/build_local_index.py` |
| Kafka (test): топики и инструменты | `docs/IDX/kafka-topics.json`, обновление `tools/build_kafka_index.py` |
| NATS: subjects и стримы тестового кластера | `docs/IDX/nats.json`, обновление `tools/build_nats_index.py` |
| подключения DVPS (k8s test/prod) | `docs/IDX/dvps-endpoints.json`, обновление `tools/build_env_index.py` |
| какие БД/NATS/Kafka принадлежат проекту (по стендам) | `docs/project-links.md`, таблицы `project_*` с полем `env` |
| единый справочник: MSSQL + Kafka + NATS в SQLite | `docs/IDX/catalog.db`, сборка `tools/build_catalog.py` |
| локальные индексы (MSSQL + проекты Bitbucket) | `docs/IDX/` (`README.md`, `mssql-index.json`, `bitbucket-projects.{json,md}`) |

---

## Где что смотреть

| вопрос | контур | инструмент |
|---|---|---|
| что видит клиент в API | docs.devino.online (v0.2.0/ru) | справочник, см. `docs/api/public-api.md` |
| как реализовано | Bitbucket | `bbk search`, `bbk grep`, `bbk file` |
| как спроектировано и почему | Confluence | `bbk cql`, `bbk page` |
| кто и когда менял | Jira | `bbk jql`, `bbk mine` |
| что писали в почте | Gmail (read-only, через браузер) | `docs/mail.md` |
| когда обсуждали / встречались | Google Chat и Calendar | поиск по чату (`docs/chat.md`), `bbk cal` |

## Источники и родственные проекты

| проект | что это | как используем |
|---|---|---|
| [pdogra1299/bitbucket-mcp-server](https://github.com/pdogra1299/bitbucket-mcp-server) (npm `@nexus2520/bitbucket-mcp-server`, v4.0.0) | MCP-сервер на TypeScript: 25 инструментов, три движка grep (snapshot/stream/fanout), READ_ONLY-режим, вложения, инлайн-комментарии. Исходники с комментариями — основной источник идей | **Удалён 2026-11-18.** Все 25 инструментов перенесены в `bbk` (`repo_grep.py`, `review.py`, `write.py`); проверка покрытия — `tests/coverage_mcp.py` |
| [avivsinai/bitbucket-cli](https://github.com/avivsinai/bitbucket-cli) (`bkt`, v0.40.2) | CLI на Go + набор agent-правил (`skills/bkt/rules/*.md`): pr/repo/branch/commit/perms/webhook/status | Идеи перенесены: `my_prs` через dashboard, `--dry-run`, компактный TSV-вывод, «документация как скилл». Сам `bkt` остаётся отдельной утилитой; дорабатывать его не стали — он менее богат, чем нужно (см. `docs/bitbucket/findings.md`) |
| [atlassian-python-api](https://atlassian-python-api.readthedocs.io/) ([github](https://github.com/atlassian-api/atlassian-python-api), 5.0.5) | клиентская библиотека для Cloud и DC | Изучена при выборе пути; в `bbk` вызовы прямые через `requests`, потому что библиотека на Server возвращает генераторы и имеет Cloud-сигнатуры. Полезна как справочник по методам |
