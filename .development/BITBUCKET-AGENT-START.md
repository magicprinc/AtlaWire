# AGENT-START — с чего начать другому агенту

Короткая инструкция: что использовать, что убрать, где смотреть детали.

## 1. Убрать Bitbucket MCP (он больше не нужен)

Признак: в `~/.dsh/profiles/web/cordis.patch.yml` есть `serverName: bitbucket` или `id: mcp-bitbucket`,
в `~/.config/opencode/opencode.json` — `mcp.servers.bitbucket`.

```powershell
# 1) конфиг DSH: блок заменить комментарием-надгробием (как mcp-kurlo/mcp-bitbucket удалены ранее)
#    обязательно сделать бэкап: Copy-Item cordis.patch.yml cordis.patch.yml.bak-<дата>
# 2) OpenCode: удалить ключ mcp.servers.bitbucket
# 3) пакет и обвязка:
npm uninstall -g @nexus2520/bitbucket-mcp-server
Remove-Item "$env:USERPROFILE\.local\opt\bitbucket-mcp-diff-fix" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\.local\bin\bb-search*" -Force -ErrorAction SilentlyContinue
# 4) проверить, что профиль грузится:
dsh --profile web --dump-config   # exit 0, записей "id: mcp-" должно остаться 9
```

Все 25 инструментов MCP перенесены в `bbk` — проверка: `python tests/coverage_mcp.py` (25/25).

## 2. Использовать: папка, пакет, скилл

| что | где |
|---|---|
| ** проект** | `d:/zcache/bbk` (в bash — `/d/zcache/bbk`) |
| документация | `d:/zcache/bbk/docs/INDEX.md` — **читать первым** |
| код | `d:/zcache/bbk/bbk` (Python + CLI) |
| индексы знаний | `d:/zcache/bbk/docs/IDX/` (MSSQL, проекты Bitbucket, подключения DVPS, NATS, Kafka, локальные копии, справочник схемы) |
| журнал изменений | `d:/zcache/bbk/logs/` (`CHANGELOG.md`, `notes.md`) |
| скиллы | `bitbucket` (вход: Bitbucket/Jira/Confluence + маршруты), `kafka`, `nats`, `everythingsearch` |
| токены | `~/.config/atlassian/credentials.json`; календарь — `~/.config/google/calendar.b64` |

## 3. Первые три команды

```bash
bbk selftest                 # 33 проверки чтения: живы ли токены и контракты
bbk whoami                   # кто мы для Bitbucket/Jira/Confluence
bbk local <KEY/slug>         # где локальная копия репозитория + возраст коммита
```

Лаунчеры: `~/.local/bin/bbk.cmd` (Windows) и `~/.local/bin/bbk` (bash) ставят `PYTHONPATH` сами. В bash путь переводится через `cygpath -w` (нативный Python понимает только `D:\zcache\bbk` с разделителем `;`).
Если запускаете из Python: `python -m bbk …` из `d:/zcache/bbk`.

## 4. Программы, которые уже настроены

| задача | инструмент |
|---|---|
| Bitbucket/Jira/Confluence | `bbk` (Python-пакет, токены в файле) |
| поиск файлов на диске | `es.exe` (Everything; если `exit 8` — запустить `C:\Program Files\Everything\Everything.exe`) |
| code map и история символов | `basemind` (CLI; `rescan --root <чекаут>`) |
| граф кода | `codebase-memory-mcp cli index_repository --repo-path <path> --mode fast` (+ MCP) |
| Kafka | `kcl` (`-B broker` после подкоманды), `kafkactl` (нужен контекст), kafka-ui API |
| NATS | `nats` (`stream ls/info`), мониторинг `:8222` |
| MSSQL | DBX MCP (`mssql-TEST.devinotest.local`, копия прода) |
| ревью PR | `bbk review <url> --refresh --out review.md` |

## 5. Правила

- **Секреты** — только в `~/.config/atlassian` и `~/.config/google`; в проект, доки и логи не писать.
  `bbk.redact()` вычищает известные токены из текста ошибок.
- **Пишущие операции** — через `bbk.write.*`: они пишут в `logs/` **до** запроса и принимают `dry_run`.
  `BBK_READ_ONLY=1` запрещает любые изменения.
- **Kafka/NATS читать только с ограничением**: окно времени/`max_messages`, не менять offsets.
- **Локальные копии могут быть старыми** (`bbk local` печатает возраст): перед выводами о актуальном
  коде — `git fetch`/`pull` или запрос к Bitbucket.
- **Не угадывать** поведение серверов: грабли собраны в `docs/bitbucket/findings.md`,
  `docs/nats.md`, `docs/kafka.md`, `docs/grafana.md`.
- Индексы — снимки: обновление командой из соответствующего `docs/*.md`
  (`tools/build_*_index.py`, `git pull` + `basemind rescan`).
- **Нагрузка на внутренние ресурсы** (Bitbucket, Jira, Grafana). Два разных правила:
  1) *регулярный опрос* в течение дня — **не чаще одного запроса в 10 секунд** (наш такт вообще 10 минут +
     джиттер, то есть значительно реже);
  2) *разовый сбор данных* — **не больше пяти потоков**, каждый делает запросы по одному
     (`--workers 5`). Замер: 40 репозиториев за 5 секунд, полный проход 551 ≈ 1–2 минуты.
  Не держать сервис под непрерывной нагрузкой часами — вот чего избегаем.
- **Сначала читать, потом изменять.** В проекте параллельно работают другие агенты: перед правкой
  перечитывайте файл целиком (он мог измениться), делайте минимальный точечный диф, не
  переформатируйте чужие строки. Если содержимое не совпало с ожидаемым — остановитесь.
- **Странные изменения — только уведомлять владельца.** Неожиданный конфликт `git pull`,
  чужие правки, непонятный диф, версия, которой нет в Maven, — показать факты и ждать решения;
  самостоятельно не «приводить в порядок».
- **Коммиты делает владелец.** Агент не выполняет `git commit`, `git add` под коммит, `rebase`,
  `push` — только предлагает текст коммит-сообщения.

## 6. Что читать дальше (по 1 файлу на тему)

`docs/INDEX.md` (карта) → `docs/bitbucket/findings.md` (грабли Bitbucket 5.10) →
`docs/review.md` (ревью PR) → `docs/dvps.md` (куда сервис подключается) →
`docs/IDX/README.md` (индексы и справочник схемы) → `docs/calendar.md`, `docs/chat.md` (встречи, обсуждения).
