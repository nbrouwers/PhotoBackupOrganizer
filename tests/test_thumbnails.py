from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.thumbnails import is_browser_native_codec, probe_video_codec


# ---------------------------------------------------------------------------
# is_browser_native_codec
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("codec", ["h264", "vp8", "vp9", "av1", "avc1"])
def test_browser_native_recognised(codec: str) -> None:
    assert is_browser_native_codec(codec) is True


@pytest.mark.parametrize("codec", ["hevc", "h265", "mpeg4", "mpeg2video", "flv1", "unknown"])
def test_non_browser_native_rejected(codec: str) -> None:
    assert is_browser_native_codec(codec) is False


def test_none_not_native() -> None:
    assert is_browser_native_codec(None) is False


# ---------------------------------------------------------------------------
# probe_video_codec
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probe_returns_codec_on_success() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"h264\n", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await probe_video_codec("/fake/video.mp4")

    assert result == "h264"


@pytest.mark.asyncio
async def test_probe_returns_none_on_nonzero_exit() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await probe_video_codec("/fake/video.mp4")

    assert result is None


@pytest.mark.asyncio
async def test_probe_returns_none_on_empty_output() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await probe_video_codec("/fake/video.mp4")

    assert result is None


@pytest.mark.asyncio
async def test_probe_returns_none_on_exception() -> None:
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("ffprobe not found")):
        result = await probe_video_codec("/fake/video.mp4")

    assert result is None
