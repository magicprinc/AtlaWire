# Jira Server 8.22.2 — REST, JQL, грабли

Инстанс: `https://jira.example.com`, версия 8.22.2 (build 822002), `deploymentType: Server`.

## Частые вызовы

| задача | вызов |
|---|---|
| кто я | `GET /rest/api/2/myself` → `name`, `displayName` |
| поиск | `GET /rest/api/2/search?jql=<encoded>&maxResults=50&fields=summary,status,…` |
| задача | `GET /rest/api/2/issue/{KEY}?expand=renderedFields` (HTML описания и комментариев) |
| комментарий | `POST /rest/api/2/issue/{KEY}/comment` `{"body": "<wiki-разметка>"}` |
| правка комментария | `PUT /rest/api/2/issue/{KEY}/comment/{id}` `{"body": …}` |
| список статусов | `GET /rest/api/2/status` |

В пакете: `bbk.jql()`, `bbk.rows()`, `bbk.mine()`, `bbk.issue()`, `bbk.issue_md()`,
`bbk.statuses()`, `bbk.jira_me()`; запись — `bbk.write.jira_comment()`.

## Последние комментарии человека

`GET /rest/api/2/search?jql=updated >= -90d ORDER BY updated DESC&fields=summary,comment`
возвращает комментарии прямо в результатах поиска — один проход вместо запроса на каждую задачу.
Фильтр по автору (`author.name`) и сортировка по `created` — на клиенте; пагинация `startAt`
прекращается, когда набрано N комментариев и следующие задачи заведомо старше. Если у задачи
комментариев больше, чем вернул поиск (`comment.total > len(comments)`), тред дочитывается через
`GET /rest/api/2/issue/{KEY}/comment`.

Реализация: `bbk.comments()`, CLI — `bbk comments <user|ФИО> --days N --limit K [--grep RE]
[--project KEY]`; ссылка в строке ведёт на комментарий (`?focusedCommentId=…#comment-…`).

`GET /rest/api/2/user/search?username=<term>` ищет по логину и латинскому displayName;
кириллические ФИО транслитерируются (`Воробьев` → `vorobyev`, `Батурин` → `baturin`).

Оговорки (проверены ревью):
- `--days` ограничивает **дату обновления задачи**, а не дату комментария: старый комментарий
  в недавно обновлённой задаче попадёт в выборку.
- Сравнение времени — по моментам (`datetime` + offset), иначе `.100` и `.900` в одну секунду
  или `01:45+0100` против `01:15+0000` дают неверный порядок и преждевременную остановку.
- Исчерпание бюджета (`max_issues`, страницы треда) не маскируется: печатается предупреждение,
  `--strict` превращает его в ошибку.
- Неоднозначное ФИО (несколько совпадений без точного логина) — ошибка со списком логинов.
- `--json` печатает только JSON в stdout; шапка `<ФИО> (<логин>)` идёт в stderr.

## JQL-рецепты

```
assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC
assignee = currentUser() AND status = "In Progress"
project = PLAT AND created >= -7d ORDER BY created DESC
reporter = currentUser() AND status = "Готово к деплою"
text ~ "деплой" AND project = PLAT
```

**Имена статусов — не угадывать.** В этом инстансе одновременно живут английские и русские
статусы: `In Progress`, `In development`, `В работе`, `Готово к деплою`, `Pending`,
`RETURNED`, `На согласовании ОТ` и др. — всего 50+. Берутся из `bbk.statuses()`; литерально
«in-processing» не существует, ближайшее — `In Progress`.

`statusCategory != Done` удобнее перечисления: закрывает `Closed`, `Done`, `Закрыта`,
`Resolved`, `Отменена` и прочие «завершённые» одним условием.

## Факты по задаче PLAT-376 (пример на будущее)

`fields.updated` — ISO-время; `renderedFields.description` — HTML; сам `fields.description` —
wiki-разметка. Конвертация: `bbk.issue_md(key)` (HTML через markdownify) или
`bbk.issue_md(key, wiki=True)` (wiki → md, компактнее: 2 869 Б против 3 948 Б на PLAT-3901).

## PAT для Jira

Создаётся `POST /rest/pat/latest/tokens` с `expirationDuration` — **целым числом дней**;
токен приходит в `rawToken` один раз. Подробности и отзыв — `../auth.md`.

## Грабли

- Анонимный доступ: `serverInfo` → 200, задача → 401. Bitbucket-PAT → 403. Нужен Jira PAT.
- `Negotiate`/Kerberos не работает (домена нет), `curl --negotiate` даёт 401.
- Тело ошибки не печатать: может содержать заголовки запроса.
- Расширение `renderedFields` резко увеличивает ответ; для списков его не запрашивать.
