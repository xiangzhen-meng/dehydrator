from pathlib import Path

import pytest

from dehydrator.mcp_security import MCPPathError, validate_input_path, validate_output_path


def test_input_must_be_under_configured_root(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    recording = media / "lecture.mp4"
    recording.write_bytes(b"media")

    assert (
        validate_input_path(recording, env={"DEHYDRATOR_MCP_INPUT_ROOTS": str(media)}) == recording
    )

    with pytest.raises(MCPPathError):
        validate_input_path(
            tmp_path / "outside.mp4", env={"DEHYDRATOR_MCP_INPUT_ROOTS": str(media)}
        )


def test_output_must_be_under_configured_root(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    assert (
        validate_output_path(outputs / "lecture", env={"DEHYDRATOR_MCP_OUTPUT_ROOTS": str(outputs)})
        == outputs / "lecture"
    )

    with pytest.raises(MCPPathError):
        validate_output_path(
            tmp_path / "outside", env={"DEHYDRATOR_MCP_OUTPUT_ROOTS": str(outputs)}
        )
