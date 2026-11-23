# INDEX — что умеет AtlaWire

AtlaWire — CLI и Python-библиотека **только для чтения** к self-hosted Jira, Confluence и
Bitbucket (включая старые Server/Data Center). Пишущих операций, выполнения переходов,
ограниченного read-only REST-слоя (`api-get`/`api-request`: только неадминистративные
GET и четыре документированных read-only POST) и MCP в пакете нет: агент читает и
применение изменений остаётся за владельцем (см. [DEFERRED-WRITES.md](DEFERRED-WRITES.md)).

Проверка доступа: `atlawire whoami --json` (алиас `atlawire selftest`). Живые проверки —
в [LIVE-READ-ONLY.md](LIVE-READ-ONLY.md) и каталоге `checks/`.

## Установка и запуск

Нужен CPython 3.15. Из корня репозитория:

```shell
python -m pip install --user -e .
atlawire --help
```

Пакет не опубликован; ставится редактируемо из этого checkout. Если `atlawire` не в PATH:

```shell
C:/Python315/python.exe -P -B -m atlawire --help
```

`-P` не подмешивает checkout в `sys.path`, `-B` не пишет `__pycache__`.

## Учётки

По умолчанию читается тот же per-user файл, что у BBK: `~/.config/atlassian/credentials.json`
(или путь из `BBK_CREDENTIALS`). Используется только пара выбранного продукта
`<product>_url` / `<product>_token`; BBK не импортируется, чужие продукты не подставляются.

`--token-from-env` переключает на env-режим: `ATLAWIRE_<PRODUCT>_URL` и
`ATLAWIRE_<PRODUCT>_TOKEN`, файл не открывается. Токен никогда не передаётся аргументом и не
печатается; ошибки не содержат ни токена, ни тела ответа.

## Из чего состоит CLI

88 видимых команд (проверено `atlawire --catalog`). Команды плоские — `atlawire issue`,
`atlawire pr`, `atlawire page`, без группировки по продуктам. Группы по смыслу:

| Группа | Команды | Что дают |
|---|---|---|
| Обнаружение без сети | `--catalog`, `--describe <id>`, `operations`, `read-operation` | каталог команд и операций; описание одной; разрешённые чтения |
| Канонический read | `read <id> --params '{"k":"v"}'` | один зарегистрированный GET с JSON-конвертом |
| Удостоверение | `whoami`, `selftest` | доступ ко всем трём продуктам одним вызовом |
| Межпродуктовый поиск | `find "<term>" [<term>...]` | Confluence + Jira + Bitbucket за один вызов |
| Bitbucket | `projects`, `repos`, `project`, `repository`, `find-repos`, `search`, `grep-repo`/`grep`, `files`, `ls`, `file`, `blame`, `branches`, `branch`, `commits`, `commit`, `commit-changes`, `commit-diff`, `tags`, `tag`, `last-modified`, `scan-extension`/`scan`, `pr`, `pr-files`, `pr-comments`, `prs`, `my-prs`, `pr-merge-status`, `pr-diff-complete`, `pr-review`, `attachment-get`, `default-branch`, `repo-changes`, `commit-comments`, `commit-comment`, `repo-participants`, `repo-forks`, `related-repos` | код, история, PR и diff, ревью, инвентаризация |
| Jira | `jql`, `mine`, `issue`, `issue-comments`, `issue-changelog`, `issue-worklogs`, `issue-remote-links`, `issue-votes`, `issue-watchers`, `issue-subtasks`, `issue-comment`, `issue-worklog`, `issue-properties`, `issue-property`, `issue-link`, `statuses`, `transitions`, `jira-me`, `jira-priorities`, `jira-resolutions`, `jira-issue-types`, `jira-status-categories`, `jira-projects`, `jira-users`, `jira-author-comments`, `jira-edit-meta`, `jira-create-meta`, `jira-transition-fields` | поиск задач, карточки, комментарии и история, метаданные |
| Confluence | `page`, `cql`, `spaces`, `space`, `space-content`, `children`, `page-attachments`, `page-comments`, `page-labels`, `page-history`, `page-version`, `page-url`, `convert-body` | страницы, поиск, вложения и комментарии |
| SDK-путь | `api-get`, `api-request` | стандартные неадминистративные `/rest/` чтения через `atlassian-python-api==5.0.5` |

Подробности контракта вывода (`--json` / `--raw` / `--fields` / `--expand`, `truncated` /
`complete` / `total`, exit-коды) — в [AGENT-QUICKSTART.md](AGENT-QUICKSTART.md). Готовые
сценарии «задача → команда» — в [AGENT-SKILL.md](AGENT-SKILL.md).

## Где смотреть операции

Операции — это зафиксированные в реестре чтения с известным методом и путём; вызывающий не
может подставить URL, метод, заголовок или произвольный query.

| что | команда | что вернёт |
|---|---|---|
| все команды и их параметры | `atlawire --catalog` | один JSON: 88 команд, типы/дефолты/envvars и 3 канонические операции |
| все зарегистрированные операции | `atlawire operations` | JSON-массив 202 записей (192 из `manifest.json` + 51 встроенная, после дедупликации по маршруту) |
| одна операция | `atlawire --describe <id>` | описание, `command` и готовый `example.argv` |
| выполнить операцию | `atlawire read <id> --params '{"k":"v"}'` | JSON-конверт `{"ok": true, "product": ..., "data": ...}` |
| совместимый одиночный GET | `atlawire read-operation <id> --params '{"k":"v"}'` | сырой JSON ответа |

`--catalog` и `operations` не читают файл учёток и не ходят в сеть. Канонические (агентские)
операции: `bitbucket.repository.get`, `confluence.space.get`, `jira.project.get`.

## Живые проверки

| что | где | как запускать |
|---|---|---|
| девятипроверочный гейт по трём продуктам | `checks/live_read_only.py` | `python -B checks/live_read_only.py --live` (нужны fixture-переменные из [LIVE-READ-ONLY.md](LIVE-READ-ONLY.md)) |
| End-to-end CLI и параметрная матрица | `checks/e2e_param_matrix.py`, `checks/e2e_param_matrix_rest.py`, `checks/e2e_bbk_*.py`, `checks/e2e_semantic_live.py` | по гейтам `ATLAWIRE_*_LIVE=1` / `--live`; см. заголовки файлов |
| отчёт последнего живого прогона | `checks/e2e_param_matrix_report.md` | читать; содержит дату, коммит и CAP/GAP |
| офлайн-набор | `tests/` | `C:/Python315/python.exe -B -m pytest -p no:cacheprovider -q tests` |

Живые проверки не входят в офлайн-набор и запускаются только на согласованном стенде с
read-only учёткой. Отсутствие строк не доказывает отсутствие данных: лимит, права, индекс
или бюджет страниц могли закончиться раньше.

## Python-библиотека

Публичные модули: `atlawire.bitbucket` (41 функция), `atlawire.jira` (33),
`atlawire.confluence` (17), `atlawire.operations` (5), `atlawire.sdk` (6),
`atlawire.http` (сессии и транспорт), `atlawire.repo_scan` (2), `atlawire.repo_grep` (1),
`atlawire.identity` (1), `atlawire.federated` (1), `atlawire.facade.AtlaWire`. Полный
справочник сигнатур, REST-маршрутов и лимитов — [API.md](API.md).

## Документация

| файл | о чём |
|---|---|
| [AGENT-QUICKSTART.md](AGENT-QUICKSTART.md) | как запускать, контракт вывода, рецепты по продуктам |
| [AGENT-SKILL.md](AGENT-SKILL.md) | короткая таблица «задача → команда → что вернётся» |
| [API.md](API.md) | справочник функций Python-API по модулям |
| [LIVE-READ-ONLY.md](LIVE-READ-ONLY.md) | как проверять живой стенд только на чтение |
| [RESEARCH-COVERAGE.md](RESEARCH-COVERAGE.md) | что заменяет BBK, а что нет |
| [DEFERRED-WRITES.md](DEFERRED-WRITES.md) | исторический справочник пишущих операций BBK (в AtlaWire их нет) |
| [FEEDBACK.md](FEEDBACK.md) | шаблон отчёта о практических блокерах |
| [../README.md](../README.md), [../CHANGELOG.md](../CHANGELOG.md) | обзор проекта и история изменений |
