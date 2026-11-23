# AtlaWire: что вызывать, что делает, куда идёт

Справочник для Python-потребителя: по одной записи на каждую публичную функцию модулей
`atlawire.bitbucket`, `atlawire.confluence`, `atlawire.jira` и диспетчера
`atlawire.operations` плюс краткие разделы про `sdk`, `http`, `repo_scan`, `repo_grep`,
`identity`, `federated`. Сигнатуры скопированы из рабочего дерева (`HEAD 53401b1`),
REST-пути — из f-строк, констант и словарей `params`, номера строк — из этих же файлов.

В четырёх основных модулях **96 функций**: Bitbucket 41, Confluence 17, Jira 33,
диспетчер 5. Пометка «нет функции» в разделе про потребителя осталась у **2** пунктов
(`page_storage`, `platform`); `titles` и сырой JQL теперь есть.

Как читать строку:

* **REST** — метод и путь ровно как он строится; `{...}` — аргументы, подставляемые с
  URL-кодированием каждого сегмента по одному разу. Query и заголовки, которые функция
  ставит сама, перечислены здесь же.
* **→** — что реально возвращается: проекция (`TypedDict`/`list[...]`), сырой объект
  сервера (`dict[str, object]`) или строка/байты.
* **Ошибки/лимиты** — только специфичное для функции. Общий транспорт одинаков везде и
  описан ниже.

## Общий транспорт (`src/atlawire/http.py`, `sdk.py`)

* `base_url` проверяется `http.normalize_base_url` (`http.py:135`): только HTTPS; HTTP — лишь
  для `127.0.0.1`/`::1` при `allow_http_loopback=True`; без userinfo, query и fragment;
  завершающий `/` срезается.
* `token` — Bearer-токен (грамматика `[A-Za-z0-9._~+/=-]+`), уходит только в заголовке
  `Authorization`; `Accept: application/json` ставят сессии.
* JSON-транспорт: таймауты `(5, 30)`, редиректы не следуются (3xx — ошибка и тело не
  читается), HTTP 206 отвергается, JSON ≤ 8 MiB после распаковки, текст ≤ 1 MiB, только
  UTF-8, gzip ограничен одним членом.
* `http.bearer_session(token)` (`http.py:193`) — строгая read-сессия; закрывает вызывающий.
  `http.new_session(base_url, token=None, *, follow_redirects=False, trust_env=False,
  timeout=None, allow_http_loopback=False)` (`http.py:153`) — публичная фабрика с явной
  политикой редиректов/env/таймаута; `token=None` даёт сессию без Authorization.
* Списки строятся целиком до возврата: поздний сбой не отдаёт частичный результат. Где
  сервер может молча урезать выдачу, есть отдельная `*_with_metadata`/`*Listing`-функция с
  `truncated`/`complete`.
* Ошибки — `http.AtlaWireError` с необязательными атрибутами
  `product`, `operation`, `category`, `http_status`, `method`, `path`; `category` ∈
  `transport`, `http`, `validation`, `unknown_operation`, `credentials`, `upstream` или `None`.
  Текст ошибки не содержит тела ответа, токена и сырых аргументов.

## Bitbucket (`src/atlawire/bitbucket.py`)

Префикс `_repository_url`: `/rest/api/1.0/projects/{project}/repos/{slug}` (оба значения
URL-кодируются). Страница списка — `limit` ≤ 100, число запросов ограничено `max_pages`
(1..1000, по умолчанию 100); курсор берётся только из `nextPageStart`, конец — по
`isLastPage=True`.

**`list_projects(base_url, *, token, max_pages=100, allow_http_loopback=False) -> list[Project]`** — `bitbucket.py:307`
- REST: `GET /rest/api/1.0/projects`; query `start`, `limit` (по 100).
- → `Project` (`key`, `name`, `public`, `description`, `url` из `links.self`).
- Ошибки/лимиты: `max_pages` 1..1000; битые поля; исчерпание бюджета —
  `AtlaWireError("Bitbucket page limit reached; increase --max-pages.")`.

**`list_repositories(base_url, project, *, token, max_pages=100, allow_http_loopback=False) -> list[Repository]`** — `bitbucket.py:327`
- REST: `GET /rest/api/1.0/projects/{project}/repos`; query `start`, `limit`.
- → `Repository` (`slug`, `name`, `state`, `public`).
- Ошибки/лимиты: `project` должен соответствовать `~?[A-Za-z0-9_][A-Za-z0-9_.-]*`;
  лимиты как у `list_projects`.

**`list_all_repositories(base_url, *, token, start=0, limit=100, max_pages=100, allow_http_loopback=False) -> list[dict[str, object]]`** — `bitbucket.py:346`
- REST: `GET /rest/api/1.0/repos` (все видимые репозитории инстанса); query `start` —
  начальный курсор, `limit` — желаемый размер страницы.
- → сырые объекты репозиториев как есть, включая неизвестные поля; `start` не вычисляется
  из `limit`, каждая нетерминальная страница идёт по своему `nextPageStart`.
- Ошибки/лимиты: исчерпан `max_pages` — ошибка без частичного списка.

**`find_repositories(base_url, name, *, token, limit=25, max_pages=100, allow_http_loopback=False) -> list[RepositoryMatch]`** — `bitbucket.py:404`
- REST: `GET /rest/api/1.0/projects`, затем по каждому проекту
  `GET /rest/api/1.0/projects/{project}/repos`; query `start`, `limit`.
- → `RepositoryMatch` (`project`, `slug`, `name`, `state`); поиск без учёта регистра по
  вхождению в `slug`/`name`.
- Ошибки/лимиты: пустое `name`; `limit` 1..1000; `max_pages` — общий бюджет на список
  проектов и все страницы репозиториев; останавливается на `limit` совпадений.

**`get_pull_request(base_url, repo, pr_id, *, token, allow_http_loopback=False) -> dict[str, object]`** — `bitbucket.py:446`
- REST: `GET /rest/api/1.0/projects/{project}/repos/{slug}/pull-requests/{id}`; query нет.
- → сырой объект PR целиком.
- Ошибки: `repo` не `PROJECT/slug`; `pr_id` не положительный signed-64-bit; ответ без
  `id`/`title`/`state` или с `id` ≠ запрошенному — ошибка.

**`get_pull_request_merge_status(base_url, repo, pr_id, *, token, allow_http_loopback=False) -> dict[str, object]`** — `bitbucket.py:470`
- REST: `GET .../pull-requests/{id}/merge`; query нет.
- → сырой объект mergeability (`canMerge`, `conflicted`, `outcome`, `vetoes`, ...).
- Ошибки/лимиты: один GET; POST на merge не отправляется.

**`get_repository_file(base_url, repo, path, *, token, at="master", allow_http_loopback=False) -> str`** — `bitbucket.py:500`
- REST: `GET .../raw/{path}`; query `at` (по умолчанию `"master"`); заголовок
  `Accept: text/plain`.
- → точный текст файла в UTF-8.
- Ошибки/лимиты: небезопасный `path`/`at`; JSON-ответ считается ошибкой, любой другой
  media type — текстом файла (`.md` приходит как `text/markdown`); 1 MiB; управляющие
  символы и эхо токена отвергаются.

**`get_repository_archive(base_url, project_key, repository_slug, *, token, at=None, format=None, max_bytes=67108864, allow_http_loopback=False) -> bytes`** — `bitbucket.py:537`
- REST: `GET /rest/api/1.0/projects/{project}/repos/{slug}/archive` ровно один раз;
  заголовок `Accept: */*`; query `at` (если задан), `format` (`zip`/`tar`/`tar.gz`/`tgz`,
  по умолчанию серверный `zip`).
- → точные байты архива; ничего не пишется на диск.
- Ошибки/лимиты: `max_bytes` по умолчанию 64 MiB, `None` — без границы (буферизация
  остаётся); `at=None` — серверная ветка по умолчанию, пустая строка отвергается;
  redirect/206/не-2xx/oversize — ошибка без частичного тела.

**`get_file_blame(base_url, repo, path, *, token, at=None, allow_http_loopback=False) -> list[BlameLine]`** — `bitbucket.py:631`
- REST: `GET .../browse/{path}`; query `blame=true`, `noContent=true`, `at` (только непустой).
- → `BlameLine` (`line` 1-based, `author`, `email`, `date` `YYYY-MM-DD` UTC, `commit`).
- Ошибки/лимиты: пейджинговый file-конверт вместо голого массива отвергается.

**`list_repository_files(base_url, repo, *, token, at=None, max_pages=100, before_page=None, allow_http_loopback=False) -> list[str]`** — `bitbucket.py:673`
- REST: `GET .../files`; query `at` (если непустой), `start`, `limit` (100).
- → список путей рекурсивно от корня.
- Ошибки/лимиты: `max_pages`; исключение `before_page` пробрасывается; поздний сбой не
  отдаёт частичный список.

**`list_directory(base_url, repo, path="", *, token, at=None, max_pages=100, allow_http_loopback=False) -> list[DirectoryEntry]`** — `bitbucket.py:711`
- REST: `GET .../browse[/{path}]`; query `at`, `start`, `limit`; строки берутся из
  вложенного `children`.
- → `DirectoryEntry` (`path`, `type`, `size`).
- Ошибки/лимиты: ответ `lines` (файл) или отсутствие `children` — ошибка; `max_pages`.

**`get_last_modified(base_url, repo, path=None, *, token, at=None, allow_http_loopback=False) -> dict[str, object]`** — `bitbucket.py:749`
- REST: `GET .../last-modified[/{path}]`; query `at` **обязателен**: при `at=None` функция
  сама резолвит default-ветку через `get_default_branch` и отправляет её `latestCommit`
  (полный 40-hex) — живая проверка 2026-11-23 показала HTTP 400 без `at`.
- → сырой объект (`files`, `latestCommit`, ...) без изменений.
- Ошибки/лимиты: нет default-ветки/неполный коммит — ошибка до запроса; серверный HTTP 500
  на path-форму, указывающую на файл, превращается в понятную ошибку (root-форма и каталог
  работают).

**`get_pull_request_file(base_url, repo, pr_id, path, *, token, side="new", allow_http_loopback=False) -> str`** — `bitbucket.py:826`
- REST: два запроса — `GET .../pull-requests/{id}`, затем `GET .../raw/{path}` (или raw
  fork-репозитория из метаданных PR); query `at=<40-hex latestCommit>`; `Accept: text/plain`.
- → текст выбранной стороны (`new` = `fromRef`, `old` = `toRef`).
- Ошибки/лимиты: `side` не `new`/`old`; небезопасный путь; битые `fromRef`/`toRef`/
  `latestCommit`; 1 MiB текста.

**`list_pull_request_files(base_url, repo, pr_id, *, token, allow_http_loopback=False) -> list[ChangedFile]`** — `bitbucket.py:866`
- REST: `GET .../pull-requests/{id}/changes`; query `limit=1000`.
- → `ChangedFile` (`path`, `type`, `node`); `PullRequestFile` — алиас.
- Ошибки/лимиты: `/changes` в 5.10 не пейджингуется; нетерминальная страница,
  `truncated=true` или строк не меньше заявленного `limit` — ошибка (выдача может быть
  урезана).

**`get_pull_request_diff(base_url, repo, pr_id, *, token, context=3, path=None, source_path=None, allow_http_loopback=False) -> dict[str, object]`** — `bitbucket.py:919`
- REST: `GET .../pull-requests/{id}/diff` (весь PR) или `.../diff/{path}`; query
  `contextLines`, `whitespace=ignore-all`, `withComments=false`; `srcPath` — только вместе
  с `path`.
- → сырой diff-объект.
- Ошибки/лимиты: `context` 0..100; `source_path` без `path`; объявленный `truncated` —
  `DeclaredTruncationError` (подкласс `AtlaWireError`); незаявленный серверный cap не
  детектируется.

**`get_pull_request_diff_with_fallback(base_url, repo, pr_id, *, token, context=3, allow_http_loopback=False) -> PullRequestDiffFallback`** — `bitbucket.py:971`
- REST: как `get_pull_request_diff` (весь PR); только при `DeclaredTruncationError` —
  `GET .../changes?limit=1000`, затем `GET .../diff/{path}` на каждый файл (с `srcPath`).
- → `PullRequestDiffFallback` (`fallback`, `fallback_reason`, `diff`, `files[]` с
  `path`/`source_path`/`diff`).
- Ошибки/лимиты: любой не-`DeclaredTruncationError` пробрасывается; пустая `/changes` после
  усечения, дубли путей, нет `srcPath` у MOVE/COPY/RENAME, агрегат > 32 MiB — ошибка;
  снимок между запросами не гарантируется.

**`get_pull_request_diff_text(base_url, repo, pr_id, *, token, context=3, path=None, source_path=None, allow_http_loopback=False) -> str`** — `bitbucket.py:1073`
- REST: тот же один запрос diff.
- → читаемый unified-diff-подобный текст (не применяемый патч; без index/binary/rename
  маркеров), управляющие символы и bidi экранируются.
- Ошибки/лимиты: наследует `get_pull_request_diff`; эхо токена в тексте — ошибка.

**`list_pull_request_comments(base_url, repo, pr_id, *, token, max_pages=100, allow_http_loopback=False) -> list[PullRequestComment]`** — `bitbucket.py:1115`
- REST: `GET .../pull-requests/{id}/activities`; query `start`, `limit` (100).
- → `PullRequestComment` (`id`, `author`, `path`, `line`, `text`, `created`); активности без
  `comment` пропускаются, ответы не разворачиваются.
- Ошибки/лимиты: `max_pages`; битый комментарий/anchor.

**`list_pull_request_commits(base_url, repo, pr_id, *, token, max_pages=100, allow_http_loopback=False) -> list[Commit]`** — `bitbucket.py:1151`
- REST: `GET .../pull-requests/{id}/commits`; query `start=0`, `limit=100`.
- → `Commit` (`hash`, `date` — UTC `YYYY-MM-DD HH:MM`, `timestamp` — исходные epoch-мс
  `authorTimestamp`, `author` — git-имя, `email` — `author.emailAddress` (на 5.10 бывает
  пустой строкой), `displayName` — `author.displayName` (на 5.10 всегда `None`: сервер
  документирует для автора только `name` и `emailAddress`), `message`).
- Ошибки/лимиты: `max_pages`; не-advancing `nextPageStart`.

**`list_pull_requests(base_url, repo, *, token, state="OPEN", order=None, author=None, direction=None, role=None, participant=None, limit=25, max_pages=100, allow_http_loopback=False) -> list[PullRequest]`** — `bitbucket.py:1182`
- REST: `GET .../pull-requests`; query `state`, `order` (если задан), `direction`
  (`INCOMING`/`OUTGOING`), `start`, `limit`; фильтр участников — `username.1` и `role.1`,
  которые всегда отправляются парой.
- → `PullRequest` (`id`, `title`, `state`, `author`, `from`, `to`, `updated`).
- Ошибки/лимиты: `state` ∈ OPEN/MERGED/DECLINED/ALL; `order` ∈ NEWEST/OLDEST;
  `role` ∈ AUTHOR/REVIEWER/PARTICIPANT; `author` — username и отбирается с
  `role.1=AUTHOR`; `role` без `participant` сначала резолвит username аутентифицированного
  пользователя из заголовка `X-AUSERNAME` одним bounded-запросом dashboard (маршрут не
  документирован); `participant` — готовый username и лишнего запроса не требует;
  `author` несовместим с `role`/`participant`; `limit` 1..1000.
**`list_my_pull_requests(base_url, *, token, state="OPEN", role="AUTHOR", participant_status=None, limit=25, max_pages=100, allow_http_loopback=False) -> list[MyPullRequest]`** — `bitbucket.py:1259`
- REST: `GET /rest/api/1.0/dashboard/pull-requests`; query `state`, `role`,
  `participantStatus` (если задан), `start`, `limit`.
- → `MyPullRequest` (`repo`, `id`, `title`, `state`, `author`, `reviewers_inactive`, `created`).
- Ошибки/лимиты: `state` ALL запрещён; `role` ∈ AUTHOR/REVIEWER/PARTICIPANT;
  `participant_status` — до трёх значений UNAPPROVED/NEEDS_WORK/APPROVED.

**`list_branches(base_url, repo, *, token, filter_text=None, max_pages=100, before_page=None, allow_http_loopback=False) -> list[Branch]`** — `bitbucket.py:1308`
- REST: `GET .../branches`; query `filterText` (если непустой), `start`, `limit`.
- → `Branch` (`name` из `displayId`, `id`, `commit`, `default`).
- Ошибки/лимиты: `max_pages`; битые страницы; исключение `before_page` пробрасывается.

**`get_branch(base_url, repo, name, *, token, max_pages=100, before_page=None, allow_http_loopback=False) -> Branch | None`** — `bitbucket.py:1343`
- REST: тот же список веток с `filterText=<name>`.
- → первая строка с точным `displayId == name`; `None` — полный успешный обход без совпадения.
- Ошибки/лимиты: пустое имя; при ошибке `None` не возвращается.

**`list_tags(base_url, repo, *, token, filter_text=None, order_by=None, limit=25, max_pages=100, allow_http_loopback=False) -> list[dict[str, object]]`** — `bitbucket.py:1398`
- REST: `GET .../tags`; query `filterText`, `orderBy` (если заданы), `start`, `limit`.
- → сырые объекты тегов без проекции.
- Ошибки/лимиты: `order_by` ∈ ALPHABETICAL/MODIFICATION; `limit` 1..1000; ровно `limit`
  строк доказывает только достижение потолка, не конец списка.

**`list_tags_with_metadata(base_url, repo, *, token, filter_text=None, order_by=None, limit=25, max_pages=100, allow_http_loopback=False) -> TagListing`** — `bitbucket.py:1441`
- REST: как `list_tags`.
- → `TagListing` (`tags`, `limit`, `complete`): `complete=True` только при терминальной
  странице и всех строках в пределах `limit`; `false` — тегов может быть больше.
- Ошибки/лимиты: `totalCount` сервер 5.10 не отдаёт, поэтому полнота — это `complete`.

**`get_tag(base_url, repo, name, *, token, allow_http_loopback=False) -> dict[str, object]`** — `bitbucket.py:1487`
- REST: `GET .../tags/{name}` (имя — slash-разделённый путь, сегменты кодируются по одному).
- → сырой объект тега.
- Ошибки/лимиты: небезопасное имя тега; один GET.

**`list_commits(base_url, repo, *, token, at=None, path=None, author=None, limit=25, max_pages=100, allow_http_loopback=False) -> list[Commit]`** — `bitbucket.py:1514`
- REST: `GET .../commits`; query `until` (из `at`), `path` (если непустой), `start`, `limit`;
  `author` фильтруется на стороне клиента по точному git-имени (серверный фильтр 5.10 не
  документирован), поэтому читаются страницы до `limit` совпадений.
- → `Commit` (`hash`, `date` — UTC `YYYY-MM-DD HH:MM`, `timestamp` — исходные epoch-мс
  `authorTimestamp`, `author` — git-имя, `email` — `author.emailAddress` (на 5.10 бывает
  пустой строкой), `displayName` — `author.displayName` (на 5.10 всегда `None`: сервер
  документирует для автора только `name` и `emailAddress`), `message` — сырое сообщение).
- Ошибки/лимиты: `limit` 1..1000; управляющие символы в `path`; `max_pages`.

**`list_commits_with_metadata(base_url, repo, *, token, at=None, path=None, author=None, limit=25, max_pages=100, allow_http_loopback=False) -> CommitListing`** — `bitbucket.py:1560`
- REST: как `list_commits`.
- → `CommitListing` (`commits`, `limit`, `complete`); `complete=True` — терминальная страница
  и все строки в пределах `limit`.
- Ошибки/лимиты: как у `list_commits`; общего числа 5.10 не сообщает.

**`get_commit(base_url, repo, sha, *, token, allow_http_loopback=False) -> dict[str, object]`** — `bitbucket.py:1627`
- REST: `GET .../commits/{sha}`; query нет.
- → сырой объект коммита.
- Ошибки/лимиты: `sha` не 7..40 hex; `id` ответа не 40-hex или не начинается с запрошенного
  сокращения.

**`list_commit_changes(base_url, repo, sha, *, token, max_pages=100, allow_http_loopback=False) -> list[ChangedFile]`** — `bitbucket.py:1659`
- REST: `GET .../commits/{sha}/changes`; query `start`, `limit` (100).
- → `ChangedFile` (`path`, `type`, `node`).
- Ошибки/лимиты: `sha`; `truncated=true`; `max_pages`; серверный незаявленный cap не
  детектируется.

**`get_commit_diff(base_url, repo, sha, *, token, paths=None, context=3, allow_http_loopback=False) -> dict[str, object] | list[dict[str, object]]`** — `bitbucket.py:1699`
- REST: `GET .../commits/{sha}/diff` или по одному `.../diff/{path}` на каждый путь; query
  `contextLines`, `whitespace=ignore-all`, `withComments=false`.
- → сырой diff-объект; при `paths` — список объектов в порядке путей.
- Ошибки/лимиты: `context` 0..100; не более 100 путей; небезопасный путь; объявленная
  обрезка — `DeclaredTruncationError`.

**`get_commit_diff_text(base_url, repo, sha, *, token, paths=None, context=3, allow_http_loopback=False) -> str`** — `bitbucket.py:1743`
- REST: запросы идентичны `get_commit_diff`.
- → читаемый текст под одним заголовком коммита (не патч); пустой diff — явный маркер.
- Ошибки/лимиты: как у `get_commit_diff`; эхо токена — ошибка.

**`get_project(base_url, project_key, *, token, raw=False, allow_http_loopback=False) -> ProjectDetail | dict[str, object]`** — `bitbucket.py:1777`
- REST: `GET /rest/api/1.0/projects/{projectKey}`; query нет.
- → `ProjectDetail` (`key`, `name`, `description`, `public`, `type`); `raw=True` — сырой
  объект (`id`, `links`, неизвестные поля).
- Ошибки/лимиты: `project_key` валидируется до сессии; один GET.

**`get_repository(base_url, project_key, slug, *, token, raw=False, allow_http_loopback=False) -> RepositoryDetail | dict[str, object]`** — `bitbucket.py:1810`
- REST: `GET .../projects/{projectKey}/repos/{repositorySlug}`.
- → `RepositoryDetail` (`slug`, `name`, `state`, `public`, `defaultBranch`; сервер 5.10 обычно
  не кладёт `defaultBranch` в объект репозитория, тогда `None`); `raw=True` — сырой объект.

**`get_default_branch(base_url, project_key, slug, *, token, raw=False, allow_http_loopback=False) -> BranchDetail | dict[str, object] | None`** — `bitbucket.py:1843`
- REST: `GET .../branches/default`; query нет; документированный 204 (пустой репозиторий) → `None`.
- → `BranchDetail` (`id`, `displayId`, `latestCommit`, `isDefault`); `raw=True` — сырой объект.

**`get_repository_changes(base_url, project_key, slug, until, *, token, since=None, limit=None, max_pages=100, raw=False, allow_http_loopback=False) -> list[ChangedFile] | list[dict[str, object]]`** — `bitbucket.py:1876`
- REST: `GET .../changes`; query `until` (обязателен), `since` (если задан), `start`, `limit`.
- → `ChangedFile` (`path`, `type`, `node`) или сырые строки при `raw=True`.
- Ошибки/лимиты: `until`/`since` — коммит или ref; `limit` 1..1000 или `None`; `max_pages`;
  курсор только из `nextPageStart`.

**`list_commit_comments(base_url, project_key, slug, commit_id, *, token, path=None, limit=None, max_pages=100, raw=False, allow_http_loopback=False) -> list[CommitComment] | list[dict[str, object]]`** — `bitbucket.py:1924`
- REST: `GET .../commits/{commitId}/comments`; query `path` (на живом 5.10 фактически
  обязателен), `start`, `limit`.
- → `CommitComment` (`id`, `author`, `text`, `createdDate`) или сырые строки при `raw=True`.
- Ошибки/лимиты: `commit_id` 7..40 hex; `limit` 1..1000 или `None`; `max_pages`.

**`get_commit_comment(base_url, project_key, slug, commit_id, comment_id, *, token, raw=False, allow_http_loopback=False) -> CommitComment | dict[str, object]`** — `bitbucket.py:1973`
- REST: `GET .../commits/{commitId}/comments/{commentId}`; query нет.
- → `CommitComment`; `raw=True` — сырой объект.
- Ошибки/лимиты: `id` ответа должен совпасть с запрошенным; `commit_id` 7..40 hex.

**`list_repository_participants(base_url, project_key, slug, *, token, max_pages=100, raw=False, allow_http_loopback=False) -> list[ParticipantRow] | list[dict[str, object]]`** — `bitbucket.py:2017`
- REST: `GET .../participants` (без фильтров `direction`/`filter`/`role`).
- → `ParticipantRow` (`name`, `displayName`, `role`); `role` заполняется только если сервер
  его прислал, иначе `None`; `raw=True` — сырые строки.
- Ошибки/лимиты: пустой ответ — пустой список; `max_pages`.

**`list_repository_forks(base_url, project_key, slug, *, token, max_pages=100, raw=False, allow_http_loopback=False) -> list[RepositoryLink] | list[dict[str, object]]`** — `bitbucket.py:2049`
- REST: `GET .../forks` (только прямые форки).
- → `RepositoryLink` (`slug`, `project`, `state`), `project` — плоский ключ (`PRJ`/`~user`);
  `raw=True` — сырые строки.

**`get_related_repositories(base_url, project_key, slug, *, token, max_pages=100, raw=False, allow_http_loopback=False) -> list[RepositoryLink] | list[dict[str, object]]`** — `bitbucket.py:2076`
- REST: `GET .../related`; возвращает список строк, как форки.
- → `RepositoryLink` (`slug`, `project`, `state`); `raw=True` — сырые строки.

## Confluence (`src/atlawire/confluence.py`)

Фиксированные `expand`/`depth` выставляет функция; continuation-ссылки не запрашиваются —
пейджер идёт по `start`/`limit` и проверяет метаданные (`start`, `size`, `totalSize`, `next`).

**`page_id(value: str | int) -> str`** — `confluence.py:179`
- REST: нет (локальная валидация); принимает положительное целое или ссылку с одним
  query-параметром `pageId`.
- → канонический десятичный ID строкой.
- Ошибки/лимиты: bool/неположительное/битая ссылка; сырые ASCII-контролы.

**`get_page(base_url, page_id_or_url, *, token, expand="body.storage,version,space,ancestors", allow_http_loopback=False) -> dict[str, object]`** — `confluence.py:211`
- REST: `GET /rest/api/content/{id}`; query `expand` — отправляется verbatim, по умолчанию
  `body.storage,version,space,ancestors`; пустая строка отвергается до запроса.
- → сырой JSON страницы; проверены `id`, `type`, `title`, а `body.storage.value` — только
  когда `expand` содержит `body` или `body.storage` (сырой storage XHTML, Markdown нет).
- Ошибки/лимиты: битый ID/ссылка; не-объект; страница не того типа; выбранный `body`
  без storage; один объект.

**`get_page_web_url(base_url, page_id_or_url, *, token, allow_http_loopback=False) -> str`** — `confluence.py:241`
- REST: `GET /rest/api/content/{id}` (через `get_page`); отдаёт `base_url` + `_links.webui`
  либо fallback `/pages/viewpage.action?pageId={id}`.
- → браузерный URL страницы.
- Ошибки/лимиты: как у `get_page`; небезопасный/абсолютный `webui` игнорируется; ссылки не
  следуются.

**`get_page_history(base_url, page_id_or_url, *, token, allow_http_loopback=False) -> dict[str, object]`** — `confluence.py:365`
- REST: `GET /rest/api/content/{id}/history`; query нет.
- → сырой объект истории.
- Ошибки/лимиты: это не полный список версий — только history-представление.

**`get_page_version(base_url, page_id_or_url, version, *, token, allow_http_loopback=False) -> dict[str, object]`** — `confluence.py:389`
- REST: `GET /rest/api/content/{id}`; query `status=historical`, `version=N`,
  `expand=body.storage,version`.
- → сырой JSON исторической версии с `body.storage` (XHTML).
- Ошибки/лимиты: `version` — положительное целое; форма страницы/`version.number` должна
  совпасть; живой прогон 2026-11-23 показал, что у исторической версии может быть пустой
  `body` — это пустое тело, а не ошибка чтения.

**`search_cql(base_url, query, *, token, limit=25, allow_http_loopback=False) -> list[ContentRow]`** — `confluence.py:446`
- REST: `GET /rest/api/search`; query `cql`, `start`, `limit` на каждой странице.
- → `ContentRow` (`id`, `space`, `type`, `title`, `url`).
- Ошибки/лимиты: пустой CQL; `limit` 0..1000; дубли/смена `totalSize`/обрыв до total —
  ошибка; `limit=0` → `[]` без запроса. Полноту показывает `search_cql_with_metadata`.

**`search_cql_with_metadata(base_url, query, *, token, limit=25, allow_http_loopback=False) -> ContentSearchMetadata`** — `confluence.py:474`
- REST: как `search_cql`.
- → `ContentSearchMetadata` (`rows: list[ContentRow]`, `truncated`, `total`, `next`):
  `truncated` — `totalSize` больше прочитанного или последняя страница несёт
  continuation; `total` — `totalSize` или `None`; `next` — ссылка продолжения, которую
  функция никогда не запрашивает; `limit=0` → пустой результат без сессии.
- Ошибки/лимиты: как у `search_cql`; отдельного запроса ради метаданных нет.

**`list_spaces(base_url, *, token, limit=100, allow_http_loopback=False) -> list[SpaceRow]`** — `confluence.py:521`
- REST: `GET /rest/api/space`; query `start`, `limit`.
- → `SpaceRow` (`key`, `name`, `type`).
- Ошибки/лимиты: `limit` 0..1000; `limit=0` → `[]` без сессии.

**`get_space(base_url, space_key, *, token, allow_http_loopback=False) -> SpaceDetail`** — `confluence.py:553`
- REST: `GET /rest/api/space/{key}`; query нет.
- → `SpaceDetail` (`key`, `name`, `type`, `status`, `url`); неизвестные поля отбрасываются.
- Ошибки/лимиты: ответ с другим `key` отвергается; `space_key` — один безопасный сегмент.

**`list_space_content(base_url, space_key, *, token, type=None, limit=100, allow_http_loopback=False) -> ContentRows`** — `confluence.py:579`
- REST: без `type` — `GET /rest/api/space/{key}/content` (per-type map), с `type` —
  `GET /rest/api/space/{key}/content/{type}`; query `start`, `limit`, `expand=version`.
- → `ContentRows` (`rows: list[ContentSummary]`, `truncated`); порядок без `type` — pages,
  blogposts, затем остальные типы по алфавиту.
- Ошибки/лимиты: `limit` 0..1000; полный бюджет — не ошибка, а `truncated=true`; `limit=0` →
  пустой список без сессии.

**`list_children(base_url, page_id_or_url, *, token, limit=100, allow_http_loopback=False) -> list[ChildRow]`** — `confluence.py:610`
- REST: `GET /rest/api/content/{id}/child/page`; query `expand=version`, `start`, `limit`.
- → `ChildRow` (`id`, `title`, `version`); ошибка отбрасывает уже прочитанные строки.
- Ошибки/лимиты: `limit` 0..1000; `limit=0` → `[]` без сессии (но base URL и ID проверяются);
  список не показывает, что сервер имел ещё строки — для этого
  `list_children_with_metadata`.

**`list_children_with_metadata(base_url, page_id_or_url, *, token, limit=100, allow_http_loopback=False) -> ChildRows`** — `confluence.py:649`
- REST: как `list_children`.
- → `ChildRows` (`rows`, `truncated`, `total`); `truncated` — из `totalSize`, иначе из
  `_links.next`; `total` — `totalSize` или `None`, никогда не выводится из размера страницы.
- Ошибки/лимиты: как у `list_children`.

**`get_page_attachments(base_url, page_id_or_url, *, token, start=0, limit=50, allow_http_loopback=False) -> dict[str, object]`** — `confluence.py:694`
- REST: `GET /rest/api/content/{id}/child/attachment`; query `start`, `limit`.
- → сырой JSON одной страницы (метаданные и `_links` внутри); ссылки не следуются.
- Ошибки/лимиты: `start` ≥ 0; `limit` 1..1000; одна страница; сервер может урезать `limit`.

**`get_page_attachments_with_metadata(base_url, page_id_or_url, *, token, start=0, limit=50, allow_http_loopback=False) -> RawContentPage`** — `confluence.py:725`
- REST: как `get_page_attachments`.
- → `RawContentPage` (`rows`, `truncated`, `total`, `next`); `truncated` — из `totalSize`,
  иначе из `next`; `next` не запрашивается.
- Ошибки/лимиты: как у `get_page_attachments`.

**`get_page_comments(base_url, page_id_or_url, *, token, start=0, limit=25, include_replies=True, allow_http_loopback=False) -> dict[str, object]`** — `confluence.py:762`
- REST: `GET /rest/api/content/{id}/child/comment`; query `start`, `limit`,
  `expand=body.storage`, `depth=all` (по умолчанию).
- → сырой JSON одной страницы (тела — storage XHTML).
- Ошибки/лимиты: `include_replies=False` убирает `depth`; `limit` 1..1000; одна страница.

**`get_page_comments_with_metadata(base_url, page_id_or_url, *, token, start=0, limit=25, include_replies=True, allow_http_loopback=False) -> RawContentPage`** — `confluence.py:800`
- REST: как `get_page_comments`.
- → `RawContentPage` (`rows`, `truncated`, `total`, `next`).
- Ошибки/лимиты: как у `get_page_comments`.

**`get_page_labels(base_url, page_id_or_url, *, token, start=0, limit=200, allow_http_loopback=False) -> dict[str, object]`** — `confluence.py:841`
- REST: `GET /rest/api/content/{id}/label`; query `start`, `limit`.
- → сырой JSON одной страницы; схема ответа не предполагается.
- Ошибки/лимиты: `start`/`limit`; одна страница.

## Jira (`src/atlawire/jira.py`)

JQL-поиск для коротких строк фиксирует
`fields=summary,status,priority,issuetype,assignee,updated` (`_SEARCH_FIELDS`). Пейджер
проверяет `startAt`/`maxResults`/`total` и отвергает дрейф метаданных; Jira 8.22 может не
прислать `total` — тогда пустая страница единственное доказательство конца.

**`get_issue(base_url, key_or_url, *, token, expand="renderedFields", allow_http_loopback=False) -> dict[str, object]`** — `jira.py:200`
- REST: `GET /rest/api/2/issue/{key}`; query `expand` (по умолчанию `renderedFields`,
  передаётся verbatim).
- → сырой JSON задачи (`fields` + `renderedFields`, неизвестные поля сохраняются; Markdown нет).
- Ошибки/лимиты: ключ не `[A-Z][A-Z0-9_]*-[0-9]+`/URL; ответ без `key`/`fields`; после move
  допустим другой ключ — проверяется синтаксис; один GET.

**`get_issue_worklogs(base_url, key_or_url, *, token, allow_http_loopback=False) -> dict[str, object]`** — `jira.py:226`
- REST: `GET /rest/api/2/issue/{key}/worklog`; query нет.
- → сырой worklog-документ (`startAt`, `maxResults`, `total`, `worklogs`).
- Ошибки/лимиты: только первая серверная страница; для полного обхода —
  `list_issue_worklogs`.

**`get_issue_changelog(base_url, key_or_url, *, token, allow_http_loopback=False) -> dict[str, object]`** — `jira.py:256`
- REST: `GET /rest/api/2/issue/{key}`; query `expand=changelog`.
- → сырой `changelog`-документ (`startAt`, `maxResults`, `total`, `histories`).
- Ошибки/лимиты: серверный cap виден в `total`; полнота не доказывается; для полной истории —
  `list_issue_changelog`.

**`list_issue_worklogs(base_url, key_or_url, *, token, max_pages=100, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:292`
- REST: `GET /rest/api/2/issue/{key}/worklog` со `startAt` по страницам, пока строки не
  покроют заявленный `total`.
- → все записи как пришли, включая неизвестные поля.
- Ошибки/лимиты: `max_pages` 1..1000 — исчерпание бюджета ошибка, не частичный список;
  `startAt`/`total`/`maxResults` каждой страницы проверяются (сервер, игнорирующий `startAt`,
  отвергается).

**`list_issue_changelog(base_url, key_or_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:410`
- REST: `GET /rest/api/2/issue/{key}?expand=changelog`.
- → полная история `histories` или ошибка.
- Ошибки/лимиты: если `total` больше числа `histories` — ошибка с обоими числами; отдельного
  пагинируемого ресурса changelog у 8.22 нет.

**`list_issue_comments(base_url, key_or_url, *, token, limit=None, max_pages=100, allow_http_loopback=False) -> list[CommentRow]`** — `jira.py:462`
- REST: `GET /rest/api/2/issue/{key}/comment`; query `startAt`, `maxResults` (50 или `limit`).
- → `CommentRow` (`id`, `author`, `created`, `updated`, `body` — сырая wiki-разметка).
- Ошибки/лимиты: `limit` 1..1000 или `None`; `max_pages`; дубли ID, дрейф `total`/`maxResults`,
  пустая страница раньше total — ошибка; форма списка не показывает усечение — для этого
  `list_issue_comments_with_metadata`.

**`list_issue_comments_with_metadata(base_url, key_or_url, *, token, limit=None, max_pages=100, allow_http_loopback=False) -> CommentThreadMetadata`** — `jira.py:495`
- REST: как `list_issue_comments`.
- → `CommentThreadMetadata` (`rows`, `truncated`, `total`); `truncated` истинно, когда `limit`
  остановил чтение раньше известного `total`; пустой тред — пустой и полный.

**`search_raw(base_url, jql, *, token, fields="*all", limit=None, start=0, expand=None, allow_http_loopback=False) -> dict[str, object]`** — `jira.py:680`
- REST: `GET /rest/api/2/search`; query `jql`, `fields`, `startAt`, `maxResults` (если `limit`),
  `expand` (если задан).
- → сырой search-envelope без проекции; `fields` — строка verbatim или список (через запятую
  в заданном порядке); один GET, без пагинации.
- Ошибки/лимиты: пустой JQL; `start` ≥ 0; `limit` 1..1000; пустой `fields` отвергается.

**`search_issues(base_url, query, *, token, fields="summary,status,priority,issuetype,assignee,updated", limit=50, allow_http_loopback=False) -> list[IssueRow]`** — `jira.py:729`
- REST: `GET /rest/api/2/search`; query `jql`, `fields` (строка — verbatim, список — через
  запятую в заданном порядке; пустой выбор отвергается до запроса), `startAt`,
  `maxResults` (не больше недостающих строк).
- → `IssueRow` (`key`, `status`, `type`, `priority`, `assignee`, `updated` (10 символов),
  `summary`).
- Ошибки/лимиты: `limit` 1..1000; `fields` валидируется до запроса; делегирует в
  `search_issues_with_metadata`; список не показывает cap.

**`search_issues_with_metadata(base_url, query, *, token, fields="summary,status,priority,issuetype,assignee,updated", limit=50, allow_http_loopback=False) -> IssueSearchMetadata`** — `jira.py:764`
- REST: как `search_issues`; `fields` уходит в каждый запрос.
- → `IssueSearchMetadata` (`rows`, `truncated`, `total`); `truncated` истинно при известном
  `total` > строк, а также когда сервер не прислал `total` и лимит достигнут.
- Ошибки/лимиты: как у `search_issues`; дополнительного запроса ради метаданных нет.

**`search_all_issues(base_url, jql, *, token, fields="*all", limit=None, max_pages=100, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:803`
- REST: `GET /rest/api/2/search` от `startAt=0`, шаг — фактически прочитанное число задач;
  размер страницы из эха `maxResults` (≤ 100).
- → все найденные задачи как есть, без проекции.
- Ошибки/лимиты: `max_pages` 1..1000 (100 страниц ≈ 10 000 задач); исчерпание — ошибка, не
  частичный список; пустая страница до заявленного total — ошибка; `isLast` игнорируется.

**`search_all_issues_with_metadata(base_url, jql, *, token, fields="*all", limit=None, max_pages=100, allow_http_loopback=False) -> RawIssueSearchMetadata`** — `jira.py:847`
- REST: как `search_all_issues`.
- → `RawIssueSearchMetadata` (`rows`, `truncated`, `total`); при `limit=None` обход полный и
  `truncated=False`; при достигнутом лимите и отсутствии `total` — консервативно `True`.

**`titles(base_url, keys, *, token, allow_http_loopback=False) -> dict[str, str]`** — `jira.py:889`
- REST: `GET /rest/api/2/search` с `jql="key in (K1,K2,...)"`, `fields=summary`,
  `maxResults=<размер батча>`; ключи батчатся по 50 в порядке входа.
- → `{key: summary}` для найденных задач; ненайденные/скрытые/удалённые опускаются.
- Ошибки/лимиты: ключи валидируются до сессии; пустой список → `{}` без запроса.

**`list_my_issues(base_url, *, token, status=None, limit=50, allow_http_loopback=False) -> list[IssueRow]`** — `jira.py:971`
- REST: `GET /rest/api/2/search` через `search_issues`; JQL
  `assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC` либо
  `... status = "<status>" ...`.
- → `IssueRow` (см. `search_issues`).
- Ошибки/лимиты: `status` — строка без кавычек/бэкслешей/контролов; далее как у
  `search_issues`.

**`list_statuses(base_url, *, token, allow_http_loopback=False) -> list[str]`** — `jira.py:1003`
- REST: `GET /rest/api/2/status`; query нет.
- → отсортированные уникальные имена статусов.
- Ошибки/лимиты: без пагинации — весь массив сразу.

**`list_priorities(base_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1031`
- REST: `GET /rest/api/2/priority`; → сырые объекты приоритетов без проекции.

**`list_resolutions(base_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1052`
- REST: `GET /rest/api/2/resolution`; → сырые объекты резолюций.

**`list_issue_types(base_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1072`
- REST: `GET /rest/api/2/issuetype`; → сырые типы задач (subtask не фильтруются).

**`list_status_categories(base_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1092`
- REST: `GET /rest/api/2/statuscategory`; → сырые категории статусов.

**`list_jira_projects(base_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1112`
- REST: `GET /rest/api/2/project`; → сырой массив проектов.
- Ошибки/лимиты: пагинационных метаданных нет — короткий массив не доказывает полноту.

**`search_users(base_url, username, *, token, start_at=0, max_results=50, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1153`
- REST: `GET /rest/api/2/user/search`; query `username`, `startAt`, `maxResults`.
- → сырые объекты пользователей одной страницы.
- Ошибки/лимиты: пустой/не-UTF-8 `username`; `start_at` ≥ 0; `max_results` 1..1000; одна
  страница, полнота не доказывается.

**`list_transitions(base_url, key_or_url, *, token, allow_http_loopback=False) -> list[TransitionRow]`** — `jira.py:1211`
- REST: `GET /rest/api/2/issue/{key}/transitions`; query нет.
- → `TransitionRow` (`id`, `name`, `to_status`).
- Ошибки/лимиты: битый ключ; вся коллекция одним ответом.

**`list_issue_remote_links(base_url, key_or_url, *, token, allow_http_loopback=False) -> list[dict[str, object]]`** — `jira.py:1276`
- REST: `GET /rest/api/2/issue/{key}/remotelink`; query нет.
- → сырые remote links (URL — данные, не адреса запросов).

**`get_current_user(base_url, *, token, allow_http_loopback=False) -> CurrentUser`** — `jira.py:1308`
- REST: `GET /rest/api/2/myself`; query нет.
- → `CurrentUser` (`name`, `displayName`, `email` из `emailAddress`).

**`resolve_user(base_url, term=None, *, token, allow_http_loopback=False) -> CurrentUser`** — `jira.py:1381`
- REST: `term=None` → `GET /rest/api/2/myself`; иначе поиск пользователей по исходному терму,
  BBK-совместимой русской транслитерации и четырёхбуквенному транслитерированному префиксу.
- → `CurrentUser` (`name`, `displayName`, `email`); точный логин важнее не-точного кандидата.
- Ошибки/лимиты: два и более разных кандидата — ошибка с найденными логинами; пустой
  `displayName` заменяется логином; токен в сообщение не попадает.

**`get_issue_votes(base_url, key_or_url, *, token, allow_http_loopback=False) -> IssueVotes`** — `jira.py:1858`
- REST: `GET /rest/api/2/issue/{key}/votes`.
- → `IssueVotes` (`voters: list[UserRefRow]`, `hasVoted`, `watchCount`); отсутствующие поля —
  `None`, не вычисляются (на 8.22 `watchCount` в ответе нет → `None`).

**`get_issue_watchers(base_url, key_or_url, *, token, allow_http_loopback=False) -> IssueWatchers`** — `jira.py:1884`
- REST: `GET /rest/api/2/issue/{key}/watchers`.
- → `IssueWatchers` (`watchers`, `watchCount`, `isWatching`); список сервер отдаёт целиком.

**`list_issue_subtasks(base_url, key_or_url, *, token, allow_http_loopback=False) -> list[SubtaskRow]`** — `jira.py:1908`
- REST: `GET /rest/api/2/issue/{key}/subtask`.
- → `SubtaskRow` (`key`, `summary`, `type`, `status` — имена, не вложенные объекты); весь
  массив проверяется до возврата.

**`get_issue_comment(base_url, key_or_url, comment_id, *, token, allow_http_loopback=False) -> CommentRow`** — `jira.py:1932`
- REST: `GET /rest/api/2/issue/{key}/comment/{id}`.
- → `CommentRow` (`id`, `author`=логин, `body`=сырая wiki-строка, `created`, `updated`).

**`get_issue_worklog(base_url, key_or_url, worklog_id, *, token, allow_http_loopback=False) -> WorklogRow`** — `jira.py:1962`
- REST: `GET /rest/api/2/issue/{key}/worklog/{id}`.
- → `WorklogRow` (`id`, `author`, `started`, `seconds`=`timeSpentSeconds`, `comment`).

**`get_issue_properties(base_url, key_or_url, *, token, allow_http_loopback=False) -> IssuePropertyKeys`** — `jira.py:1991`
- REST: `GET /rest/api/2/issue/{key}/properties`.
- → `{"keys": [...]}`; пустой ответ — пустой список, не ошибка.

**`get_issue_property(base_url, key_or_url, property_key, *, token, allow_http_loopback=False) -> IssueProperty`** — `jira.py:2015`
- REST: `GET /rest/api/2/issue/{key}/properties/{propertyKey}` (ключ — один сегмент пути).
- → `{"key": ..., "value": ...}`; `value` — произвольный JSON без изменений.
- Ошибки/лимиты: пустой ключ, разделители пути, длина > 255 — ошибка до запроса.

**`get_issue_link(base_url, link_id, *, token, allow_http_loopback=False) -> IssueLinkRow`** — `jira.py:2045`
- REST: `GET /rest/api/2/issueLink/{linkId}`.
- → `IssueLinkRow` (`id`, `type`, `inwardIssue`, `outwardIssue` — ключи задач, не объекты).

## Диспетчер операций (`src/atlawire/operations.py`)

Реестр собран из 192 строк `manifest.json` и 51 встроенной `_Operation(...)`; после
дедупликации по `(product, method, path)` — **202 операции** (109 Jira, 57 Bitbucket,
36 Confluence; 199 GET и 3 semantic-read POST). Маршрут берётся из реестра, не из аргументов.

**`list_operations() -> list[dict[str, object]]`** — `operations.py:1682`
- REST: нет (офлайн, токен не читается).
- → отсортированный по id список описаний: `id`, `product`, `method`, `path`, `description`,
  `documented_version`, `response` (`kind`, `required`, `items_required`,
  `optional_object_arrays`, `null_on_204`), `arguments`, `query_rules`, `body`, `query`.
- Ошибки/лимиты: нечитаемый manifest просто не добавляет записей (базовые остаются).

**`describe_operation(operation_id: object) -> dict[str, object]`** — `operations.py:1785`
- REST: нет (офлайн).
- → описание одной операции плюс `command` (`atlawire read <id>`) и `example` (argv с
  безопасными плейсхолдерами).
- Ошибки: неизвестный id/не str — `AtlaWireError(category="unknown_operation")` без эха значения.

**`canonical_operations() -> list[dict[str, object]]`** — `operations.py:1798`
- REST: нет (офлайн).
- → компактные описания трёх канонических чтений (`bitbucket.repository.get`,
  `confluence.space.get`, `jira.project.get`): `id`, `product`, `description`, `command`,
  `example`.
- Ошибки/лимиты: те же 3 записи, что отдаёт `--catalog` в `operations`.

**`read_operation(operation_id, base_url, *, token, arguments, query=None, body=None, allow_http_loopback=False, use_library=False) -> dict[str, object] | list[object] | None`** — `operations.py:1916`
- REST: `{method} {base_url}{path}` выбранной операции; плейсхолдеры — из `arguments` с
  кодированием; query — только объявленные типизированные поля.
- → сырой JSON (`dict`/`list`; `None` только для 204 `bitbucket.repository.default-branch`);
  ровно один запрос, без пагинации.
- Ошибки/лимиты: неизвестный id → `unknown_operation`; лишние/битые `arguments`/`query`/`body`
  → `validation`; не-GET без `use_library=True` → `validation`; неверная форма/обязательные
  поля ответа → `OperationShapeError` (`upstream`).

**`read_binary(operation_id, base_url, *, token, arguments, destination, max_bytes=33554432, allow_http_loopback=False) -> dict[str, object]`** — `operations.py:1870`
- REST: один зарегистрированный binary-read (7 операций).
- → квитанция `{"path", "bytes", "sha256", "content_type"}`; файл создаётся целиком или не
  создаётся вовсе.
- Ошибки/лимиты: `destination` не должен существовать; `max_bytes` по умолчанию 32 MiB;
  операция должна иметь `kind="binary"`.

## SDK и транспорт (`src/atlawire/sdk.py`, `http.py`)

`atlawire.sdk` — тонкая read-only обёртка над `atlassian-python-api==5.0.5`; таймауты
`(5, 30)`, редиректы запрещены, административные и мутирующие маршруты отсекаются до запроса.

**`client_for(product, base_url, token, *, allow_http_loopback=False) -> ReadOnlyClient`** — `sdk.py:341`
- → библиотечный клиент (`Jira`, `ConfluenceServer` или `Bitbucket`); закрывает вызывающий.

**`get_json(product, base_url, path, *, token, params=None, allow_http_loopback=False) -> object`** — `sdk.py:359`
- REST: стандартный неадминистративный `GET /rest/...`; → распарсенный JSON.

**`get_json_with_status(...) -> tuple[int, object]`** — `sdk.py:380`
- То же, но → `(status, payload)`.

**`request_json(product, base_url, path, *, method, token, params=None, body=None, allow_http_loopback=False) -> object`** — `sdk.py:401`
- REST: GET или разрешённый read-only POST (Jira `/rest/api/2/search`, Jira
  `/rest/api/2/worklog/list`, Bitbucket `/rest/api/1.0/markup/preview`, Confluence
  `/rest/api/contentbody/convert/{to}`); → payload.

**`request_json_with_status(...) -> tuple[int, object]`** — `sdk.py:425`
- То же, но → `(status, payload)`.

**`download_to_file(product, base_url, path, *, token, destination, params=None, max_bytes=33554432, allow_http_loopback=False) -> tuple[str | None, int, str]`** — `sdk.py:492`
- → `(content_type, bytes, sha256)`; файл публикуется атомарно, на ошибке не остаётся.

Публичные функции `http.py`: `normalize_base_url` (`135`), `new_session` (`153`),
`bearer_session` (`193`), `reject_credential_echo` (`396`), `post_json_object` (`525`),
`get_json_any` (`571`), `get_json_object` (`578`), `get_json_object_allow_no_content` (`587`),
`get_json_array` (`605`), `get_text` (`614`), `read_encoded_limited` (`683`).

## Прочие модули

* `repo_scan.scan_repository_extensions(base_url, extension, *, token, workers=8, max_pages=100,
  allow_http_loopback=False, project=None) -> list[ExtensionMatch]` (`repo_scan.py:86`) —
  обход projects → repositories → `/files`; ошибка страницы обрывает скан без строк.
* `repo_scan.scan_repository_extensions_report(...) -> ExtensionScanReport`
  (`repo_scan.py:144`) — то же, но при исчерпании page budget возвращает прочитанные строки с
  `complete=False`, `repositories_scanned`, `repositories_total`, `reason`.
* `repo_grep.grep_repository(base_url, repo, pattern=None, *, token, at=None, glob=None,
  path=None, ignore_case=True, limit=200, timeout_s=120.0, regex_timeout_s=5.0, max_pages=100,
  allow_http_loopback=False) -> GrepResult` (`repo_grep.py:149`) — regex или листинг путей
  одного закреплённого коммита; `GrepResult` содержит `hits`, `truncated`, `complete`,
  `status` (`complete`/`truncated`/`timeout`), `message`.
* `identity.whoami(*, confluence, jira, bitbucket, allow_http_loopback=False) ->
  dict[str, IdentityCheck]` (`identity.py:93`) — по записи на продукт; Confluence требует
  известную личность, Bitbucket подтверждает только authenticated dashboard.
* `federated.federated_search(terms, *, confluence, jira, bitbucket, limit=20,
  allow_http_loopback=False) -> dict[str, object]` (`federated.py:150`) — поиск каждого терма
  по трём продуктам с `counts`, `errors`, `complete`, `budget`, `limits`, `limitations`.
* `catalog.build_command_catalog(group) -> dict[str, object]` (`catalog.py:12`) — плоские
  метаданные Click-команд для `--catalog`.

## Формат ответа для агента

Правило: структурные данные (поля задач, статусы, даты, id, счётчики) — JSON; человекочитаемый
контент (тело страницы, описание, комментарии) — Markdown; сырой storage XHTML или сырой JSON
сервера — только когда вызывающий явно просит.

* В Python-API: `get_*` обычно отдают сырой объект сервера, `list_*`/`search_*` — проекцию
  (`IssueRow`, `ContentRow`, `Repository`, ...). Исключения помечены в записях выше:
  `list_tags` отдаёт сырые строки, `get_space` — проекцию, `get_page_attachments/comments/labels`
  — сырую страницу.
* Markdown: `confluence_markdown.render_page_markdown(page)` (`confluence_markdown.py:300`)
  сохраняет ссылки (`ri:page` → `confluence:<title>`, `ri:attachment` → `attachment:<name>`,
  `ri:url`/`<a href>` — как есть), картинки `ac:image`, параметры макросов, таблицы и панели;
  неизвестный макрос — читаемый маркер. `issue_markdown.render_issue_markdown(issue,
  use_wiki=False)` (`issue_markdown.py:691`) рендерит HTML `renderedFields` или сырую wiki
  (`use_wiki=True`), сохраняет картинки и упоминания пользователей, комментарии — в исходном
  порядке. `issue_markdown.wiki_to_markdown(text)` (`issue_markdown.py:589`) — компактный
  read-only рендер Jira wiki.
* CLI: `--json` печатает проекцию (там, где у команды есть TSV/человекочитаемый режим), `--raw`
  печатает сырой ответ сервера у новых команд (`issue-votes`, `space`, `repository`, ...);
  `--fields`/`--expand` у `jql`, `--expand` у `cql`, `page`, `issue` переключают на один
  непроецированный документ. `--limit` где он объявлен ограничивает строки (и у
  `issue-comments` уходит в `maxResults`), `--max-pages` — бюджет страниц.
* Признак неполноты: `truncated`/`complete`/`total` в `*_with_metadata`-функциях и в JSON
  команд (`issue-comments`, `children`/`page-comments` — только в библиотеке, `space-content`,
  `tags`/`commits` — библиотека, `scan`, `grep`). Если признака нет, короткая выдача не
  доказывает полноту.

## Как это вызывает наш потребитель

`base` и `token` потребитель держит сконфигурированными; ниже — одна строка вызова.
`revision` — один и тот же явный ref для пары `list_repository_files`/`get_repository_file`.

| Вызов потребителя | Одна строка | Что получает / примечание |
|---|---|---|
| `list_files` | `bitbucket.list_repository_files(base, "PROJ/slug", token=token, at=revision)` | `list[str]`; `at=None` — ветка сервера. |
| `file_at` | `bitbucket.get_repository_file(base, "PROJ/slug", "path/file.py", token=token, at=revision)` | `str`; дефолт функции — `"master"`, поэтому передавайте `at` явно. |
| `projects` | `bitbucket.list_projects(base, token=token)` | проекции `Project`. |
| `repos` | `bitbucket.list_repositories(base, "PROJ", token=token)` | проекции `Repository`. |
| `search_code` | `bitbucket_search.search_code(base, "term", token=token)` (`bitbucket_search.py:52`) | индексный поиск плагина (`POST /rest/search/latest/search`), проекции `SearchRow`. |
| `page` | `confluence.get_page(base, 7307751, token=token)` | сырой JSON страницы (storage XHTML внутри). |
| `page_storage` | `нет функции` | публичной функции нет; CLI — `atlawire page ID --storage`, библиотека — `confluence.get_page(...)["body"]["storage"]["value"]` (`confluence.py:211`). |
| `page_md` | `confluence_markdown.render_page_markdown(confluence.get_page(base, 7307751, token=token))` | Markdown; CLI — `atlawire page ID --markdown`. |
| `search_cql` | `confluence.search_cql(base, 'text ~ "term"', token=token)` | проекции `ContentRow`. |
| `issue` | `jira.get_issue(base, "PLAT-1", token=token)` | сырой JSON задачи. |
| `jql` | `jira.search_raw(base, "project = PLAT ORDER BY updated DESC", token=token, fields="summary,status,priority,issuetype,assignee,reporter,updated,created,labels", limit=50)` (`jira.py:680`) | сырой search-envelope с caller-полями; CLI — `atlawire jql ... --fields ...`. |
| `me` | `jira.get_current_user(base, token=token)` | проекция `CurrentUser`. |
| `rows` | `jira.search_issues(base, "project = PLAT ORDER BY updated DESC", token=token, limit=50)` | проекция `IssueRow` (key, status, type, priority, assignee, updated, summary). |
| `titles` | `jira.titles(base, ["PLAT-1", "PLAT-2"], token=token)` (`jira.py:889`) | `{key: summary}`, батчи по 50; кэша нет. |
| `url` | `confluence.get_page_web_url(base, 7307751, token=token)` (`confluence.py:241`) | браузерный URL страницы; для задачи Jira URL не строится. |
| `platform` | `нет функции` | реестра окружений нет; ближайшая — `http.normalize_base_url` (`http.py:135`). |

Итого «нет функции»: **2** (`page_storage`, `platform`); `url` закрыт только для страниц
Confluence, `titles` и `jql` закрыты.

## Замечания к API

1. `at` в Bitbucket расходится: `get_repository_file` по умолчанию фиксирует `"master"`, а
   `get_file_blame`/`list_repository_files`/`list_commits`/`list_directory` используют
   `at=None` (ветка сервера). `get_last_modified` при `at=None` сам резолвит default-ветку.
2. Проекция против сырого остаётся неоднородной: `list_tags` отдаёт сырые `dict`, а рядом есть
   `list_tags_with_metadata`; `get_*` обычно сырые, `list_*`/`search_*` — проекции, но
   `get_space` — проекция. Правило «`get_*` сырое, `list_*`/`search_*` проекция» работает с
   исключениями из раздела выше.
3. Часть списков по-прежнему отдаёт голый `list` без признака обрезки: `search_cql`,
   `list_spaces`, `list_children`, `list_pull_requests`, `list_commits`, `list_tags`,
   `list_pull_request_comments/commits`, `list_commit_changes`, `list_issue_subtasks`. Для
   `children`/`tags`/`commits`/Jira-комментариев/поиска/CQL есть `*_with_metadata`-варианты;
   для остальных признак неполноты виден только по достигнутому `limit`/бюджету страниц.
4. `list_pull_request_files` отвергает полную `/changes`-страницу и объявленную обрезку;
   `get_pull_request_diff` не детектирует незаявленный серверный cap.
5. `get_issue_worklogs`/`get_issue_changelog` отдают одну серверную страницу, `total` виден, но
   неполнота не заполняется автоматически — для полного обхода есть
   `list_issue_worklogs`/`list_issue_changelog`.
6. Content-обёрток `page_md`/`issue_md` в виде одной функции нет: CLI рендерит Markdown, а
   библиотеке нужна пара «`get_*` + `render_*`».

## Приложение: как проверены пути

Пути не переписаны по памяти: сигнатуры и строки сняты `inspect`/`ast` с рабочего дерева
(`HEAD a4efee1`), REST-фрагменты сверены `grep` по `src/atlawire/{bitbucket,confluence,jira,
operations,sdk,http,repo_scan}.py` и `manifest.json`. Живые прогоны, на которые опираются
примечания (`last-modified` без `at` → HTTP 400; path-форма файла → HTTP 500), записаны в
`checks/e2e_param_matrix_report.md` и `docs/LIVE-READ-ONLY.md`; они проверяют одно
развёртывание и не заменяют проверку на другом стенде.
