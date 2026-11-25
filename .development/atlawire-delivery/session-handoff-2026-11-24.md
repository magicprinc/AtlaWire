# Handoff: сессия анализа AtlaWire — 2026-11-24

Полная выжимка из сессии: что проанализировано, какие решения приняты, что найдено,
что создано и что осталось. Сессия сломалась из-за повреждённой записи tool-call в
истории (API 400 `input[69].name`); содержимое ниже восстановлено по ходу работы.

## 1. Задача пользователя

Проанализировать AtlaWire (улучшенная версия библиотеки/CLI для self-hosted Atlassian
Jira/Confluence/Bitbucket для агентов; read-only; секреты в `$HOME/.config`; старая
библиотека `bbk` в `D:\zcache\bbk` используется успешно), посмотреть, что осталось,
и сделать план исполнителю для публикации на GitHub — без задержек и овер-инжиниринга.

## 2. Состояние репозитория (проверено)

- HEAD `d40d071`, `main == origin/main`, дерево чистое; публичный
  `github.com/magicprinc/AtlaWire`, 109 коммитов.
- Свежая базовая линия (2026-11-24):
  - oфлайн-набор: **662 passed**, 283.5 s, exit 0;
  - `uv lock --check --offline`: **PASS**, 52 пакета, пин `atlassian-python-api==5.0.5`;
  - `ruff check src tests checks` (0.17.6 из lock): **красный**, ~37 находок
    (`FURB188`, `ISC004`, `UP037`, `SIM103/102/114`, `I001`);
  - `ruff check --select S src`: **красный, 4 находки**: S105 в `http.py:24`,
    `operations.py:106`, `pr_review.py:121` (константы-сообщения),
    S603 в `regex_helper.py:298` (subprocess);
  - `ruff format --check`: **40 файлов** требуют переформатирования (включая
    PEP 758 `except A, B:` — валидно для 3.15);
  - `pyright src tests checks`: **224 ошибки**, из них в `src` ровно **1**:
    `pr_review.py:562` `reportReturnType`; остальные — tests/checks;
  - GitHub About: «Complete API access…» — неверно для read-only клиента; темы не заданы.
- Структура: `src/atlawire/` (28 модулей + `manifest.json`), `tests/` (31 spec-файл),
  `checks/` (живые проверки), `docs/` (8 документов), `tools/build_read_manifest.py`,
  `.development/` (HANDOFF, планы, маппинги, инвентарь).
- Пакет: `0.1.0.dev0`, Python ≥3.15, установлен редактируемо; 88 CLI-команд,
  202 зарегистрированные read-операции (Jira 109, Confluence 36, Bitbucket 57).

## 3. Ключевые находки анализа

1. **Потеряны safety-регрессии.** При перезаписи тестового набора в spec-набор
   исчезли решающие регрессии audit-слайсов A–B: no-clobber публикация файла
   (`read --out`, `attachment-get --out`), unsolicited HTTP 206 на бинарном SDK-пути,
   усечённый gzip, JSON `1e999`. Grep по `tests/` пуст; старые файлы архивированы.
2. **`tests/_loopback.py` не существует** (только stale `.pyc`) — старые гейты
   delivery/test-plan ссылаются на архивные файлы.
3. **Теста на `manifest.json` нет**; `tools/build_read_manifest.py` до сих пор читает
   **удалённый** `.planning/…` — генератор сломан после чистки 24.11, надо перевести
   на `.development/{jira,confluence,bitbucket}/mapping-*.json`.
4. **`facade.py` импортируется только из `__init__.py`**, тестов на фасад в текущем
   наборе нет (87 тестов ушли с архивным набором) — фасад экспортируется публично
   без покрытия и дублирует реестр `operations.py`.
5. **Wheel-гейт в прежнем виде неисполним:** `pyproject` задаёт
   `pythonpath = ["src"]`, и `atlawire` импортируется из чекаута из любого cwd —
   проверка установленного колеса требует `PYTHONPATH=<target>` + `-o pythonpath=`
   и assert `atlawire.__file__` в target.
6. **Инвентарь D4:** 252 строки = 202 required + 41 excluded + 9 unresolved;
   после решения об исключении 9 + `application-properties` итог:
   **201 required / 51 excluded / 0 unresolved**.
7. `uv.lock` согласован с `pyproject` (старое замечание снято).
8. Функциональность BBK на уровне библиотеки — ~45 Atlassian-экспортов; у AtlaWire
   отсутствуют часть удобных Python-функций: `page_storage`, `page_md`, `issue_md`
   как функции (сейчас только CLI-флаги), `title`, `url_for`, `jira.url()`,
   `pr_compact`, batch `pr_diff(paths=[...])`, публичные конвертеры Markdown
   (`confluence_to_md`, `wiki_to_md`, `html_to_md`, `jira_issue_to_md`, `render_diff`),
   review-хелперы.
9. `jira2markdown` в прошлой сессии оценивали только «из коробки», конфигурацию
   (`elements.replace`, `usernames`, кеш парсера, LF-нормализация) не проверяли —
   тогда написали свой конвертер; оценку надо перепровести (решение D9/S3.4).

## 4. Решения владельца (зафиксированы)

- **Q01-A / D1:** GitHub-релиз `v0.1.0` + wheel в Release; **без PyPI**;
  **исполнитель НИКОГДА не пушит** — пушит и применяет владелец по чек-листу.
- **Q02 / D2:** два равноправных API — (1) CLI (88 плоских команд + `read <id>` /
  `read-operation` / `operations` / `api-get` / `api-request`), (2) типизированная
  Python-библиотека (модули `atlawire.bitbucket` 41, `jira` 33, `confluence` 17 и др.).
  `facade.AtlaWire` из публичного экспорта убрать (модуль удалить).
- **Q03-A / D3 (усиление):** реестр 202 — рекламируемый инвентарь v0.1.0; сверка
  query-полей с версионированными доками (Jira 8.22 / Confluence 6.6 / Bitbucket 5.10)
  — следующие батчи после релиза; **НО** весь функционал, которым агенты пользовались
  в BBK, реализовать, покрыть тестами и дать удобно **сейчас** (миграция возможна
  сразу).
- **Q04-A / D4:** 9 нерешённых маршрутов исключаются с записанной причиной
  (8 × Bitbucket `/settings/…`, Jira `subtask/move` GET) + `application-properties`.
- **D5:** контент тремя формами одной командой/функцией — оригинал (raw),
  Markdown, JSON.
- **D6:** гибрид транспорта сохраняется: `atlassian-python-api==5.0.5` где подходит +
  собственный строгий `http.py` как abstraction layer; без новых фреймворков.
- **D7:** живые read-only E2E на реальных серверах — обязательная часть релиза
  (согласие дано; только чтение, без вывода payload, синтетические ожидания).
- **D8:** цель — все неадминистративные read-only возможности трёх продуктов;
  unknown ≠ excluded.
- **D9:** BBK не эталон: строгий ревью с вердиктом adopt / keep / improve —
  берём лучшее из двух; контракты AtlaWire строго лучше (truncated/complete,
  бюджеты, case-sensitive ветки, без кешей, отказ redirect/admin) не ослаблять.
- **D10:** ручная настройка кредов (BBK-совместимый файл / env) — единственный путь
  для нового пользователя в v0.1.0; `auth login` — backlog.
- Ограничения: без группированного CLI, MCP, pydantic-моделей для 202 операций,
  кешей, `.env`, новых зависимостей (кроме возможного `jira2markdown` по вердикту S3.4).

## 5. Созданный план релиза

`D:\REPO\github\AtlaWire\.development\atlawire-delivery\github-release-plan.md`
(438 строк, untracked): D1–D10, ограничения против over-engineering, профиль
исполнителя, слайсы:

- **S1** статика зелёная (ruff check/S/format, pyright src, audit §E);
- **S2** поверхность: фасад убран, осознанный экспорт, честный `client_for`,
  no-request тест границы;
- **S2b** восстановление safety-регрессий (no-clobber, 206, gzip, `1e999`, retry);
- **S3** BBK-паритет (disposition-таблица adopt/keep/improve, контент-тройки D5,
  публичные конвертеры, `pr_compact`, batch `pr_diff`, миграционный гайд,
  переоценка `jira2markdown`);
- **S4** заморозка инвентаря (201/51/0), починка генератора, тест манифеста,
  `query_documented` в `--describe`, удаление устаревшей `full_api_matrix.md`;
- **S5** документация (updateHistory/failFast, числа, пример кредов, владельцы фактов);
- **S6** CI GitHub Actions (lint/type/test ubuntu+windows, deps, gitleaks);
- **S7** release-доказательство: version bump → wheel → изолированная установка с
  `PYTHONPATH`-пином → smoke + агентский walk-through → живая read-only матрица → покрытие;
- **S8** квиток верификации (test-plan §5.5) + независимый ревью → CHANGELOG, README,
  HANDOFF, TODO → чек-лист владельца (pushes/tags/About — только владелец);
- Backlog: R2-батчи, выборка ≥90 %, `auth login`, pyright для tests/checks,
  матрица версий, `jira2markdown`.

Статус утверждения: ожидается ответ `P01-R1-APPROVE` (ревизия R1).

## 6. Независимое ревью плана (24 находки, все внесены)

Вердикт был **NEEDS-REVISION**. Блокеры и главное:

1. Wheel-гейт S7 неисполним (`_loopback.py` нет; `pythonpath=["src"]`; импорт из
   чекаута из любого cwd) — переписан на исполняемую механику.
2. Ссылки гейтов на архивные тест-файлы — добавлена заметка и замены.
3. R4 (`auth login`) тихо уходил в backlog — зафиксировано решение D10.
4. Арифметика инвентаря D4 противоречила черновику + циклический freeze-тест —
   исправлено: 201/51/0, честная сверка согласованности, независимость — R2.
5. R1 walk-through отсутствовал — добавлен в S7.
6. R3 safety-регрессии предполагались закрытыми — добавлен S2b.
7. Квиток test-plan §5.5 + независимый ревью отсутствовали — добавлено в S8.
8. `client_for` без теста raw-транспорта — добавлен no-request тест.
9. Audit §E без владельца — добавлен в S1.5.
10. Контракт строк инвентаря терял поля черновика — восстановлен полный контракт.
11. `ruff --select S` в §0 был ошибочно «чисто» — исправлено на 4 находки.
12. «Тест на проекцию уже есть» — неверно; добавлен обязательный тест манифеста.
13. Живая матрица не указывала механизм wheel-запуска — добавлен `PYTHONPATH`-пин.
14. Bump версии инвалидировал колесо — перенесён до сборки (S7.0).
15. Корпус `jira2markdown` (≥50 описаний) конфликтовал с «без payload»/публичным
    репо — корпус локальный untracked, в доки только агрегаты.
16. Добавление CLI-команд ломало счётчик 88 — введено правило счётчиков.
17. CI недоопределён — provisioning Python 3.15, argv, gitleaks по факту прогона.
18. Слабые критерии приёмки — усилены, добавлены приёмки S5/S8.
19. `query_documented` — аддитивное изменение контракта: CHANGELOG + round-trip тест.
20. Удаление матрицы — точный grep + где живут три списка test-plan §6.
21. Удаление facade противоречило audit-follow-up — отмечено supersede решением D2.
22. Владельцы документации — назначены в S5.4.
23. Дерево «чистое» при untracked плане — уточнено.
24. Сужение pyright до `src` — зафиксировано как осознанное решение.

## 7. Факты о bbk (`D:\zcache\bbk`, пакет `bbk`)

Atlassian-часть публичного API (~45 экспортов):

- bitbucket: `search_code`, `projects`, `repos`, `list_files`, `file_at`,
  `repos_with_extension`, `pr`, `pr_files`, `pr_diff` (batch `paths=[...]`),
  `pr_file`, `pr_comments`, `pr_compact`, `my_prs`, `prs`;
- repo: `ls`, `grep`, `grep_ex`, `blame`, `branch`, `branches`, `commits`, `commit`,
  `commit_changes`, `commit_diff`, `pr_commits`, `find_repos`;
- jira: `jql`, `rows`, `mine`, `issue`, `issue_md`, `statuses`, `me`, `transitions`,
  `resolve_user` (транслитерация), `recent_comments`, `titles` (кеш), `url`;
- confluence: `page`, `page_md`, `page_storage`, `page_id`, `title`, `children`,
  `spaces`, `search_cql`, `url_for`;
- md (публичные): `confluence_to_md`, `wiki_to_md`, `html_to_md`, `jira_issue_to_md`,
  `render_diff`, `compact`, `compact_json`;
- review: `review`, `collect`, `render_markdown`, `Packet`, `parse_pr_link`,
  `file_links`, `java_members`, `red_flags`, `changed_symbols`;
- `attachments.attachment_download`, `whoami`, `find`; есть и пишущий `write` (вне AtlaWire).
- Не-Atlassian модули (координация агентов, календарь, чаты, почта, локальные
  индексы, инфраструктурные интеграции) — вне области (уходят в devinoAI).
- CLI bbk: 39 команд (argparse) — полная опись в
  `.development/review/2026-11-20_BBK_PARITY_BASELINE.md`.

## 8. Инфраструктура сессии

- Эта сессия получала `400 Invalid_request_error ... input[69].name` — в историю
  попали искажённые имена tool-call (последствие сбоев передачи). Fork не лечит
  (копирует историю); создана новая сессия **`a63fedce-1037-4644-a93b-f38d86fa0184`**
  с брифом на Ponytail Audit; Ponytail Audit в этой сессии НЕ выполнялся
  (загружен только skill `ponytail-audit` + `evidence-contract.md`).
- На машине не запускать GUI индексатора файлов (уже работает) — использовать CLI.
- Локальный профиль: установленный CPython 3.15 (`C:/Python315/python.exe`), без venv,
  без `uv run`/`uv sync`; `uv` — только `uv lock --check --offline`.
- Полный офлайн-набор ~287 с; запускать на кандидатах, не после каждой правки.

## 9. Команды-гейты

```text
C:/Python315/python.exe -B -m pytest -q -p no:cacheprovider        # 662 passed
uv lock --check --offline
C:/Python315/python.exe -m ruff check src tests checks
C:/Python315/python.exe -m ruff check --select S src
C:/Python315/python.exe -m ruff format --check src tests checks
C:/Python315/python.exe -m pyright src
```

## 10. Куда смотреть

- План: `.development/atlawire-delivery/github-release-plan.md`
- Карта проекта: `.development/HANDOFF.md` (опыт, грабли, §6 остатки)
- Контракты/методология: `delivery-plan.md`, `audit-follow-up.md`, `test-plan.md`
- Инвентарь: `.development/rest-inventory-draft.md`; BBK: `bbk-parity.md` +
  `review/2026-11-20_BBK_PARITY_BASELINE.md`
- Документация продукта: `README.md`, `TODO.md`, `CHANGELOG.md`,
  `docs/{INDEX,AGENT-QUICKSTART,AGENT-SKILL,API,LIVE-READ-ONLY,RESEARCH-COVERAGE,DEFERRED-WRITES,FEEDBACK}.md`

## 11. Следующие шаги

1. Выполнить/дождаться Ponytail Audit (новая сессия либо вручную).
2. Утвердить план ответом `P01-R1-APPROVE` (ревизия R1) — либо правки → R2.
3. После утверждения отдать план исполнителю (файл самодостаточен);
   пушит и применяет GitHub-настройки только владелец.



## 12. Полный текст независимого ревью плана (verbatim)

Reviewer: independent-review subagent (fresh context, read-only). Plan revision R1
(после внесения — R1; вердикт относился к первоначальной ревизии). Ниже — полный
ответ без сокращений.

### Coverage verdict (question 1, answered first because it drives the rest)

Mapping HANDOFF §6.1–9 / §10 and delivery-plan R1–R6 against S1–S8:

| Standing item | Covered? |
|---|---|
| HANDOFF §6.1 canonical surface | Yes — D2/S2 |
| §6.2 release proof (R6) | Yes — S7 (but see #1) |
| §6.3 BBK parity disposition (R5) | Yes — S3.1 |
| §6.4 R2 parameter completeness | Recorded backlog (D3, §12.1) — legitimate |
| §6.5 inventory + 9 unresolved rows | Yes — S4.2/D4 (arithmetic broken, #4) |
| §6.6 stale matrix | Yes — S4.5 (schema reduced, #10) |
| §6.7 CI + About | Yes — S6/S8 |
| §6.8 `updateHistory`/`failFast` | Yes — S5.1 |
| **§6.9 audit §E** (bad fixtures, live-runner child envs, coverage scope) | **No slice** (#9) |
| §10 "не доказано" (1–6) | Yes, except "live sample not exhaustive" only re-stated |
| **R1 agent walk-through from wheel** | **No slice** (#5) |
| R2 | Recorded backlog by D3 — legitimate |
| **R3 reproduced safety defects** | **Assumed fixed, never cited/proven** (#6) |
| **R4 / `auth login` handoff setup** | **Silently dropped to backlog** (#3) |
| R5 | Yes — S3 |
| R6 | Yes — S7 |
| **test-plan §4 sensitivity receipt, §5.5 independent review** | **Absent** (#7) |

Orphans: HANDOFF §6.9, R1 walk-through, R3 regressions, R4 setup, test-plan §4/§5.5.
Separately, the plan inherits executable gates from test-plan §5.1/§5.3 that no longer
resolve in the repo (#2).

---

### Findings

### 1. BLOCKER — S7's wheel gate cannot be executed as written

Evidence:
- `S7.2` (plan:290–291) instructs "Прогнать `tests/_loopback.py`-сценарии с PATH,
  закреплённым за target-лаунчером". **`tests/_loopback.py` does not exist** — only
  `tests/__pycache__/_loopback.cpython-315.pyc` remains. No test module in `tests/`
  uses `subprocess`, `.exe`, `Scripts` or `Python315` at all (grep count = 0), so
  "PATH pinned to the target launcher" exercises nothing: the suite never launches
  the console script.
- `pyproject.toml:39–40` sets `[tool.pytest.ini_options] pythonpath = ["src"]`, and
  pytest inserts those at position 0. So `S7.3`'s "PYTHONPATH и PATH на target …
  утечка в чекаут = провал гейта" is red on every run, because `<repo>/src` outranks
  `PYTHONPATH`.
- `atlawire` is importable from any cwd — verified: importing from the scratch dir
  yields `D:\REPO\github\AtlaWire\src\atlawire\__init__.py`, `0.1.0.dev0`.
  `<target>\Scripts\atlawire.exe` therefore runs the editable checkout unless
  `PYTHONPATH` is pinned; test-plan §5.3/§5.4 already warned about exactly this.
- `pip install --target` script placement is correct (`<target>\Scripts`), so the
  path is not the problem — the import identity is.

Fix: replace S7.2/S7.3 with exact commands, including `-o pythonpath=` (or run pytest
with `PYTHONPATH=<target>` from outside the rootdir) and a hard assertion that
`atlawire.__file__` is under `<target>` before any case runs.

### 2. BLOCKER — standing-doc gate commands point at test modules that no longer exist

Evidence: `tests/` now holds 31 files, all `test_spec_*` plus `test_contract_oracles.py`.
Absent: `test_jira_reference_unit.py`, `test_jira_reference_cli_e2e.py`,
`test_sdk_unit.py`, `test_sdk_e2e.py`, `test_sdk_cli_e2e.py`, `test_facade_unit.py`,
`test_facade_cli_e2e.py`, `test_catalog_unit.py`, `test_entrypoints.py`,
`tests/_loopback.py`, `test_binary_read_cli_e2e.py`,
`test_bitbucket_attachment_cli_e2e.py` — i.e. every file named by test-plan §5.1
(lines 284–285) and §5.3, and by delivery-plan's evidence section (lines 694–707).
Plan:9–10 asserts their criteria remain in force, and plan:291 references a dead one.

Fix: add a first-slice reconciliation step mapping each standing gate command to
existing files/nodes, and list replaced evidence explicitly.

### 3. BLOCKER — R4 (owner setup / `auth login`) demoted to backlog without a recorded decision

Evidence: plan:86 lists "auth-login флоу (backlog)"; plan:337–338 puts
`atlawire auth login` in §12 "Backlog после релиза … если реальные пользователи её
попросят". Standing gates: delivery-plan R4 "What is still owed … Implement the
approved manual enrollment path" (line 42); `%live-fixtures-8` "The handoff still
needs the documented, tested manual setup flow … Existing-token access alone does not
pass the new-enrollment check" (delivery-plan:238–241); test-plan §3C "Human setup,
**required for handoff** but not for the first read slice" (line 172), and §5.5 lists
unsupported required scope as a release blocker (line 356).

Fix: either add an S-slice for the manual PAT enrollment path, or record an explicit
owner decision superseding R4/§3C and state what a fresh user is told to do instead.

### 4. BLOCKER — D4/S4 frozen inventory is internally inconsistent and the freeze gate is circular

Evidence:
- D4 (plan:49–54) says "9 нерешённых строк" then enumerates `8 × /settings/…` +
  `GET …/subtask/move` + `GET /rest/api/1.0/application-properties` = **10 rows**.
  `.development/rest-inventory-draft.md:19–24` fixes the semantics: 252 rows =
  41 excluded + 202 required + 9 unresolved, and line 44/48 states
  application-properties is a **required** row absent from the runtime registry, not
  one of the 9 unresolved (line 71 shows the 9th is `subtask/move`). So S4.2's
  "202 required (текущий реестр), 41 excluded, +9 по D4" (plan:236–238) cannot be
  reconciled to any single set of totals.
- S4.3's gate "offline-тест сравнивает required-строки инвентаря с рантайм-реестром
  (`list_operations()`)" (plan:240–241) is tautological: the registry is itself built
  from `src/atlawire/manifest.json` (`operations.py:1598–1679`,
  `_install_manifest_operations()` at 1679), which is generated from the same mapping
  files (`tools/build_read_manifest.py:17`). test-plan §1.3 forbids exactly this as
  evidence.

Fix: publish the post-D4 counts (required/excluded/unresolved totals) and replace the
subset check with route expectations authored independently of
`operations.py`/`manifest.json`.

### 5. MAJOR — R1's "fresh agent finishes from the wheel" gate has no slice

Evidence: delivery-plan R1 "prove a fresh agent can finish from the final wheel and
shipped guide" (line 39); test-plan §6 requires "Run one **agent task walk-through**
without source access from a clean wheel … learn syntax; find a known issue, page and
repository; retrieve exact issue/page revision/pinned PR; ask for a second page;
explain an empty result and a controlled failure; download the known binary and verify
its receipt" (lines 413–419). S7.2 (plan:287–291) checks only `--help`,
`operations` = 202, `--catalog` = 88 — none of the walk-through.

Fix: add one scripted walk-through against the wheel with exact argv and expected
exits, recorded in the release report.

### 6. MAJOR — R3's reproduced safety defects are assumed closed; decisive regressions do not exist

Evidence: delivery-plan execution order step 1 is "Stop false success and data loss"
(line 612); test-plan §5.1 requires the slice-A regression plus
`tests/test_binary_read_cli_e2e.py` and `tests/test_bitbucket_attachment_cli_e2e.py`
(lines 274–279) — those files are gone. Grep of `tests/` for
`file_publication|publish_new_file|create_temporary|FilePublication` → **no matches**;
`O_EXCL|already exists|FileExistsError|truncated gzip|content-encoding` → no matches.
Only one `206` test exists, for the archive reader
(`tests/test_spec_missing_functions.py:556–564`), not for the SDK binary path
(`sdk.py:623`, `sdk.py:912`). The docs still call these open: `bbk-parity.md:47–48`
"no-overwrite and complete gzip validation are open … need regression proof".

Fix: add one slice (or an explicit "already green, here are the nodes" evidence line)
covering no-clobber publication, 206 on both binary paths, truncated gzip and `1e999`.

### 7. MAJOR — test-plan §4 (sensitivity) and §5.5 (independent review + receipt) absent from the release path

Evidence: test-plan §4 requires a runnable regression per shared boundary with
recorded node ID and "failing before / passing after" (lines 238–270), with "missing
decisive sensitivity evidence is a handoff blocker" (268–270); §5.5 requires an
implementer receipt table and a **fresh reviewer** (lines 347–358); delivery-plan
step 5 repeats "Have a fresh reviewer challenge code and tests" (line 616). Plan §3
(lines 100–107) assigns "ревью" to the primary agent and S8 goes straight from
candidate to the owner checklist (plan:309–328). No slice produces that receipt or an
independent pass.

Fix: add S8.0 "evidence receipt + independent review" with the receipt table as the
deliverable and the reviewer's verdict as an exit condition.

### 8. MAJOR — `client_for` stays public with zero tests, while the standing gate requires a no-request assertion

Evidence: audit-follow-up #4 (`%read-boundary-1`, lines 79–89) treats this as a
reproduced read-only breach and demands inventory + a verified closed surface;
test-plan §3C requires "Assert the public interface does not expose a callable generic
SDK `request()`; no actual write is needed to prove this" (line 167). The code fix
exists (`sdk.py:293–329`, `ReadOnlyClient`, `_RAW_TRANSPORT`), but grep `client_for`
in `tests/` → **no matches**: no test protects it. Plan S2.3 keeps it (plan:137–140)
and S2.2's new export test explicitly declines function-level coverage (plan:136).

Fix: one no-request unit test that `client_for(...).request/.get/.post` raise
`AttributeError`, plus narrowing the README wording to "advanced, not guaranteed
read-only".

### 9. MAJOR — HANDOFF §6.9 / audit §E items have no owner

Evidence: HANDOFF §6.9 (lines 236–239) points at audit-follow-up §E: fixture
corrections (`tags` cursor/cap, Jira late-row numeric IDs), live-runner child
environments (`SystemRoot`, nested pytest user-site), and coverage measured with an
explicit package + subprocess collection. Plan S7.5 covers only the coverage half,
and only as "цифру зафиксировать … Порог не вводится" (plan:301–303) — no assertion
that a known child's execution is represented. No slice touches the fixture/runner
items; the runner has no test in `tests/` at all.

Fix: one small slice "audit §E closure" or an explicit line naming which §E items are
already green and which are accepted as backlog.

### 10. MAJOR — the frozen inventory's row contract drops fields the standing docs require

Evidence: plan:236–238 specifies
`product | method | route | disposition | reason | operation_id`. delivery-plan
`%scope-30` requires "the target product/edition/reference versions and each row's
method, normalized route, stable ID, **response kind**, disposition and **source
anchor**" (lines 490–491); the existing draft already carries `reference_version`,
`path_as_written`, `source{file,row_group,anchor,index}`, `metadata_gaps`,
`runtime_operation_id`, `duplicate_of` (`rest-inventory-draft.md:156–164`).
test-plan §6 additionally requires per row `advertised | adapter | offline installed
test | live status` (lines 373–391). The plan's schema silently discards provenance
and response kind.

Fix: adopt the draft's row contract plus the evidence columns, or state explicitly
which columns are deferred and to which backlog item.

### 11. MAJOR — S1's baseline table is wrong for the security lint gate

Evidence: plan:21 claims "`ruff check --select S src` | чисто". Measured on this
HEAD: **4 findings** — `http.py:24` S105 (`_SECRET_ECHO_MESSAGE`), `operations.py:106`
S105 (`_INVALID_TOKEN`), `pr_review.py:121` S105 (`_TOKEN_INVALID`),
`regex_helper.py:298` S603 (`subprocess.Popen`). S1's acceptance (plan:123) is
"`ruff check --select S` — 0", so the executor must resolve four security findings the
plan never enumerates; the cheap way out is blanket `# noqa`. (Also §0's "~41
находка" measures 37 today — cosmetic.)

Fix: list the four S findings with their intended resolution.

### 12. MAJOR — S4.1's premise ("тест на проекцию уже есть") is false

Evidence: grep `manifest` in `tests/` → **no files**; the plan explicitly declines CI
coverage (plan:234–235). Meanwhile `src/atlawire/manifest.json` is imported into the
live registry at import time (`operations.py:1598–1605`, 1679) and ships in the wheel,
and the generator being repaired reads a directory that no longer exists
(`tools/build_read_manifest.py:17`).

Fix: add the small projection test (or a `--check` mode) and drop the "no test needed"
line.

### 13. MAJOR — S7's live-matrix step does not say how the wheel is reached, and the runner is a module launch

Evidence: `checks/live_read_only.py:19` — `CLI_PREFIX = (sys.executable, "-P", "-B",
"-m", "atlawire")`; test-plan §5.4: "The current nine-check runner is a baseline, not
final evidence: its fixed module launch can select the editable install"
(lines 326–329). Verified locally that `atlawire` resolves to
`D:\REPO\github\AtlaWire\src\atlawire\__init__.py` from any cwd. Plan S7.4 says "всё
с того же установленного колеса" (plan:294–300) but names no mechanism and no
pre-run assertion.

Fix: name the override (`PYTHONPATH=<target>` before the run) and require the
`atlawire.__file__` check before credentials are supplied.

### 14. MAJOR — S7's artifact is invalidated by S8's version bump

Evidence: `src/atlawire/__init__.py:7` — `__version__ = "0.1.0.dev0"`, and hatchling
reads the version from that file (`pyproject.toml:32–33`). S7 builds, hashes and runs
everything "на одном хеше колеса" *before* S8.1 sets `0.1.0` (plan:311). D7 (plan:66)
and S7's acceptance (plan:305–307) require the live matrix on "том же колесе"; the
release asset and the report hash would then differ.

Fix: bump the version in a pre-S7 commit, or rebuild/re-hash/re-run after S8.1.

### 15. MAJOR — S3.4's corpus contradicts D7's own terms and the public-repo secrets rule

Evidence: plan:214–216 collects "≥50 реальных описаний Jira (живое чтение по D7:
`jql --fields description`)" as a comparison corpus. D7 (plan:63–66) authorises "только
чтение, только фиксированные проверенные маршруты, **без вывода payload**,
синтетические ожидания по форме ответа (**не по данным**)"; HANDOFF:15–17: "Репозиторий
**публичный**. Секретов, хостов, номеров задач и персональных данных в новых файлах
быть не должно." The plan says nothing about where the corpus lives, or that it must
stay untracked/sanitised.

Fix: mandate a local, untracked corpus (or sanitisation + explicit approval), and state
that only aggregate results enter the disposition table.

### 16. MAJOR — S3.2 delegates CLI-surface changes to the disposition table while D2 fixes the surface and the counts

Evidence: plan:188–189 "`pr_compact`: … как функция + `pr … compact` или флаг — по
disposition-таблице"; plan:190–191 `pr_diff(paths=[…])`; plan:194–196 "экспортировать
из `pr_review` или зафиксировать как внутренние — по disposition-таблице". D2 fixes
"88 плоских команд" (plan:33–34), and S5.2/S7.2 assert the 88 count against
`--catalog` (plan:258–260, 289–290). An executor cannot add `pr compact` and keep 88;
whether new subcommands may appear is an owner decision the plan has not made.

Fix: decide now — public *functions* only, or "any new command/flag updates the
catalog count, README and the 88 assertion in the same slice".

### 17. MAJOR — S6 is not startable without more detail, and one of its hard rules is unverified

Evidence: plan:264–278 names jobs but not the interpreter provisioning (Python 3.15 on
`ubuntu-latest`/`windows-latest`), nor the exact pytest invocation, nor that
`-o pythonpath=` must not re-inject `src`. The secrets rule "allowlist ровно для двух
синтетических фикстур" (plan:93–95, 273–275) presumes a count nobody measured:
`tests/` contains 25+ token literals of the form `TOKEN = "synthetic-…-token"`
(e.g. `test_spec_session_factory.py:19`, `test_spec_jira_rest.py:31`), and gitleaks is
not installed locally to derive the real set.

Fix: name the setup action + `python-version: "3.15"` + the exact pytest argv; restate
the secrets rule as "only fixtures the run actually flags, each with a file+regex
entry and a one-line justification".

### 18. MAJOR — acceptance criteria that cannot fail

Weak, descriptive or already-true criteria:
- S2: "фасада в `--catalog`/`operations` не было и нет" (plan:143) — true before and
  after; it can never fail.
- S3: "миграционный гайд существует" (plan:225) — existence is not behaviour.
- S4.4: `--describe` "явно говорит о статусе сверки" (plan:243–244) — no test pins
  `query_documented` for the 180 `None` rows, so setting it `True` everywhere would pass.
- S6: "CI зелёный на кандидате релиза (обе ОС)" (plan:280) — no artifact identity
  recorded, so a green run on a different commit passes.
- S7: "«внезапных» расхождений между проверками нет" (plan:306–307) — pure judgement.
- S5 (plan:253–261) and S8 (plan:309–328) have **no acceptance section at all**.

Fix: one falsifiable condition per slice ("fails if X"), and add acceptance for S5 and S8.

### 19. MINOR — `query_documented` changes a documented machine contract without the required decision

Evidence: HANDOFF §8 rule 5 "контракт JSON/TSV не меняется без отдельного решения"
(line 303); delivery-plan `%errors-33` fixes the `--describe` document shape
(lines 339–345). Plan S4.4 adds a new field (plan:242–244) and records no decision.

Fix: record it as a deliberate additive change and add a strict-JSON round-trip test
for `--describe` with both states.

### 20. MINOR — S4.5's link check is stated but not scoped; the matrix replacement is not shown to cover test-plan §6

Evidence: only four references to `full_api_matrix.md` exist (`HANDOFF.md:51,223,353`,
`PLANS-CHANGELOG.md:22`); the plan names HANDOFF and PLANS-CHANGELOG but the acceptance
"удаление матрицы не ломает ни одну ссылку" gives no command. And HANDOFF §6.6 asked to
rebuild the matrix or replace the generator; test-plan §6's "three lists … one evidence
owner and a disposition" (lines 362–368) is not obviously satisfied by inventory +
`operations`.

Fix: state the exact grep to run and add one sentence on where the three-list
functional matrix now lives.

### 21. MINOR — audit instruction "do not delete facade.py" is superseded without being cited

Evidence: `audit-follow-up.md:29` "Do not delete it or bless it as canonical as an
audit fix." D2/S2 now delete it (plan:39, 129). The plan is entitled to that, but an
executor reading the audit first will hit an apparent contradiction.

Fix: one line in S2 citing the supersede.

### 22. MINOR — doc-ownership is inconsistent across slices

Evidence: S5.1 targets README/API.md/`AGENT-QUICKSTART.md` (plan:255–256); S3.2 requires
"docs/API.md + AGENT-SKILL.md" per gap (plan:179). `plan-concerns.md` #11 explicitly
asked for "one owner per fact".

Fix: name the single owner document per fact in S5 and reference it from S3.2.

### 23. NIT — §0's tree state is described as clean while the plan file itself is untracked

Evidence: `git status --short --branch` → `## main...origin/main` plus
`?? .development/atlawire-delivery/github-release-plan.md`; HEAD `d40d071` matches.

Fix: "clean except this plan".

### 24. NIT — pyright scope narrowing is asserted, not recorded as a decision

Evidence: plan:118–121 narrows the gate to `pyright src` and says to record it in
README; test-plan §5.2 says "Run Ruff and Pyright scoped to the project"
(lines 294–297). The narrowing is defensible but not an owner decision.

Fix: one line recording it as a deliberate, documented scope decision with the
223-error baseline.

---

**Verdict: NEEDS-REVISION**

The plan is well-organised and unusually honest about baselines, but three of its
release gates (wheel identity, freeze gate, setup/handoff) cannot be executed or
cannot fail as written, two standing acceptance obligations are silently dropped (R4,
test-plan §4/§5.5), and several S-slices hide decisions the owner has not made (CLI
surface additions, gitleaks allowlist scope, security-lint resolution, post-bump wheel
identity). Fixes #1–#4 and #6–#7 before approval; the rest can be resolved with
one-line plan edits.



## 13. Дополнительно для следующего агента (обзоры, знания, факты сессии)

### 13.1 Ревью и аудиты, уже лежащие в репозитории

- `delivery-plan.md` — контракт R1–R6 (контракт, не состояние; checkpoint `16b739a`
  устарел): R1 — обнаружение/один канонический путь; R2 — именованный read-доступ +
  инвентарь; R3 — безопасность/детерминизм; R4 — настройка владельца отдельно;
  R5 — рабочие сценарии BBK; R6 — доказательство следует за артефактом.
  Внутри: execution order (5 шагов), процесс upstream-issues, решения по objections.
- `audit-follow-up.md` — **это ревью предыдущего аудита** (baseline `16b739a`).
  Ключевое: исправления ложных выводов прошлого ревью («13 failures/eight real bugs»
  не перемеряно; `tags`/`last-modified` exit-коды — дефекты фикстур; пустой
  transition ID и HTML-ссылки — не дефекты продукта; `facade.py` не мёртв; манифест
  тогда регенерировался байт в байт; «24 % покрытия» — проблема измерения).
  Находки 1–7 с file:line: overwrite при публикации, 206 в бинарном SDK-пути,
  `ChunkedEncodingError` вне обработки, `1e999`→Infinity, `client_for` отдаёт raw
  session, `find` ложный total-failure, неполное release-evidence. Work order A–F;
  большая часть закрыта коммитами `706e6ca`, `33c8360`, `bb6c1fe`, `5d90c08`,
  `fc8fb5d`, `9cb1b4d`.
- `test-plan.md` — исполняемые критерии: §1 правила кандидата/доказательств;
  §2 первый срез; §3 сценарии A–E (что именно должен отлавливать каждый тест);
  §4 таблица чувствительности/дефектов; §5 release gates (focused green → полный
  офлайн → чистое колесо → живая проверка владельцем → квиток + независимый ревью);
  §6 полная функциональная матрица (три списка).
- `plan-concerns.md` — 12 возражений исполнителя (историческое; закрыто решениями
  D1–D10 и текущим планом).
- `review/2026-11-20_BBK_PARITY_BASELINE.md` — инвентарь BBK: 39 команд, все учтены;
  disposition тестов (12 adapt / 8 split / 17 out-of-scope / 2 tool / 4 replace);
  таблица milestone-доказательств.
- `review/2026-11-18_BBK_QUALITY_AUDIT.md`, `2026-11-20_AGENT_READINESS_REVIEW.md`,
  `2026-11-20_WEB_STUDY_APPLICATION.md` — **в этой сессии не читались** (не проверены).

### 13.2 HANDOFF.md — главное (полный текст в репозитории)

- §4 грабли (исправлены): ложный успех при усечённом чтении; противоречивая
  пагинация (Jira 8.22 `total` опционален; Bitbucket — `nextPageStart`/`isLastPage`);
  потеря файла при публикации; утечка токена через ошибки SDK; обход `%2fadmin`;
  потери Markdown (картинки, `[~user]`, макросы, XHTML-ссылки); склейка `{{...}}`;
  ложная ошибка `{{code}}`; ошибки окружения как «дефекты продукта»; подмешивание
  `bbk` в проверки; «зелёный тест ≠ принятый артефакт».
- §7 особенности: только CPython 3.15 без venv; тесты могут импортировать установленную
  копию; живые проверки opt-in; секреты — только env/BBK-файл; Bitbucket-поиск —
  плагин (default branch, точные термы, ≤999 файлов, без regex); `file` на дефолтном
  коммите может не найти файл ветки — фиксируйте ref; смешанные имена статусов;
  inline-привязка PR-комментариев может не сохраняться; поиск пользователей требует
  транслитерации; `displayName` в авторах коммитов может отсутствовать; Jira
  `get_issue` отдаёт raw JSON (changelog/worklogs — отдельно); Windows: никакого
  `nul`-редиректа в bash, дорогой grep по архивам.
- §8 обязательный набор на каждую новую read-команду: unit разбора + E2E через
  loopback + пути отказа (cap/усечение/невалидный UTF-8/206/redirect/бюджет) +
  ненулевой код с пустым stdout + стабильный JSON/TSV + живая проверка фикстурами.
- §9 ускорение: заморозить знаменатель; идти от рабочих сценариев, не от endpoint'ов;
  сначала решить вопрос единой поверхности; шаблон вместо ручной работы; приёмка на
  колесе; дешёвые живые проверки; не перепроверять доказанное.
- §12 практика: `python -m atlawire.cli` ничего не делает (нет `__main__`-хука) —
  работает `python -m atlawire`; не выводить `--catalog`/`--describe` в контекст
  (десятки КБ одной строкой); дешёвая фиксация провода — loopback + `parse_qs`;
  дешёвое доказательство параметра — `--fields`; JQL `order by created DESC` без
  известных ключей валиден; существующие живые проверки — в `checks/`; статика может
  быть красной на HEAD; полный набор ~287 с.

### 13.3 jira2markdown — доказанное и недоказанное (HANDOFF §5)

- Доказано на bare `convert()`: `{code}` в ячейке таблицы разваливается в inline;
  `[^file.pdf]` даёт неверную цель Markdown; `{color}` → активный `<font>`; на сыром
  CRLF таблица ломается; stock-таблицы/панели — raw HTML (до 113 активных вхождений
  на 10 описаниях против 0–3 у нашего конвертера).
- НЕ доказано: «скорость библиотеки» (0,081 с холодный ≈ 0,078 с повторный —
  кешировать надо парсер `jira2markdown.parser`, а не «греть» `convert`); CRLF —
  требование интеграции (нормализация на LF решает); `mailto:` не теряется;
  `[~user]` управляется аргументом `usernames`; конфигурация `elements` **не
  проверялась вообще** — документированный путь, может снять оба реальных дефекта.
- Если возвращаться: LF → кеш парсера → `usernames` → `elements.replace(Code, …)`
  на кейсе ячейки → санитайзер ссылок/HTML → сравнение на ≥50 описаниях. Наш
  конвертер: 99,4–100 % фактов, инертен, 0,2–1,4 мс.

### 13.4 Операционные факты и уроки этой сессии

- Полный прогон pytest как **background**-задача дважды убивался `^C`; **foreground**
  с таймаутом 600 с отработал (283,5 с). Для длинных прогонов — foreground.
- Shell — `cmd.exe`: `;` не разделитель (нужен `&`), `&&` с коротким замыканием;
  кириллица в консоли отображается в OEM-кодировке (файлы в UTF-8 не страдают).
- `uv` — это `uv.exe` в PATH; `python -m uv` падает («No module named uv»).
  `uv lock --check --offline` прошёл (интерпретатор — chocolatey python3 3.15.2).
- Мои длинные кириллические payload'ы периодически искажались при передаче
  (примеры: «防疫», «029», «усиле022ние»); после каждой записи проверять файл;
  упрямые строки чинить байтовыми python-правками по индексу строки.
- GUI индексатора файлов запускался при использовании встроенных поисковых
  инструментов — не запускать его, использовать CLI.
- GitHub About сейчас: «Complete API access to Atlassian Jira, Confluence & Bitbucket
  for AI agents. Supports self-hosted and legacy versions.» — требует замены (S8).
- Файлы сессии: план — 438 строк; handoff — 586 строк + этот раздел; оба untracked;
  `HANDOFF.md` ещё не обновлён; код не менялся, дерево чистое на `d40d071`.

### 13.5 Ponytail Audit — запрошен, но в этой сессии не выполнен

- Skill: `C:\Users\magic\.agents\skills\ponytail-audit\SKILL.md`;
  контракт: `C:\Users\magic\.agents\skills\ponytail-review\references\evidence-contract.md`.
- Issue `anomalyco/opencode#65939` — это feature request (desktop: sidebar-вкладка
  со списком файлов сессии от magicprinc; labels `area/desktop`, `type/feature`,
  `version/v2`; бот-ответ «maintainers will consider»). К аудиту AtlaWire отношения
  не имеет — контекст.
- Формат отчёта: «What this repo does» / examined scope + load assumptions /
  findings по группам Must fix–Should fix–Nice to have (path:line, сценарий,
  доказательство, минимальный фикс, регрессия) / examined-sampled-unread /
  unverified risks / scoped verdict; read-only, one-shot, без вложенных ревьюеров.
- Бриф передан новой сессии **`a63fedce-1037-4644-a93b-f38d86fa0184`** (фон).

### 13.6 Открытые нити и риски

1. План ждёт утверждения: ответ `P01-R1-APPROVE` (ревизия R1) или правки → R2.
2. Отчёт Ponytail Audit — ожидается в новой сессии (или выполнить вручную).
3. Хрупкость этой сессии: 400 `input[…].name` из-за искажённых записей tool-call
   в истории; путь восстановления — новый чат (fork копирует повреждение).
4. План и handoff untracked — коммит/пуш на усмотрение владельца; код не менялся.
