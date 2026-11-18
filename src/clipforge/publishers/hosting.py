from __future__ import annotations

import shutil
from pathlib import Path

from ..config import HostingCfg


class PublicHost:
    """Makes a local file reachable at a public URL (needed by Instagram).

    Copies the file into `local_dir`; you serve that directory at `base_url`.
    """

    def __init__(self, cfg: HostingCfg):
        if not cfg.base_url:
            raise ValueError("hosting.base_url is required for Instagram")
        self.dir = Path(cfg.local_dir)
        self.base_url = cfg.base_url.rstrip("/")

    def expose(self, video: Path) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        target = self.dir / video.name
        if target.resolve() != video.resolve():
            shutil.copyfile(video, target)
        return f"{self.base_url}/{video.name}"
