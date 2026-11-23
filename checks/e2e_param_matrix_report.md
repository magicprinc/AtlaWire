# AtlaWire E2E live (git.platform-s.com), 2026-11-23, только чтение; гейты ATLAWIRE_E2E_LIVE/_BBK_BITBUCKET/_BBK_JIRA/_PARAM_MATRIX_LIVE + --live. Обновлены checks/e2e_bbk_cli_bitbucket.py (last-modified: без --at проверяется резолв default-ветки до latestCommit, root+--at, каталог+--at=200, файл → понятная ошибка без сырого HTTP 500; grep-repo status/complete/message; file text/plain+text/markdown), checks/e2e_bbk_bitbucket.py (grep status/message), checks/e2e_param_matrix.py и checks/e2e_param_matrix_rest.py (metadata-варианты *_with_metadata: truncated/total/complete, дефолт grep 120 с, default-branch резолв). src/ и tests/ не менялись, коммитов нет.
| файл | гейт | exit | результат |
|---|---|---|---|
| e2e_bbk_cli_bitbucket.py | — | 0 | 30/30 наблюдений |
| e2e_bbk_bitbucket.py | ATLAWIRE_E2E_BBK_BITBUCKET=1 | 0 | 24 passed, 0 failed |
| e2e_bbk_jira.py | ATLAWIRE_E2E_BBK_JIRA=1 | 0 | 13 passed, 0 failed |
| e2e_bbk_confluence.py | ATLAWIRE_E2E_LIVE=1 | 0 | 7 passed, 0 failed |
| e2e_bbk_cli_jira_confluence.py | ATLAWIRE_E2E_LIVE=1 | 0 | 16/16 шагов |
| e2e_param_matrix.py | ATLAWIRE_PARAM_MATRIX_LIVE=1 | 0 | 80 строк: PASS=62 CAP=9 GAP=9 DEFECT=0 |
| e2e_param_matrix_rest.py | --live | 1 | 86 строк: 1 failed |
| e2e_semantic_live.py | ATLAWIRE_E2E_LIVE=1 | 1 | MATCH=12 VACUOUS=1 |
**Дефекты (не подгонялись):** repo_scan.scan_repository_extensions без project упирается в page limit за 20.8 с («Bitbucket page limit reached»), т.е. «скан всех проектов» недостижим при дефолтном бюджете — не связано с недавними изменениями, проверка оставлена как есть; CLI help/docstring `last-modified` в src/atlawire/cli.py всё ещё утверждает «at не отправляется» — устаревшее описание при новом поведении. **Не проверено:** семантика окна `jql updated >= -1d` (за 1 и 7 суток нет обновлённых задач — VACUOUS), CLI-attachments, 401/403/429 сценарии, production-масштаб.
