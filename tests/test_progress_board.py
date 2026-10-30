"""The progress board's data contract, enforced instead of described.

`docs/progress/README.md` states the rules — status enum, `blocked` needs a note,
`current` must be `null` when nothing is running, `updated_at` is what makes the board
credible. Until this file existed, none of that was checked: the board drifted three
weeks behind reality and still rendered "40% in progress", which is the failure the
board was built to avoid.

A rules file that only humans read decays. These tests are the part that does not.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

BOARD = Path("docs/progress/progress.json")
STATUSES = {"todo", "doing", "done", "blocked"}


@pytest.fixture(scope="module")
def board() -> dict:
    assert BOARD.is_file(), "进度看板的数据文件不见了"
    return json.loads(BOARD.read_text(encoding="utf-8"))


def test_updated_at_is_a_real_timestamp_with_an_offset(board: dict) -> None:
    """Without an offset the staleness banner cannot be computed, and the board would
    silently claim to be current forever."""
    stamp = datetime.fromisoformat(board["updated_at"])
    assert stamp.tzinfo is not None, "updated_at 必须带时区，否则「多久没更新」算不出来"


def test_updated_at_is_recent_enough_to_be_useful(board: dict) -> None:
    """The file is edited by hand; a stale one is worse than a missing one."""
    stamp = datetime.fromisoformat(board["updated_at"])
    age = datetime.now(UTC) - stamp
    assert age < timedelta(days=7), (
        f"看板已经 {age.days} 天没更新了。要么更新它，要么承认它不代表现在"
    )


def test_current_is_null_or_points_at_a_real_task(board: dict) -> None:
    current = board["current"]
    if current is None:
        return
    phases = {phase["id"]: phase for phase in board["phases"]}
    assert current["phase"] in phases, "current.phase 指向了不存在的阶段"
    tasks = {task["id"] for task in phases[current["phase"]]["tasks"]}
    assert current["task"] in tasks, "current.task 指向了不存在的任务"
    assert current["step"].strip(), "current.step 不能为空"


def test_every_task_uses_the_four_state_enum(board: dict) -> None:
    for phase in board["phases"]:
        for task in phase["tasks"]:
            assert task["status"] in STATUSES, f"{task['id']} 状态非法：{task['status']}"
            for entry in task.get("files", []):
                assert entry["status"] in STATUSES, (
                    f"{task['id']} 的文件 {entry['path']} 状态非法：{entry['status']}"
                )


def test_a_blocked_task_must_say_why(board: dict) -> None:
    """`blocked` with an empty note is indistinguishable from "nobody got to it", and
    the two call for different actions."""
    for phase in board["phases"]:
        for task in phase["tasks"]:
            if task["status"] == "blocked":
                assert task.get("note", "").strip(), f"{task['id']} 标了 blocked 却没写原因"


def test_a_done_task_has_no_file_left_in_progress(board: dict) -> None:
    """The percentage is computed from file statuses, so a task marked done while one
    of its files is still `todo` produces a number that contradicts its own label."""
    for phase in board["phases"]:
        for task in phase["tasks"]:
            if task["status"] != "done":
                continue
            unfinished = [
                entry["path"] for entry in task.get("files", []) if entry["status"] != "done"
            ]
            assert not unfinished, f"{task['id']} 标了 done，但 {unfinished} 还没完成"


def test_ids_are_unique(board: dict) -> None:
    phase_ids = [phase["id"] for phase in board["phases"]]
    assert len(phase_ids) == len(set(phase_ids)), "阶段 id 重复"
    task_ids = [task["id"] for phase in board["phases"] for task in phase["tasks"]]
    assert len(task_ids) == len(set(task_ids)), "任务 id 重复"


def test_every_phase_says_what_it_was_for(board: dict) -> None:
    """A phase without a goal turns the board into a list of filenames."""
    for phase in board["phases"]:
        assert phase.get("name", "").strip(), f"{phase['id']} 没有名字"
        assert phase.get("goal", "").strip(), f"{phase['id']} 没有目标"
        assert phase.get("tasks"), f"{phase['id']} 没有任务"
