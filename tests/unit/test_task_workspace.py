"""Unit tests for task_workspace.py"""

import pytest
import json
import uuid
from pathlib import Path
from task_workspace.task_workspace import (
    ensure_workspace,
    write_plan,
    write_progress,
    write_checkpoint,
    read_plan,
    read_progress,
    read_checkpoint,
    delete_workspace,
)


@pytest.fixture
def task_id():
    return str(uuid.uuid4())


def test_ensure_workspace_creates_dir(task_id):
    path = ensure_workspace(task_id)
    assert path.exists()
    assert path.is_dir()
    assert str(path) == f"/home/Bilirubin/workspace/task/{task_id}"


def test_write_plan_creates_file(task_id):
    content = "# My Plan\n\nDo things."
    write_plan(task_id, content)
    path = Path(f"/home/Bilirubin/workspace/task/{task_id}/plan.md")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == content


def test_write_progress_creates_json_file(task_id):
    progress = {"step": 1, "status": "running", "user": "andrey"}
    write_progress(task_id, progress)
    path = Path(f"/home/Bilirubin/workspace/task/{task_id}/progress.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == progress


def test_write_checkpoint_creates_json_file(task_id):
    checkpoint = {"last_action": "created", "timestamp": "2026-05-08T08:12:39Z"}
    write_checkpoint(task_id, checkpoint)
    path = Path(f"/home/Bilirubin/workspace/task/{task_id}/checkpoint.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == checkpoint


def test_read_plan_returns_content(task_id):
    content = "# My Plan\n\nDo things."
    write_plan(task_id, content)
    assert read_plan(task_id) == content


def test_read_plan_returns_none_if_missing(task_id):
    assert read_plan(task_id) is None


def test_read_progress_returns_data(task_id):
    progress = {"step": 1, "status": "running"}
    write_progress(task_id, progress)
    assert read_progress(task_id) == progress


def test_read_progress_returns_none_if_missing(task_id):
    assert read_progress(task_id) is None


def test_read_checkpoint_returns_data(task_id):
    checkpoint = {"last_action": "created"}
    write_checkpoint(task_id, checkpoint)
    assert read_checkpoint(task_id) == checkpoint


def test_read_checkpoint_returns_none_if_missing(task_id):
    assert read_checkpoint(task_id) is None


def test_delete_workspace_removes_dir(task_id):
    write_plan(task_id, "# Test")
    assert Path(f"/home/Bilirubin/workspace/task/{task_id}").exists()
    delete_workspace(task_id)
    assert not Path(f"/home/Bilirubin/workspace/task/{task_id}").exists()


def test_multiple_tasks_independent(task_id):
    task_id2 = str(uuid.uuid4())
    write_plan(task_id, "Plan A")
    write_plan(task_id2, "Plan B")
    assert read_plan(task_id) == "Plan A"
    assert read_plan(task_id2) == "Plan B"


def test_write_progress_overwrites(task_id):
    progress1 = {"step": 1}
    progress2 = {"step": 2}
    write_progress(task_id, progress1)
    write_progress(task_id, progress2)
    assert read_progress(task_id) == progress2


def test_write_checkpoint_overwrites(task_id):
    cp1 = {"action": "start"}
    cp2 = {"action": "resume"}
    write_checkpoint(task_id, cp1)
    write_checkpoint(task_id, cp2)
    assert read_checkpoint(task_id) == cp2