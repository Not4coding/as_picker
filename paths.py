"""路径相对本目录，换机器只拷 bin 即可。可用环境变量覆盖。"""
import os
import shutil
from pathlib import Path

BIN = Path(__file__).resolve().parent
DATA = Path(os.environ.get("AS_DATA", str(BIN / "data")))
SOURCE = Path(os.environ.get("AS_SOURCE", str(DATA / "source")))
PRODUCT = Path(os.environ.get("AS_PRODUCT", str(DATA / "product")))
MUSIC = Path(os.environ.get("AS_MUSIC", str(SOURCE / "Sample" / "Music")))
TMP = Path(os.environ.get("AS_TMP", str(BIN / "_compose_tmp")))
MAIN = BIN


def _first(*cands: str | Path) -> Path:
    for c in cands:
        if not c:
            continue
        p = Path(c)
        if p.exists():
            return p
    return Path(cands[-1] if cands else "")


FONT = _first(
    os.environ.get("AS_FONT"),
    BIN / "fonts" / "msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)
FONT_BD = _first(
    os.environ.get("AS_FONT_BD"),
    BIN / "fonts" / "msyhbd.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    FONT,
)


def _tool(name: str) -> str:
    local = BIN / "ffmpeg" / (f"{name}.exe" if os.name == "nt" else name)
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"找不到 {name}，请先运行 setup.bat")


def which_ffmpeg() -> str:
    return _tool("ffmpeg")


def which_ffprobe() -> str:
    return _tool("ffprobe")
