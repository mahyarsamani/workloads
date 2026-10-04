"""Checkpoint manifest: what is needed to restore a checkpoint (and to tell
later where it came from), stored next to m5.cpt.

Written by the workload's exit handler right after it takes a checkpoint
(the same place process_info.txt is copied into the checkpoint; see
FSWorkloadWrapper._write_checkpoint_manifest), with run settings provided by
the run script through FSWorkloadWrapper.set_checkpoint_context. Read by
run_ckpt_restore.py when restoring, so values that must match the checkpoint
(platform, MSS flag, ...) come from the checkpoint rather than from whatever
the current command line or code says.
"""

import datetime
import json
import subprocess

from pathlib import Path
from typing import Optional

MANIFEST_NAME = "checkpoint_manifest.json"
SNIPPET_NAME = "insights_snippet.txt"
SCHEMA_VERSION = 1

_PROJECT_DIR = Path(__file__).resolve().parent.parent
# Repositories whose state determines the simulator and the guest binaries.
_REPOS = {
    "project": _PROJECT_DIR,
    "gem5": _PROJECT_DIR / "gem5",
    "workloads": _PROJECT_DIR / "workloads",
    "hov": _PROJECT_DIR / "workloads" / "hov",
    "UME": _PROJECT_DIR / "workloads" / "UME",
    "hpcg": _PROJECT_DIR / "workloads" / "hpcg",
    "branson": _PROJECT_DIR / "workloads" / "branson",
}


def _git_state(repo: Path) -> Optional[dict]:
    """HEAD and whether the tree has uncommitted changes, or None."""

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    try:
        return {
            "sha": git("rev-parse", "HEAD"),
            "dirty": git("status", "--porcelain", "--untracked-files=no")
            != "",
        }
    except (OSError, subprocess.CalledProcessError):
        return None


def _file_state(path: Path) -> dict:
    """Identity of a large file (disk image, kernel) without hashing it."""
    path = Path(path).resolve()
    try:
        stat = path.stat()
        return {
            "path": str(path),
            "size": stat.st_size,
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    except OSError:
        return {"path": str(path), "size": None, "mtime": None}


def write_manifest(
    checkpoint_dir: Path,
    files: dict,
    snippet: Optional[str] = None,
    **fields,
) -> Path:
    """Write the manifest into `checkpoint_dir`.

    `files` maps a role (e.g. "disk_image") to a path; `fields` are the
    checkpoint-specific values (kind, workload, platform, MSS flag, ...).
    The insights snippet, if any, is also saved as plain text so that it
    stays with the binaries it was extracted from.
    """
    checkpoint_dir = Path(checkpoint_dir)
    manifest = {
        "schema": SCHEMA_VERSION,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "git": {name: _git_state(repo) for name, repo in _REPOS.items()},
        "files": {role: _file_state(path) for role, path in files.items()},
        "has_snippet": snippet is not None,
        **fields,
    }
    if snippet is not None:
        (checkpoint_dir / SNIPPET_NAME).write_text(snippet)
    path = checkpoint_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def read_manifest(checkpoint_dir: Path) -> Optional[dict]:
    """The manifest of `checkpoint_dir`, or None for older checkpoints."""
    path = Path(checkpoint_dir) / MANIFEST_NAME
    if not path.exists():
        return None
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schema {manifest.get('schema')}, "
            f"expected {SCHEMA_VERSION}."
        )
    return manifest
