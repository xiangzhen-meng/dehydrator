from pathlib import Path

import pytest

from dehydrater.pipeline.workspace import Workspace, WorkspaceError


@pytest.fixture
def recording(tmp_path: Path) -> Path:
    path = tmp_path / "lecture.mp4"
    path.write_bytes(b"video")
    return path


def test_prepare_and_load_input(tmp_path: Path, recording: Path) -> None:
    Workspace.prepare(tmp_path / "output", recording=recording)
    lecture = Workspace(tmp_path / "output").load_lecture()

    assert lecture.recording.size == len(b"video")
    assert lecture.recording.path == recording


def test_prepare_refuses_workspace_of_another_recording(tmp_path: Path, recording: Path) -> None:
    root = tmp_path / "output"
    Workspace.prepare(root, recording=recording)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"")

    with pytest.raises(WorkspaceError, match="另一节课"):
        Workspace.prepare(root, recording=other)


def test_files_inside_workspace_are_stored_relative(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "output")
    inside = tmp_path / "output" / "sources" / "a.mp4"
    outside = tmp_path / "elsewhere" / "b.mp4"

    assert workspace.portable_path(inside) == Path("sources/a.mp4")
    assert workspace.portable_path(outside) == outside.resolve()
