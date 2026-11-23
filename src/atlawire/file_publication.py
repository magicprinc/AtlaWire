"""Publish a completed local file without replacing an existing path.

Earlier call sites answered "does this destination exist?" and later published
with a replacing rename. A file created between those steps was silently lost.
This module owns only the temporary-file lifecycle and the final publish:
[create_temporary_file][atlawire.file_publication.create_temporary_file]
creates an exclusive sibling,
[publish_new_file][atlawire.file_publication.publish_new_file] publishes it
only if the destination is still absent, and
[discard_temporary_file][atlawire.file_publication.discard_temporary_file]
removes any unpublished remainder.

Publication uses ``os.link`` followed by removal of the temporary path. Link
creation is atomic on the target filesystem: if the destination appeared after
the caller's check, the link fails with ``FileExistsError`` and the existing
bytes stay untouched. There is no check-then-replace fallback. On filesystems
without hard links the publication fails with a generic error instead of
risking data loss; the temporary file remains the caller's to clean up.
"""

import os
import tempfile
from pathlib import Path

from atlawire.http import AtlaWireError

__all__ = [
    "create_temporary_file",
    "discard_temporary_file",
    "publish_new_file",
]

_EXISTS = "The destination already exists."
_UNPUBLISHED = "Could not publish the destination file."


def create_temporary_file(destination: str | Path) -> Path:
    """Create an exclusive sibling temporary file for ``destination``.

    The file is created with ``O_EXCL`` semantics, so concurrent writers never
    share staging bytes. It sits in the destination's directory so publication
    stays on one filesystem. A missing parent directory is an error; this
    helper never creates directories.
    """
    target = Path(destination)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".part", dir=target.parent
    )
    os.close(descriptor)
    return Path(name)


def discard_temporary_file(temporary: str | Path) -> None:
    """Remove an unpublished temporary file, ignoring an already-absent path."""
    try:
        Path(temporary).unlink()
    except OSError:
        pass


def publish_new_file(temporary: str | Path, destination: str | Path) -> None:
    """Publish ``temporary`` at ``destination`` only if that path is absent.

    The destination must not exist; an existing file is never replaced. Link
    creation and the existing-target refusal are one atomic filesystem
    operation, so a destination created during publication also fails. Other
    filesystem failures are reported as one generic error that never echoes a
    host path. On success the temporary name is removed; on failure it remains
    for [discard_temporary_file][atlawire.file_publication.discard_temporary_file].
    """
    source = Path(temporary)
    target = Path(destination)
    try:
        os.link(source, target)
    except FileExistsError:
        raise AtlaWireError(_EXISTS) from None
    except OSError:
        raise AtlaWireError(_UNPUBLISHED) from None
    try:
        source.unlink()
    except OSError:
        # The destination is complete and published; a leftover staging name
        # is not a reason to report the download as failed.
        pass
