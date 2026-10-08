"""Checkpoint manifest: what is needed to restore a checkpoint (and to tell
later where it came from), stored next to m5.cpt.

Written by the workload's exit handler right after it takes a checkpoint
(the same place process_info.txt is copied into the checkpoint; see
FSWorkloadWrapper._write_checkpoint_manifest), from the board and the
workload wrapper only. Read back through
FSWorkloadWrapper.read_checkpoint_manifest when restoring, so values that
must match the checkpoint (KVM, MSS flag, ...) come from the checkpoint
rather than from whatever the current command line or code says. A
checkpoint without a manifest cannot be restored.
"""

import datetime
import json

from pathlib import Path
from typing import Optional

from m5.util import warn

from gem5.resources.md5_utils import md5_file

MANIFEST_NAME = "checkpoint_manifest.json"
SNIPPET_NAME = "insights_snippet.txt"

# Hashing a disk image takes minutes, so build-arm.sh records its md5 in
# `<image>.md5` when it builds it; files this large are not worth hashing
# on every checkpoint.
_LARGE_FILE_SIZE = 1 << 30


def _md5(path: Path) -> str:
    """md5 of `path`, from `<path>.md5` (md5sum format) if it is at least as
    new as `path`, otherwise computed."""
    sidecar = path.with_name(path.name + ".md5")
    if sidecar.exists() and sidecar.stat().st_mtime >= path.stat().st_mtime:
        return sidecar.read_text().split()[0]
    if path.stat().st_size > _LARGE_FILE_SIZE:
        warn(
            f"No up-to-date {sidecar.name} next to {path}; hashing it, which "
            "may take minutes."
        )
    return md5_file(path)


def _artifact(path: Optional[Path]) -> Optional[dict]:
    """Path and md5 of an artifact (kernel, disk image, ...), or None."""
    if path is None:
        return None
    path = Path(path).resolve()
    return {"path": str(path), "md5": _md5(path)}


def write_manifest(
    checkpoint_dir: Path,
    artifacts: dict,
    snippet: Optional[str] = None,
    **fields,
) -> Path:
    """Write the manifest into `checkpoint_dir`.

    `artifacts` maps a role (e.g. "disk_image") to a path, or None; `fields`
    are the checkpoint-specific values (workload, KVM, MSS flag, ...).
    The insights snippet, if any, is also saved as plain text so that it
    stays with the binaries it was extracted from.
    """
    checkpoint_dir = Path(checkpoint_dir)
    manifest = {
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "artifacts": {
            role: _artifact(path) for role, path in artifacts.items()
        },
        **fields,
    }
    if snippet is not None:
        (checkpoint_dir / SNIPPET_NAME).write_text(snippet)
    path = checkpoint_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def read_manifest(checkpoint_dir: Path) -> dict:
    """The manifest of `checkpoint_dir`."""
    path = Path(checkpoint_dir) / MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"{checkpoint_dir} has no {MANIFEST_NAME}; it cannot be restored."
        )
    return json.loads(path.read_text())
