import json
import shutil
import subprocess

import pytest

from clipforge.config import ProcessingCfg
from clipforge.processing.video import render_vertical

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


def _make_source(path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)


@pytest.mark.parametrize("layout", ["blur", "crop"])
def test_render_is_vertical_with_audio(tmp_path, layout):
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _make_source(src)
    render_vertical(src, dst, ProcessingCfg(layout=layout, crf=30, preset="ultrafast"), max_seconds=2)
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(dst)],
        capture_output=True, text=True, check=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert float(v["duration"]) <= 2.1
