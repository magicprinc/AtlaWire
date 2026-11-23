"""Contracts for the shared no-replace file publication.

Both ``attachment-get --out`` and canonical ``read --out`` stage bytes in a
temporary sibling and publish them through this module. These tests pin the
publication boundary: a destination that appears after the caller's early
check is refused, and the competitor's bytes are never replaced.
"""

from pathlib import Path

import pytest

from atlawire import cli, file_publication
from atlawire.http import AtlaWireError


def test_publish_refuses_a_destination_created_after_the_caller_check(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "report.bin"
    temporary = file_publication.create_temporary_file(destination)
    temporary.write_bytes(b"new")
    # The caller checked before this point; simulate a competing writer.
    destination.write_bytes(b"competing")

    with pytest.raises(AtlaWireError, match="already exists"):
        file_publication.publish_new_file(temporary, destination)

    assert destination.read_bytes() == b"competing"
    assert temporary.read_bytes() == b"new", "unpublished staging must be intact"


def test_publish_moves_bytes_and_removes_the_temporary_name(tmp_path: Path) -> None:
    destination = tmp_path / "report.bin"
    temporary = file_publication.create_temporary_file(destination)
    temporary.write_bytes(b"payload")

    file_publication.publish_new_file(temporary, destination)

    assert destination.read_bytes() == b"payload"
    assert not temporary.exists()


def test_publish_reports_a_missing_parent_without_creating_it(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "absent" / "report.bin"
    temporary = file_publication.create_temporary_file(tmp_path / "stage.bin")
    temporary.write_bytes(b"payload")

    with pytest.raises(AtlaWireError, match="Could not publish"):
        file_publication.publish_new_file(temporary, destination)

    assert not destination.parent.exists()
    assert temporary.read_bytes() == b"payload"


def test_temporary_names_are_unique_and_exclusive(tmp_path: Path) -> None:
    destination = tmp_path / "report.bin"

    first = file_publication.create_temporary_file(destination)
    second = file_publication.create_temporary_file(destination)

    assert first != second
    assert first.parent == destination.parent
    assert first.name.endswith(".part")
    assert second.name.endswith(".part")


def test_attachment_writer_refuses_a_competitor_created_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The call site delegates the final decision instead of replacing late."""
    destination = tmp_path / "attachment.bin"
    real_publish = file_publication.publish_new_file

    def competing_publish(temporary: Path, target: Path) -> None:
        Path(target).write_bytes(b"competing")
        real_publish(temporary, target)

    monkeypatch.setattr(cli, "publish_new_file", competing_publish)

    with pytest.raises(AtlaWireError, match="already exists"):
        cli._write_bytes(str(destination), b"new")

    assert destination.read_bytes() == b"competing"
    assert list(tmp_path.glob("*.part")) == []


def test_attachment_writer_reports_the_exact_receipt(tmp_path: Path) -> None:
    destination = tmp_path / "attachment.bin"

    receipt = cli._write_bytes(str(destination), b"payload")

    assert destination.read_bytes() == b"payload"
    assert receipt == {
        "path": str(destination),
        "bytes": 7,
        "sha256": __import__("hashlib").sha256(b"payload").hexdigest(),
    }
    assert list(tmp_path.glob("*.part")) == []
