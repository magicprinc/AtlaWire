import importlib

import pytest
from click.testing import CliRunner

import cosmic_ray.commands
from cosmic_ray.cli import cli
from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import TestOutcome as Outcome
from cosmic_ray.work_item import WorkResult, WorkerOutcome


@pytest.fixture
def config_file(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        """[cosmic-ray]
module-path = "subject.py"
timeout = 10
excluded-modules = []
test-command = "unused"

[cosmic-ray.distributor]
name = "local"
""",
        encoding="utf-8",
    )

    return config


@pytest.mark.parametrize(
    ("worker_outcome", "test_outcome"),
    [
        (WorkerOutcome.ABNORMAL, Outcome.SURVIVED),
        (WorkerOutcome.EXCEPTION, None),
        (WorkerOutcome.NO_TEST, None),
        (WorkerOutcome.SKIPPED, None),
        (WorkerOutcome.NORMAL, None),
    ],
)
def test_baseline_rejects_unsuccessful_worker_results(config_file, monkeypatch, caplog, worker_outcome, test_outcome):
    def execute(db, _config):
        db.set_result("baseline", WorkResult(worker_outcome=worker_outcome, test_outcome=test_outcome))

    monkeypatch.setattr(cosmic_ray.commands, "execute", execute)
    result = CliRunner().invoke(cli, ["baseline", str(config_file)])
    assert result.exit_code == 1, result.exception
    assert "Baseline failed." in caplog.text


@pytest.mark.parametrize("failure", ["empty", "exception"])
def test_baseline_fails_if_distributor_does_not_return_a_result(tmp_path, config_file, monkeypatch, failure):
    calls = []

    def distributor(*args, **kwargs):
        calls.append(True)
        if failure == "exception":
            raise RuntimeError("distributor failed")

    execute_module = importlib.import_module("cosmic_ray.commands.execute")
    monkeypatch.setattr(execute_module, "get_distributor", lambda _name: distributor)
    session = tmp_path / "session.sqlite"
    result = CliRunner().invoke(cli, ["baseline", str(config_file), "--session-file", str(session)])
    assert calls == [True]
    assert result.exit_code != 0
    assert isinstance(result.exception, StopIteration if failure == "empty" else RuntimeError)
    with use_db(session, WorkDB.Mode.open) as db:
        assert db.num_results == 0
        assert len(db.pending_work_items) == 1
