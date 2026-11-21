# Confluence → Markdown: Storage Format и конвертер

Markdown Confluence **не отдаёт**. Доступны `body.storage` (XHTML с макросами `<ac:*>`, `<ri:*>`)
и `body.view` (готовый HTML с атлассиановскими CSS/JS-обёртками). Берём storage и конвертируем.

## Почему свой конвертер, а не общий

В `body.storage` код лежит в `<ac:structured-macro ac:name="code">` с
`<ac:parameter ac:name="language">python</ac:parameter>` и CDATA в `<ac:plain-text-body>`.
Общий конвертер это теряет: на тестовом фрагменте generic markdownify выдал код **без
отступов и без fence**, вытащил наружу параметры макросов (`python`, `Green`, `IN PROGRESS`)
и потерял цель ссылки (`Read  first.`).

Проверено: markdownify 1.2.3 **вызывает** `convert_ac_structured_macro` для тега
`<ac:structured-macro>` — bs4 отдаёт имя с двоеточием, а markdownify строит имя метода из него.
Реестр не нужен. Реализация: `bbk.md.ConfluenceConverter`.

| элемент Storage Format | результат в Markdown |
|---|---|
| `code` / `noformat` | ```` ```python ```` + текст с сохранёнными отступами |
| `info` / `note` / `warning` / `tip` / `panel` | `> **Заголовок:**` + цитата |
| `expand` | `### Заголовок` + содержимое |
| `status` | `` `[IN PROGRESS]` `` |
| `ac:link` c `ri:page` | `[Текст](confluence:Название страницы)` — цель для следующего запроса |
| `ac:link`, где видимый текст — URL | `[url](url)` — иначе адрес теряется |
| `ac:image` c `ri:attachment` | `![file.png](attachment:file.png)` |
| `ri:user` | `@username` |
| неизвестный макрос | его rich-text-body, без потерь текста |

## Выбор конвертера — с замерами

Одна и та же страница (73 077 51, «Сервисы в кластере», 93 496 Б storage XHTML):

| вариант | байт | остатки inline HTML | таблицы |
|---|---|---|---|
| исходный storage | 93 496 | 1 441 | 1 |
| `pandoc -t gfm` | 60 936 | 517 | **схлопнуты в вертикальный список** |
| `pandoc -t markdown` | 52 446 | 0 | **схлопнуты** |
| markdownify (наш конвертер) | **45 866** | 0 | **373 строки pipe-таблицы, ссылки целы** |

Вывод: по умолчанию markdownify; pandoc — только для «прозаических» страниц с глубокой
вложенностью (`--pandoc` в старом скрипте, в пакете — `bbk.md.html_to_md` для HTML Jira).

## Ограничения

- Таблицы с `rowspan`/`colspan` в pipe-таблицу не превращаются: ячейки могут сместиться,
  `bbk.confluence_to_md` об этом предупреждает (на странице «Сервисы в кластере» это видно
  на строках config-server).
- `ac:image` без `ri:attachment`/`ri:url` даёт пустую строку (так в исходном рецепте).

## Прочее

- Дочерние страницы — `GET /rest/api/content/{id}/child/page`; поиск — CQL:
  `GET /rest/api/search?cql=…` (`text ~ "…"`, `space = KEY`, `title ~ "…"`, `ancestor = <id>`).
- Для комментария к странице `bbk.write.confluence_comment` использует `POST /rest/api/content`
  с `type=comment` и `container.id` родительской страницы. Запрос
  `POST /rest/api/content/{id}/child/comment` возвращал 405 в
  [проверке `bbk`](../bitbucket/findings.md). В AtlaWire этот сценарий ещё не проверен.
- Правка страницы требует bump версии, иначе 409.
- `GET /rest/api/content/{id}?expand=body.storage,version,space,ancestors` — один запрос на всё
  нужное; `body.view` не запрашивать (в нём только UI-мусор).
