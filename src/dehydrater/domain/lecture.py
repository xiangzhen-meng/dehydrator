from pathlib import Path

from dehydrater.domain.base import DomainModel, Seconds


class SourceFile(DomainModel):
    """用户提供的原始文件。大小和修改时间参与缓存键，替换文件后会自动重跑。"""

    path: Path
    """相对于工作区根目录的路径。"""
    size: int
    mtime_ns: int


class Lecture(DomainModel):
    """一次处理的输入清单。"""

    recording: SourceFile
    """用户提供的音频或视频文件。"""


class AudioFile(DomainModel):
    """从录像或录音中抽出、统一格式后的音频。"""

    path: Path
    """相对于工作区根目录的路径。"""
    sha256: str
    duration: Seconds
