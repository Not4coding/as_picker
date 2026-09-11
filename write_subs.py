"""按《字幕排版规则》从 copy.txt 出竖屏/横屏 SRT。时长跟 TTS（默认 1.0，约 7 字/秒）。"""
import os
import re
import sys
from pathlib import Path

import soundfile as sf

from paths import PRODUCT as _PRODUCT, SOURCE

PRODUCT = _PRODUCT / "subs"
SPEED = float(os.getenv("SHERPA_TTS_SPEED", "1.0"))
# 01 条实测 speed=1.0 约 7.06 字/秒
CPS = 7.0 * SPEED

# 舒适字数（规则：别顶上限）
SPEC = {
    "竖屏": {"line": 14, "lines": 1},
    "横屏": {"line": 16, "lines": 2},
}


def units(s: str) -> float:
    n = 0.0
    for ch in s:
        if ch.isspace():
            continue
        n += 1.0 if ("\u4e00" <= ch <= "\u9fff" or ord(ch) > 0x2E7F) else 0.5
    return n


def phrases(text: str) -> list[str]:
    parts = re.split(r"(?<=[，。！？；、])", re.sub(r"\s+", " ", text.strip()))
    return [p.strip() for p in parts if p.strip()]


def wrap_phrase(p: str, lim: float) -> list[str]:
    if units(p) <= lim:
        return [p]
    lines, buf = [], ""
    for ch in p:
        if buf and units(buf + ch) > lim:
            sp = buf.rfind(" ")
            if sp >= 4:
                lines.append(buf[:sp].rstrip())
                buf = buf[sp + 1 :] + ch
            else:
                lines.append(buf)
                buf = ch
        else:
            buf += ch
    if buf:
        lines.append(buf)
    return lines


def screens(text: str, line_u: float, max_lines: int) -> list[list[str]]:
    out, lines, cur = [], [], ""

    def push_line():
        nonlocal cur
        if cur:
            lines.append(cur.lstrip("、，"))
            cur = ""

    def push_screen():
        nonlocal lines
        if lines:
            out.append(lines[:])
            lines = []

    for p in phrases(text):
        for bit in wrap_phrase(p, line_u):
            if bit[:1] in "、，" and not cur and lines:
                lines[-1] += bit[0]
                bit = bit[1:]
                if not bit:
                    continue
            if cur and units(cur + bit) > line_u:
                push_line()
                if len(lines) >= max_lines:
                    push_screen()
            cur += bit
        if cur.endswith(("。", "！", "？")):
            push_line()
            push_screen()
    push_line()
    push_screen()
    if len(out) >= 2 and sum(units(x) for x in out[-1]) < 5:
        out[-2].extend(out[-1])
        if len(out[-2]) > max_lines:
            extra = out[-2][max_lines:]
            out[-2] = out[-2][:max_lines]
            out[-1] = extra
        else:
            out.pop()
    return out


def ts(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"


def srt(cues: list[list[str]], weights: list[float], dur: float) -> str:
    total = sum(weights) or 1.0
    t, blocks = 0.0, []
    for i, (lines, w) in enumerate(zip(cues, weights), 1):
        span = dur * (w / total)
        end = dur if i == len(cues) else t + span
        blocks.append(f"{i}\n{ts(t)} --> {ts(end)}\n" + "\n".join(lines) + "\n")
        t = end
    return "\n".join(blocks)


def one(folder: Path):
    text = (folder / "copy.txt").read_text(encoding="utf-8").strip()
    wav = folder / "voice.wav"
    if wav.exists():
        dur = float(sf.info(str(wav)).duration)
    else:
        dur = max(units(text) / CPS, 1.0)
    for name, spec in SPEC.items():
        cues = screens(text, spec["line"], spec["lines"])
        weights = [sum(units(x) for x in c) for c in cues]
        body = srt(cues, weights, dur)
        dest = folder / f"subs_{name}.srt"
        dest.write_text(body, encoding="utf-8")
        PRODUCT.mkdir(parents=True, exist_ok=True)
        (PRODUCT / f"{folder.name}_{name}.srt").write_text(body, encoding="utf-8")
    return dur, len(screens(text, SPEC["竖屏"]["line"], SPEC["竖屏"]["lines"]))


def main():
    folders = sorted(
        p for p in SOURCE.iterdir()
        if p.is_dir() and p.name != "Sample" and (p / "copy.txt").exists()
    )
    if len(sys.argv) > 1:
        folders = [p for p in folders if p.name.startswith(sys.argv[1])]
    for folder in folders:
        dur, n = one(folder)
        print(folder.name[:28], f"{dur:.1f}s", n, "屏")


if __name__ == "__main__":
    main()
