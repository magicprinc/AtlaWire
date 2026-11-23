"""Generate .development/full_api_matrix.md as sectioned TSV."""

from collections import Counter
from pathlib import Path

A, P, D, N = "✅A", "✔P", "⌛D", "❌N"

SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "Jira",
        [
            ("Get server info — версия и базовые сведения об инстансе", N, N),
            ("Get current user (myself) — кто я: логин, имя, часовой пояс", A, A),
            ("Get user — профиль пользователя по ключу или логину", N, P),
            ("Search users — поиск пользователей по имени или логину", D, A),
            ("Search assignable users — кому можно назначить задачу", D, N),
            ("Get user groups — группы, в которых состоит пользователь", N, N),
            ("Get issue — карточка задачи: поля, статус, исполнитель, описание", A, A),
            ("Get edit metadata — какие поля можно менять у задачи", N, N),
            ("Get create metadata — поля, обязательные при создании задачи", N, N),
            ("Get issue transitions — доступные переходы статуса", A, A),
            ("Get transition fields — обязательные поля и значения для перехода", D, N),
            ("Get issue changelog — история изменений полей и статусов", D, N),
            ("Read issue comments — полная лента комментариев задачи", A, P),
            ("Search comments by author — комментарии человека по всем задачам", D, A),
            ("Get issue worklogs — учёт трудозатрат по задаче", D, N),
            ("Issue attachments (metadata) — вложения в составе карточки задачи", P, P),
            ("Download attachment — скачать файл вложения", N, N),
            ("Issue links and subtasks — связи, их типы и подзадачи в составе карточки", P, P),
            ("Get remote links — ссылки задачи на Confluence, PR и внешние ресурсы", D, N),
            ("Watchers and votes — подписчики и голоса", N, N),
            ("Search issues (JQL) — выборка задач запросом JQL", A, A),
            ("JQL autocomplete — подсказки полей и значений JQL", N, N),
            ("Get projects — проекты Jira", N, N),
            ("Project versions and components — версии и компоненты проекта", N, N),
            ("Project roles — роли проекта и участники", N, N),
            ("Get my permissions — что мне разрешено в проекте или задаче", D, N),
            ("Get statuses — справочник статусов инстанса", A, A),
            ("Status categories — категории статусов (To Do, In Progress, Done)", N, N),
            ("Get resolutions — справочник резолюций", N, N),
            ("Get priorities — справочник приоритетов", N, N),
            ("Get issue types — типы задач", N, N),
            ("Get fields — описание полей и их схем", N, N),
            ("Get saved filters — сохранённые JQL-фильтры", N, N),
            ("Get dashboards — дашборды и их элементы", N, N),
            ("Agile boards and sprints — доски и спринты", N, N),
            ("Agile backlog and epics — бэклог и эпики", N, N),
        ],
    ),
    (
        "Confluence",
        [
            ("Get page — страница: заголовок, тело storage, версия, пространство", A, A),
            ("Render page as Markdown — читаемый Markdown из storage XHTML", A, A),
            ("Get raw storage — исходное XHTML-тело страницы", D, A),
            ("Get rendered HTML view — HTML-представление для чтения", N, N),
            ("Get page by title — найти страницу по точному заголовку", N, N),
            ("Page history and versions — список версий и их авторы", D, N),
            ("Get version detail — конкретная версия страницы", N, N),
            ("List child pages — прямые дочерние страницы", A, A),
            ("List descendants — все потомки страницы", N, N),
            ("Read comments — комментарии страницы", D, N),
            ("Page attachments — вложения страницы", N, N),
            ("Page labels — метки страницы", N, N),
            ("Page restrictions — ограничения доступа к странице", N, N),
            ("Content properties — пользовательские свойства контента", N, N),
            ("Convert content body — storage в view или экспорт (POST, без записи)", N, N),
            ("Search with CQL — поиск страниц запросом CQL", A, A),
            ("List spaces — пространства Confluence", A, A),
            ("Get space — описание и метаданные пространства", N, N),
            ("Get space content — страницы пространства списком", N, N),
            ("Blogposts — блог-посты пространства", N, N),
            ("Templates and blueprints — шаблоны страниц", N, N),
            ("Confluence users and groups — пользователи и группы", N, N),
            ("Long task status — статус фоновой операции", N, N),
        ],
    ),
    (
        "Bitbucket",
        [
            ("List projects — проекты Bitbucket", A, A),
            ("Get project — один проект по ключу", N, N),
            ("List repositories — репозитории проекта", A, A),
            ("Get repository — метаданные одного репозитория", N, N),
            ("Find repositories — поиск репозитория по имени или slug", A, A),
            ("List branches — ветки репозитория, включая признак основной", A, A),
            ("Get branch — одна ветка по точному имени", A, A),
            ("List commits — история коммитов с фильтром по пути", A, A),
            ("Get commit — один коммит по хешу", A, A),
            ("Last modified — когда последний раз менялся репозиторий или путь", D, N),
            ("Commit changes — файлы, изменённые коммитом", A, A),
            ("Commit diff — diff коммита целиком или по путям", A, A),
            ("Commit comments — комментарии к коммиту", N, N),
            ("Compare refs — diff между двумя ветками или коммитами", N, N),
            ("Get file at ref — точные байты файла на ветке или коммите", A, A),
            ("List files — все пути файлов репозитория", A, A),
            ("Browse directory — содержимое каталога", A, A),
            ("Blame — автор и дата по строкам файла", A, A),
            ("Repository participants — кто участвует в репозитории", D, N),
            ("List tags — теги репозитория", N, N),
            ("Get tag — один тег", N, N),
            ("Related repositories and forks — связанные репозитории и форки", D, N),
            ("Repository archive — архив репозитория на ref", N, P),
            ("Search all projects — полный сквозной поиск по коду всех видимых проектов (плагин поиска, не core REST)", A, A),
            ("Search in project — поиск по коду внутри одного проекта (плагин поиска)", A, A),
            ("Search in repository — поиск по коду внутри одного репозитория (плагин поиска)", A, A),
            ("Regex grep in repository — regex по содержимому репозитория на любой ветке", D, A),
            ("Scan repositories by extension — где есть файлы расширения", D, A),
            ("List pull requests — PR репозитория по состоянию", A, A),
            ("My pull requests — PR, где я автор или ревьюер", A, A),
            ("Get pull request — карточка PR: ветки, автор, состояние", A, A),
            ("PR changed files — файлы, изменённые PR", A, A),
            ("PR diff (whole) — diff всего PR", P, A),
            ("PR diff (one file) — diff одного файла PR", A, A),
            ("PR diff fallback — добор diff при заявленном усечении", D, A),
            ("PR comments — комментарии и треды PR", A, A),
            ("PR commits — коммиты PR", A, A),
            ("PR merge status — можно ли слить PR и какие есть конфликты", D, N),
            ("PR activity — лента активности PR", N, N),
            ("PR participants — участники и роли PR", N, N),
            ("PR tasks — задачи-блокеры PR", N, N),
            ("Build status — статусы сборки коммита", N, N),
            ("Default reviewers — ревьюеры по умолчанию", N, N),
            ("Repository attachments — вложения репозитория", N, P),
            ("User profile — профиль пользователя Bitbucket", N, P),
            ("Recent repositories — недавно открытые репозитории пользователя", N, N),
            ("Inbox — входящие pull requests", N, N),
            ("Markup preview — рендер разметки Bitbucket", N, N),
        ],
    ),
    (
        "Cross-cutting and composite",
        [
            ("Cross-product search — один запрос по трём продуктам (не REST)", N, A),
            ("PR review packet — тикет + PR + diff + проверки (не REST)", N, A),
            ("Raw GET passthrough — произвольный read-only GET к инстансу", D, P),
            ("Cursor and offset pagination — постраничное чтение без частичной выдачи", A, A),
            ("Bearer/PAT authentication — токен из окружения, не из аргументов", A, A),
        ],
    ),
]

HEADER = """# Full read-only API matrix

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
"""


def main() -> None:
    lines = [HEADER]
    totals: dict[str, Counter[str]] = {}
    for title, rows in SECTIONS:
        assert all(len(row) == 3 for row in rows)
        assert all(cell in {A, P, D, N} for row in rows for cell in row[1:])
        lines.append(f"## {title}\n")
        lines.append("Функционал\tAW\tBBK")
        for func, aw, bbk in rows:
            assert "\t" not in func
            lines.append(f"{func}\t{aw}\t{bbk}")
        lines.append("")
        totals[title] = (
            len(rows),
            Counter(row[1] for row in rows),
            Counter(row[2] for row in rows),
        )

    lines.append("## Сводка\n")
    lines.append(
        "Раздел\tСтрок\tAW ✅A\tAW ✔P\tAW ⌛D\tAW ❌N"
        "\tBBK ✅A\tBBK ✔P\tBBK ⌛D\tBBK ❌N"
    )
    for title, (total, aw, bbk) in totals.items():
        lines.append(
            f"{title}\t{total}\t{aw[A]}\t{aw[P]}\t{aw[D]}\t{aw[N]}"
            f"\t{bbk[A]}\t{bbk[P]}\t{bbk[D]}\t{bbk[N]}"
        )
    lines.append("")

    target = Path(".development/full_api_matrix.md")
    target.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("wrote", target, target.stat().st_size, "bytes")
    for title, (total, aw, bbk) in totals.items():
        print(title, "rows", total, "AW", dict(aw), "BBK", dict(bbk))


if __name__ == "__main__":
    main()
