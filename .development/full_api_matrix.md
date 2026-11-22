# Full read-only API matrix

Матрица read-only возможностей Atlassian REST API: Jira, Confluence, Bitbucket.
Назначение — оценить, какие возможности стоит реализовать в AtlaWire.

Формат: TSV. Столбцы разделены символом табуляции: `Функционал`, `AW`, `BBK`.
Строки, начинающиеся с `#`, — служебные заголовки, их пропускает TSV-парсер.

Область:
- цель — все неадминистративные read-only REST-возможности Jira, Confluence и
  Bitbucket; перечисленные ниже категории — примеры, а не исчерпывающий список;
- включены, в частности, карточки, поиск, история, файлы, PR, справочники,
  метаданные, бинарное чтение вложений и семантически read-only POST-операции;
- неадминистративные plugin/agile-чтения входят в область там, где доступны;
  неоценённый endpoint считается unknown до установления его семантики и
  версии, а не исключается только потому, что он относится к плагину;
- исключены административные операции и любые серверные изменения: создание,
  правка, удаление, переходы, слияния, комментарии, ветки, загрузка вложений.

Обозначения:
- ✅A — реализовано полностью;
- ✔P — реализовано частично (подмножество, ограничение охвата или только
  внутренний API без команды);
- ⌛D — отложено: кандидат на реализацию, приоритет не зафиксирован;
- ❌N — NOT IMPLEMENTED: read-only возможность в пользовательской области,
  реализации нет;
- 🚫X — EXCLUDED: запись, администрирование, системная поддержка или
  намеренно исключённый из read-only клиента класс;
- ❓? — NOT ASSESSED: endpoint не оценён и остаётся unknown до установления
  семантики и версии; это не означает исключение из области.
- ❌N в столбце BBK означает отсутствие/вне области у BBK и не переносится
  автоматически на legend AW.

Снимок: рабочее дерево после 79e501d (2026-11-22), первый батч адаптеров и
обнаружения; BBK — локальный чекаут на 2026-11-21.
Статусы записи BBK в матрицу не входят: это отдельный, отложенный класс.

## Jira

Функционал	AW	BBK
Get server info — версия и базовые сведения об инстансе	❓?	❌N
Get current user (myself) — кто я: логин, имя, часовой пояс	✅A	✅A
Get user — профиль пользователя по ключу или логину	✅A	✔P
Search users — поиск пользователей по имени или логину	✔P	✅A
Search assignable users — кому можно назначить задачу	✔P	❌N
Get user groups — группы, в которых состоит пользователь	❌N	❌N
Get issue — карточка задачи: поля, статус, исполнитель, описание	✅A	✅A
Get edit metadata — какие поля можно менять у задачи	✅A	❌N
Get create metadata — поля, обязательные при создании задачи	✅A	❌N
Get issue transitions — доступные переходы статуса	✅A	✅A
Get transition fields — обязательные поля и значения для перехода	✅A	❌N
Get issue changelog — история изменений полей и статусов	✔P	❌N
Read issue comments — полная лента комментариев задачи	✅A	✔P
Search comments by author — комментарии человека по всем задачам	✔P	✅A
Get issue worklogs — учёт трудозатрат по задаче	✔P	❌N
Issue attachments (metadata) — вложения в составе карточки задачи	✔P	✔P
Download attachment — скачать файл вложения	❌N	❌N
Issue links and subtasks — связи, их типы и подзадачи в составе карточки	✔P	✔P
Get remote links — ссылки задачи на Confluence, PR и внешние ресурсы	✅A	❌N
Watchers and votes — подписчики и голоса	✅A	❌N
Search issues (JQL) — выборка задач запросом JQL	✅A	✅A
JQL autocomplete — подсказки полей и значений JQL	✅A	❌N
Get projects — проекты Jira	✅A	❌N
Project versions and components — версии и компоненты проекта	✅A	❌N
Project roles — роли проекта и участники	✔P	❌N
Get my permissions — что мне разрешено в проекте или задаче	✅A	❌N
Get statuses — справочник статусов инстанса	✅A	✅A
Status categories — категории статусов (To Do, In Progress, Done)	✅A	❌N
Get resolutions — справочник резолюций	✅A	❌N
Get priorities — справочник приоритетов	✅A	❌N
Get issue types — типы задач	✅A	❌N
Get fields — описание полей и их схем	✅A	❌N
Get saved filters — сохранённые JQL-фильтры	✔P	❌N
Get dashboards — дашборды и их элементы	✔P	❌N
Agile boards and sprints — доски и спринты	❓?	❌N
Agile backlog and epics — бэклог и эпики	❓?	❌N
# Get issue worklogs и Get issue changelog: только текущая страница сервера;
# при total больше числа возвращённых строк результат неполон.
# jira-author-comments: ✔P; окно по updated задачи, полный скан кандидатов
# ограничен max_issues, snapshot не гарантируется; grep идёт через killable
# helper с таймаутом, но частичность окна сохраняется.
# Jira field metadata: только чтение экранов, не действия; createmeta 8.22
# помечен deprecated, поведение на живом сервере не проверено.
# Registered Jira operations add user get, one-page assignable-user search,
# mypermissions, field list, project roles (names/detail URLs, not members),
# JQL autocomplete, favourite filters only, and one-page dashboards.
# Live tests and target-version checks remain unverified.

## Confluence

Функционал	AW	BBK
Get page — страница: заголовок, тело storage, версия, пространство	✅A	✅A
Render page as Markdown — читаемый Markdown из storage XHTML	✅A	✅A
Get raw storage — исходное XHTML-тело страницы	✅A	✅A
Get rendered HTML view — HTML-представление для чтения	❌N	❌N
Get page by title — найти страницу по точному заголовку	✅A	❌N
Page history and versions — список версий и их авторы	✔P	❌N
Get version detail — конкретная версия страницы	✅A	❌N
List child pages — прямые дочерние страницы	✅A	✅A
List descendants — все потомки страницы	❌N	❌N
Read comments — комментарии страницы	✔P	❌N
Page attachments — вложения страницы	✔P	❌N
Page labels — метки страницы	✔P	❌N
Page restrictions — ограничения доступа к странице	❌N	❌N
Content properties — пользовательские свойства контента	✔P	❌N
Convert content body — storage в view или экспорт (POST, без записи)	✔P	❌N
Search with CQL — поиск страниц запросом CQL	✅A	✅A
List spaces — пространства Confluence	✅A	✅A
Get space — описание и метаданные пространства	✅A	❌N
Get space content — страницы пространства списком	✔P	❌N
Blogposts — блог-посты пространства	❌N	❌N
Templates and blueprints — шаблоны страниц	❓?	❌N
Confluence users and groups — пользователи и группы	✔P	❌N
Long task status — статус фоновой операции	❓?	❌N
# Page history: не полный список версий. page-version: сочетание
# status=historical и version не проверено на живом сервере.
# Registered Confluence operations add exact-title lookup, one-page space
# content, content properties, content attachments/children, and one-user
# lookup. Groups, rendered HTML, blogposts, descendants, and long tasks remain
# unimplemented or not assessed; no live verification.
# convert-body: semantic read-only POST, stdin UTF-8, pairs storage→view/
# export_view/styled_view/editor and editor→storage; response 8 MiB, input
# unbounded; macros/plugins may have effects; route/target version unverified.

## Bitbucket

Функционал	AW	BBK
List projects — проекты Bitbucket	✅A	✅A
Get project — один проект по ключу	✅A	❌N
List repositories — репозитории проекта	✅A	✅A
Get repository — метаданные одного репозитория	✅A	❌N
Find repositories — поиск репозитория по имени или slug	✅A	✅A
List branches — ветки репозитория, включая признак основной	✅A	✅A
Get branch — одна ветка по точному имени	✅A	✅A
List commits — история коммитов с фильтром по пути	✅A	✅A
Get commit — один коммит по хешу	✅A	✅A
Last modified — когда последний раз менялся репозиторий или путь	✅A	❌N
Commit changes — файлы, изменённые коммитом	✅A	✅A
Commit diff — diff коммита целиком или по путям	✅A	✅A
Commit comments — комментарии к коммиту	✔P	❌N
Compare refs — diff между двумя ветками или коммитами	✔P	❌N
Get file at ref — точные байты файла на ветке или коммите	✅A	✅A
List files — все пути файлов репозитория	✅A	✅A
Browse directory — содержимое каталога	✅A	✅A
Blame — автор и дата по строкам файла	✅A	✅A
Repository participants — кто участвует в репозитории	✔P	❌N
List tags — теги репозитория	✅A	❌N
Get tag — один тег	✅A	❌N
Related repositories and forks — связанные репозитории и форки	✔P	❌N
Repository archive — архив репозитория на ref	❌N	✔P
Search all projects — полный сквозной поиск по коду всех видимых проектов (плагин поиска, не core REST)	✅A	✅A
Search in project — поиск по коду внутри одного проекта (плагин поиска)	✅A	✅A
Search in repository — поиск по коду внутри одного репозитория (плагин поиска)	✅A	✅A
Regex grep in repository — regex по содержимому репозитория на любой ветке	✔P	✅A
Scan repositories by extension — где есть файлы расширения	✔P	✅A
List pull requests — PR репозитория по состоянию	✅A	✅A
My pull requests — PR, где я автор или ревьюер	✅A	✅A
Get pull request — карточка PR: ветки, автор, состояние	✅A	✅A
PR changed files — файлы, изменённые PR	✅A	✅A
PR diff (whole) — diff всего PR	✔P	✅A
PR diff (one file) — diff одного файла PR	✅A	✅A
PR diff fallback — добор diff при заявленном усечении	✅A	✅A
PR comments — комментарии и треды PR	✅A	✅A
PR commits — коммиты PR	✅A	✅A
PR merge status — можно ли слить PR и какие есть конфликты	✅A	❌N
PR activity — лента активности PR	✔P	❌N
PR participants — участники и роли PR	❌N	❌N
PR tasks — задачи-блокеры PR	✔P	❌N
Build status — статусы сборки коммита	❌N	❌N
Default reviewers — ревьюеры по умолчанию	❌N	❌N
Repository attachments — вложения репозитория	✔P	✔P
User profile — профиль пользователя Bitbucket	✅A	✔P
Recent repositories — недавно открытые репозитории пользователя	✔P	❌N
Inbox — входящие pull requests	❌N	❌N
Markup preview — рендер разметки Bitbucket	❌N	❌N
# Scan repositories by extension: реализовано, но ✔P до сравнимых тестов BBK
# и подтверждения на живом сервере.
# grep-repo: ✔P до проверки на живом сервисе; без PATTERN — список путей без
# чтения файлов, иначе известные текстовые суффиксы по умолчанию, ref закреплён
# на полном коммите, timeout кооперативный.
# Compare refs: ✔P; compare-changes/compare-commits дают одну страницу файлов
# или коммитов, не diff и не полное сравнение.
# attachment-get: ✔P; один GET на настроенный origin, base64 JSON, по умолчанию
# 8 MiB, превышение — ошибка без усечения, локальной записи нет; маршрут
# BBK-observed, документация 5.10 и совместимость на живом сервере не проверены.
# Registered Bitbucket operations add one-page commit comments, participants,
# forks, related repositories, PR activity, single-task get, user profile/list,
# and recent repositories. PR participant listing and PR task listing remain
# absent; no live verification.

## Cross-cutting and composite

Функционал	AW	BBK
Cross-product search — один запрос по трём продуктам (не REST)	✔P	✅A
PR review packet — тикет + PR + diff + проверки (не REST)	✔P	✅A
Raw GET passthrough — произвольный read-only GET к инстансу	🚫X	✔P
Cursor and offset pagination — постраничное чтение без частичной выдачи	✅A	✅A
Bearer/PAT authentication — токен из окружения, не из аргументов	✅A	✅A
Whoami / identity check — проверка, кто я, по трём продуктам	✔P	✅A
# Federated find: один CLI-вызов на три продукта; каждый продукт ограничен
# per-term лимитом, Bitbucket ищет только индексированный код, полнота не
# гарантируется.
# PR review packet: ✔P; ticket enrichment, links, Markdown и regex-heuristics
# реализованы, но эвристики ограничены, Jira опциональна, mixed revisions
# возможны, raw diff не доказан как полный, live-проверки нет.
# Static operations registry: 40 фиксированных GET по allowlist; это не
# произвольный passthrough и не покрытие всего REST. Реестр покрывает Jira
# watchers/votes, project versions/components, Confluence space get и Bitbucket
# project/repository get; один ответ без пагинации, live-проверки нет.
# Whoami: ✔P до проверки реального parity; Bitbucket подтверждает только
# аутентифицированный dashboard, не личность; Confluence отклоняет anonymous.

## Verified remaining major non-admin gaps

Source-verified against the current adapters and static registry; not executed
or live-verified:

- Jira attachment binary download: only attachment metadata is exposed, not the
  content bytes.
- Confluence attachment binary download: only one-page metadata/list reads are
  exposed, not file bytes.
- Bitbucket markup preview is not implemented. Confluence content-body
  conversion is implemented partially by `convert-body`, but remains unverified
  on a live server; installed macros/plugins may have effects.
- Jira user groups and Confluence rendered HTML remain unimplemented.
- Bitbucket build status, default reviewers, inbox, PR participant listing, and
  PR task listing remain unimplemented; only a single task get exists.
- Non-administrative plugin/agile reads are in scope where available. Routes
  not yet assessed remain `❓?` unknown until their semantics and version are
  established.

## Сводка

Раздел	Строк	AW ✅A	AW ✔P	AW ⌛D	AW ❌N	AW 🚫X	AW ❓?	BBK ✅A	BBK ✔P	BBK ⌛D	BBK ❌N
Jira	36	21	10	0	2	0	3	7	4	0	25
Confluence	23	9	8	0	4	0	2	6	0	0	17
Bitbucket	48	31	11	0	6	0	0	27	3	0	18
Cross-cutting and composite	6	2	3	0	0	1	0	5	1	0	0
