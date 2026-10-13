"""Smoke tests for the installed `smalls` console script.

They run the real entry point in a subprocess, from a throwaway SQLite project,
because what is most likely to break is invisible to the linters: the project
root not being on sys.path, and work happening at import time.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

# The script installed next to the interpreter running the tests, not whichever
# `smalls` comes first on PATH.
SMALLS = shutil.which("smalls", path=str(Path(sys.executable).parent))

pytestmark = pytest.mark.skipif(
    SMALLS is None, reason="smalls is not installed in this environment"
)


def run_smalls(folder, *args, answer=None):
    """Run `smalls` from `folder` and return the finished process."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SMALLS_")}
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [SMALLS, *args],
        cwd=folder,
        env=env,
        input=answer,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def history(project):
    """The migration_history rows as (name, version) tuples."""
    with closing(sqlite3.connect(project / "test.db")) as connection:
        return connection.execute(
            "SELECT name, version FROM migration_history ORDER BY name"
        ).fetchall()


@pytest.fixture(name="project")
def fixture_project(tmp_path):
    """A minimal project: a SQLite model, a config.ini and a migrations folder."""
    (tmp_path / "model.py").write_text(
        'from peewee import SqliteDatabase\n\ndb = SqliteDatabase("test.db")\n',
        encoding="utf-8",
    )
    (tmp_path / "config.ini").write_text(
        "[smalls]\nmodel=model\nobject=db\nsmalls_version=1.0.0\n", encoding="utf-8"
    )
    (tmp_path / "migrations").mkdir()
    return tmp_path


def test_help_needs_no_config_and_no_database(tmp_path):
    """--help works in an empty folder and leaves it empty."""
    assert run_smalls(tmp_path, "--help").returncode == 0
    result = run_smalls(tmp_path, "migrate", "--help")
    assert result.returncode == 0
    assert "Run migrations" in result.stdout
    assert not list(tmp_path.iterdir())


def test_missing_model_is_an_error(tmp_path):
    """A command without a configured model exits 1 and says why."""
    result = run_smalls(tmp_path, "status")
    assert result.returncode == 1
    assert "No model configured" in result.stdout


def test_create_migrate_status_rollback(project):
    """The model and migrations/ are found from the project root."""
    assert run_smalls(project, "create", "first").returncode == 0
    assert (project / "migrations" / "0001_first.py").is_file()

    result = run_smalls(project, "migrate")
    assert result.returncode == 0, result.stdout + result.stderr
    assert history(project) == [("0001_first", "1.0.0")]

    result = run_smalls(project, "status")
    assert result.returncode == 0
    assert "0001_first" in result.stdout

    result = run_smalls(project, "rollback", "0000", answer="y\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert history(project) == []
