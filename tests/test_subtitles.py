import json
import shutil
import subprocess

import pytest

from clipforge.config import ProcessingCfg, SubtitlesCfg
from clipforge.pipeline import run_once
from clipforge.processing.subtitles import _ass_color, _ass_time, build_ass, chunk_words, write_ass
from clipforge.processing.transcribe import Word
from clipforge.processing.video import render_vertical

from conftest import make_clip
from test_core import FakePublisher, FakeSource, fake_download

WORDS = [Word(0.0, 0.4, "this"), Word(0.4, 0.8, "is"), Word(0.8, 1.2, "insane"),
         Word(1.2, 1.6, "no"), Word(1.6, 2.0, "way"),
         Word(4.0, 4.5, "{wow}")]  # long gap + ASS-special chars


def test_chunking_by_words_gap_and_chars():
    chunks = chunk_words(WORDS, max_words=4, max_chars=100)
    assert [[w.text for w in c] for c in chunks] == [["this", "is", "insane", "no"], ["way"], ["{wow}"]]
    tight = chunk_words(WORDS[:5], max_words=10, max_chars=10)
    assert all(len(" ".join(w.text for w in c)) <= 10 for c in tight)


def test_ass_helpers():
    assert _ass_time(3725.456) == "1:02:05.46"
    assert _ass_color("#FFE600") == "&H0000E6FF"
    with pytest.raises(ValueError):
        _ass_color("yellow")


def test_build_ass_structure():
    ass = build_ass(WORDS, SubtitlesCfg(), ProcessingCfg())
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Default,DejaVu Sans,84,&H0000E6FF,&H00FFFFFF" in ass
    dialogue = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogue) == 3
    assert dialogue[0].startswith("Dialogue: 0,0:00:00.00,0:00:01.60,")
    assert "{\\kf40}THIS {\\kf40}IS {\\kf40}INSANE {\\kf40}NO" in dialogue[0]
    assert "(WOW)" in dialogue[2] and "{wow}" not in dialogue[2].upper().replace("{\\KF", "")


class FakeTranscriber:
    def __init__(self, words=None, fail=False):
        self.words, self.fail, self.calls = words if words is not None else WORDS, fail, 0

    def transcribe(self, media):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model exploded")
        return self.words


def _run(cfg, db, transcriber, enabled=True):
    cfg.subtitles.enabled = enabled
    seen = {}

    def render(src, dst, pcfg, max_seconds=60, subtitles=None):
        seen["subtitles"] = subtitles
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"r")
        return dst

    s = run_once(cfg, db, FakeSource([make_clip("a")]), [FakePublisher()],
                 download=fake_download, render=render, transcriber=transcriber)
    return s, seen["subtitles"]


def test_pipeline_passes_subtitles_to_render(cfg, db):
    s, subs = _run(cfg, db, FakeTranscriber())
    assert s.posted and subs is not None and subs.name == "a.ass" and "Dialogue:" in subs.read_text()


@pytest.mark.parametrize("t,enabled", [
    (FakeTranscriber(fail=True), True),   # transcription crash must not block the post
    (FakeTranscriber(words=[]), True),    # no speech
    (FakeTranscriber(), False),           # feature off
    (None, True),                         # no transcriber supplied
])
def test_pipeline_renders_without_captions_when_unavailable(cfg, db, t, enabled):
    s, subs = _run(cfg, db, t, enabled)
    assert subs is None and s.posted == [("a", "tiktok")]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")
@pytest.mark.parametrize("dirname", ["plain", "we ird:name,with'quote[1];x"])
def test_burn_in_with_awkward_paths(tmp_path, dirname):
    d = tmp_path / dirname
    d.mkdir()
    src, dst = d / "in.mp4", d / "out.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:size=1280x720:rate=30:duration=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(src)], check=True)
    ass = write_ass([Word(0.2, 0.8, "hello"), Word(0.8, 1.6, "world")], d / "s.ass", SubtitlesCfg(), ProcessingCfg())
    pcfg = ProcessingCfg(crf=30, preset="ultrafast", layout="crop")
    render_vertical(src, dst, pcfg, subtitles=ass)
    # Burned-in text means frames at t=1.0 differ from the same render without subtitles.
    plain = d / "plain.mp4"
    render_vertical(src, plain, pcfg)

    def frame(video, name):
        out = d / name
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0", "-i", str(video),
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(out)], check=True)
        return out.read_bytes()

    assert frame(dst, "a.raw") != frame(plain, "b.raw")
