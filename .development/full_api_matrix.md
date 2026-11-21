# Full read-only API matrix

Матрица read-only возможностей Atlassian REST API: Jira, Confluence, Bitbucket.
Назначение — оценить, какие возможности стоит реализовать в AtlaWire.

Формат: TSV. Столбцы разделены символом табуляции: `Функционал`, `AW`, `BBK`.
Строки, начинающиеся с `#`, — служебные заголовки, их пропускает TSV-парсер.

Область:
- включено только чтение: карточки, поиск, история, файлы, PR, справочники;
- исключены любые изменения: создание, правка, удаление, переходы, слияния,
  комментарии, ветки, вложения;
- исключено администрирование и поддержка работы систем: аудит, лицензии,
  почта, кластер, application properties, webhooks, схемы прав, экраны,
  поля, workflow-конфигурация, резервное копирование.

Обозначения:
- ✅A — реализовано полностью;
- ✔P — реализовано частично (подмножество, ограничение охвата или только
  внутренний API без команды);
- ⌛D — отложено: кандидат на реализацию, приоритет не зафиксирован;
- ❌N — вне области.

Снимок: AtlaWire 6c7657b, BBK — локальный чекаут на 2026-11-21.
Статусы записи BBK в матрицу не входят: это отдельный, отложенный класс.

## Jira

Функционал	AW	BBK
Get server info — версия и базовые сведения об инстансе	❌N	❌N
Get current user (myself) — кто я: логин, имя, часовой пояс	✅A	✅A
Get user — профиль пользователя по ключу или логину	❌N	✔P
Search users — поиск пользователей по имени или логину	⌛D	✅A
Get user groups — группы, в которых состоит пользователь	❌N	❌N
Get issue — карточка задачи: поля, статус, исполнитель, описание	✅A	✅A
Get edit metadata — какие поля можно менять у задачи	❌N	❌N
Get issue transitions — доступные переходы статуса	✅A	✅A
Get issue changelog — история изменений полей и статусов	⌛D	❌N
Read issue comments — полная лента комментариев задачи	✅A	✔P
Search comments by author — комментарии человека по всем задачам	⌛D	✅A
Get issue worklogs — учёт трудозатрат по задаче	⌛D	❌N
Issue attachments (metadata) — вложения в составе карточки задачи	✔P	✔P
Download attachment — скачать файл вложения	❌N	❌N
Issue links and subtasks — связи и подзадачи в составе карточки	✔P	✔P
Watchers and votes — подписчики и голоса	❌N	❌N
Search issues (JQL) — выборка задач запросом JQL	✅A	✅A
JQL autocomplete — подсказки полей и значений JQL	❌N	❌N
Get projects — проекты Jira	❌N	❌N
Project versions and components — версии и компоненты проекта	❌N	❌N
Project roles — роли проекта и участники	❌N	❌N
Get statuses — справочник статусов инстанса	✅A	✅A
Status categories — категории статусов (To Do, In Progress, Done)	❌N	❌N
Get resolutions — справочник резолюций	❌N	❌N
Get priorities — справочник приоритетов	❌N	❌N
Get issue types — типы задач	❌N	❌N
Get fields — описание полей и их схем	❌N	❌N
Get saved filters — сохранённые JQL-фильтры	❌N	❌N
Get dashboards — дашборды и их элементы	❌N	❌N
Agile boards and sprints — доски и спринты	❌N	❌N
Agile backlog and epics — бэклог и эпики	❌N	❌N

## Confluence

Функционал	AW	BBK
Get page — страница: заголовок, тело storage, версия, пространство	✅A	✅A
Render page as Markdown — читаемый Markdown из storage XHTML	✅A	✅A
Get raw storage — исходное XHTML-тело страницы	⌛D	✅A
Get rendered HTML view — HTML-представление для чтения	❌N	❌N
Get page by title — найти страницу по точному заголовку	❌N	❌N
Page history and versions — список версий и их авторы	⌛D	❌N
Get version detail — конкретная версия страницы	❌N	❌N
List child pages — прямые дочерние страницы	✅A	✅A
List descendants — все потомки страницы	❌N	❌N
Read comments — комментарии страницы	⌛D	❌N
Page attachments — вложения страницы	❌N	❌N
Page labels — метки страницы	❌N	❌N
Page restrictions — ограничения доступа к странице	❌N	❌N
Content properties — пользовательские свойства контента	❌N	❌N
Search with CQL — поиск страниц запросом CQL	✅A	✅A
List spaces — пространства Confluence	✅A	✅A
Get space — описание и метаданные пространства	❌N	❌N
Blogposts — блог-посты пространства	❌N	❌N
Templates and blueprints — шаблоны страниц	❌N	❌N
Confluence users and groups — пользователи и группы	❌N	❌N
Long task status — статус фоновой операции	❌N	❌N

## Bitbucket

Функционал	AW	BBK
List projects — проекты Bitbucket	✅A	✅A
Get project — один проект по ключу	❌N	❌N
List repositories — репозитории проекта	✅A	✅A
Get repository — метаданные одного репозитория	❌N	❌N
Find repositories — поиск репозитория по имени или slug	✅A	✅A
List branches — ветки репозитория	✅A	✅A
Get branch — одна ветка по точному имени	✅A	✅A
List commits — история коммитов с фильтром по пути	✅A	✅A
Get commit — один коммит по хешу	✅A	✅A
Commit changes — файлы, изменённые коммитом	✅A	✅A
Commit diff — diff коммита целиком или по путям	✅A	✅A
Compare refs — diff между двумя ветками или коммитами	❌N	❌N
Get file at ref — точные байты файла на ветке или коммите	✅A	✅A
List files — все пути файлов репозитория	✅A	✅A
Browse directory — содержимое каталога	✅A	✅A
Blame — автор и дата по строкам файла	✅A	✅A
List tags — теги репозитория	❌N	❌N
Get tag — один тег	❌N	❌N
Repository archive — архив репозитория на ref	❌N	✔P
Search all projects — полный сквозной поиск по коду всех видимых проектов (плагин поиска, не core REST)	✅A	✅A
Search in project — поиск по коду внутри одного проекта (плагин поиска)	✅A	✅A
Search in repository — поиск по коду внутри одного репозитория (плагин поиска)	✅A	✅A
Regex grep in repository — regex по содержимому репозитория на любой ветке	⌛D	✅A
Scan repositories by extension — где есть файлы расширения	⌛D	✅A
List pull requests — PR репозитория по состоянию	✅A	✅A
My pull requests — PR, где я автор или ревьюер	✅A	✅A
Get pull request — карточка PR: ветки, автор, состояние	✅A	✅A
PR changed files — файлы, изменённые PR	✅A	✅A
PR diff (whole) — diff всего PR	✔P	✅A
PR diff (one file) — diff одного файла PR	✅A	✅A
PR diff fallback — добор diff при заявленном усечении	⌛D	✅A
PR comments — комментарии и треды PR	✅A	✅A
PR commits — коммиты PR	✅A	✅A
PR activity — лента активности PR	❌N	❌N
PR participants — участники и роли PR	❌N	❌N
PR tasks — задачи-блокеры PR	❌N	❌N
Build status — статусы сборки коммита	❌N	❌N
Default reviewers — ревьюеры по умолчанию	❌N	❌N
Repository attachments — вложения репозитория	❌N	✔P
User profile — профиль пользователя Bitbucket	❌N	✔P
Inbox — входящие pull requests	❌N	❌N
Markup preview — рендер разметки Bitbucket	❌N	❌N

## Cross-cutting and composite

Функционал	AW	BBK
Cross-product search — один запрос по трём продуктам (не REST)	❌N	✅A
PR review packet — тикет + PR + diff + проверки (не REST)	❌N	✅A
Raw GET passthrough — произвольный read-only GET к инстансу	⌛D	✔P
Cursor and offset pagination — постраничное чтение без частичной выдачи	✅A	✅A
Bearer/PAT authentication — токен из окружения, не из аргументов	✅A	✅A

## Сводка

Раздел	Строк	AW ✅A	AW ✔P	AW ⌛D	AW ❌N	BBK ✅A	BBK ✔P	BBK ⌛D	BBK ❌N
Jira	31	6	2	4	19	7	4	0	20
Confluence	21	5	0	3	13	6	0	0	15
Bitbucket	42	23	1	3	15	27	3	0	12
Cross-cutting and composite	5	2	0	1	2	4	1	0	0
