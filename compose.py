"""ArtStation 作品一键成片：每个作品各出竖屏 + 横屏，时长相同。"""
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from paths import FONT, FONT_BD, MUSIC, PRODUCT, SOURCE, TMP, which_ffmpeg, which_ffprobe
from write_subs import one as write_subs_one
BGM_VOL = 0.13
# 竖屏字幕贴在居中原图下沿（Alignment=2，MarginV 越大越靠上）
SUB_STYLE = {
    "竖屏": {"fs": 50, "margin_v": 620, "margin_lr": 80},
    "横屏": {"fs": 70, "margin_v": 100, "margin_lr": 210},
}

INTRO_SEC = 1.5
IMAGE_SEC = 2.0
TAIL_SEC = 7.0
FADE_SEC = 0.3
FPS = 30
BG = (26, 26, 27)
SIZES = {"竖屏": (1080, 1920), "横屏": (1920, 1080)}


def run(cmd):
    if cmd and cmd[0] == "ffmpeg":
        cmd = [which_ffmpeg(), *cmd[1:]]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def font(size, bold=False):
    return ImageFont.truetype(str(FONT_BD if bold else FONT), size)


def cover_fill(im, size):
    r = max(size[0] / im.width, size[1] / im.height)
    nw, nh = max(1, int(im.width * r)), max(1, int(im.height * r))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (nw - size[0]) // 2, (nh - size[1]) // 2
    return im.crop((x, y, x + size[0], y + size[1]))


def contain(im, size, bg=BG):
    canvas = Image.new("RGB", size, bg)
    r = min(size[0] / im.width, size[1] / im.height)
    nw, nh = max(1, int(im.width * r)), max(1, int(im.height * r))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas.paste(im, ((size[0] - nw) // 2, (size[1] - nh) // 2))
    return canvas


def circle_avatar(im, d):
    im = cover_fill(im.convert("RGB"), (d, d))
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(im, mask=mask)
    return out


def rounded(im, radius):
    im = im.convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *im.size), radius=radius, fill=255)
    im.putalpha(mask)
    return im


def draw_intro(info, cover, avatar, size, portrait):
    w, h = size
    canvas = cover_fill(cover, size).filter(ImageFilter.GaussianBlur(36))
    canvas = Image.blend(canvas, Image.new("RGB", size, BG), 0.55)
    layer = canvas.convert("RGBA")
    draw = ImageDraw.Draw(layer)

    if portrait:
        d = int(w * 0.22)
        ax, ay = int(w * 0.07), int(h * 0.10)
        tx = ax + d + int(w * 0.05)
        name_sz, stat_sz, link_sz = 42, 28, 22
        # 头图在下半
        cw, ch = int(w * 0.86), int(h * 0.48)
        cx, cy = (w - cw) // 2, int(h * 0.42)
        thumb = rounded(contain(cover, (cw, ch), BG), 28)
        layer.paste(thumb, (cx, cy), thumb)
    else:
        d = int(h * 0.36)
        ax, ay = int(w * 0.18), (h - d) // 2
        tx = ax + d + int(w * 0.06)
        name_sz, stat_sz, link_sz = 48, 30, 24

    layer.paste(circle_avatar(avatar, d), (ax, ay), circle_avatar(avatar, d))
    name = info["author"]["name"] or ""
    works = info["author"].get("projects") or 0
    fans = info["author"].get("followers") or 0
    link = info.get("url") or ""
    ty = ay + int(d * 0.18)
    draw.text((tx, ty), name, font=font(name_sz, True), fill=(210, 210, 210))
    draw.text((tx, ty + int(d * 0.38)), f"作品数 {works}", font=font(stat_sz), fill=(160, 160, 160))
    sw = draw.textlength(f"作品数 {works}", font=font(stat_sz))
    draw.text((tx + sw + 36, ty + int(d * 0.38)), f"粉丝数 {fans}", font=font(stat_sz), fill=(160, 160, 160))
    # 链接可能很长，竖屏换行
    lf = font(link_sz)
    max_w = w - tx - 40
    if draw.textlength(link, font=lf) <= max_w:
        draw.text((tx, ty + int(d * 0.62)), link, font=lf, fill=(140, 140, 140))
    else:
        # 按字符拆两行
        cut = len(link)
        while cut > 8 and draw.textlength(link[:cut], font=lf) > max_w:
            cut -= 1
        draw.text((tx, ty + int(d * 0.58)), link[:cut], font=lf, fill=(140, 140, 140))
        draw.text((tx, ty + int(d * 0.72)), link[cut:], font=lf, fill=(140, 140, 140))
    return layer.convert("RGB")


def probe_dur(path):
    out = subprocess.check_output(
        [which_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        text=True,
    ).strip()
    return float(out)


def still_mp4(png, seconds, mp4, size):
    w, h = size
    run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(png),
            "-t", f"{seconds:.3f}", "-r", str(FPS),
            "-vf", f"scale={w}:{h},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-an", str(mp4),
        ]
    )


def video_mp4(src, mp4, size, seconds):
    w, h = size
    run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-t", f"{seconds:.3f}",
            "-vf",
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=1a1a1b,fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-an", str(mp4),
        ]
    )


def concat_copy(parts, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    lst.unlink(missing_ok=True)


def concat_fade(parts, out, total):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    raw = out.with_name(out.stem + "_raw.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)])
    start = max(0.0, total - FADE_SEC)
    run(
        [
            "ffmpeg", "-y", "-i", str(raw),
            "-vf", f"fade=t=out:st={start:.3f}:d={FADE_SEC}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-an", str(out),
        ]
    )
    raw.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)


def pick_bgm() -> Path | None:
    files = [p for p in MUSIC.glob("*.mp3") if p.stat().st_size > 50_000]
    return random.choice(files) if files else None


def srt_ts_to_ass(s: str) -> str:
    s = s.replace(",", ".")
    h, m, rest = s.split(":")
    sec, frac = rest.split(".")
    cs = int(round(int(frac[:3].ljust(3, "0")) / 10))
    if cs >= 100:
        cs = 99
    return f"{int(h)}:{int(m):02d}:{int(sec):02d}.{cs:02d}"


def portrait_margin_v(im, size, fs, gap=24):
    """字幕底边贴在 contain() 后的图下沿再留 gap。"""
    w, h = size
    r = min(w / im.width, h / im.height)
    nh = max(1, int(im.height * r))
    y1 = (h - nh) // 2 + nh
    return max(120, h - y1 - gap - fs)


def srt_to_ass(srt: Path, ass: Path, size, spec: dict):
    w, h = size
    fs = spec["fs"]
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Microsoft YaHei,{fs},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,2,"
        f"{spec['margin_lr']},{spec['margin_lr']},{spec['margin_v']},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    body = []
    for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8").strip()):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        m = re.search(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", lines[1])
        if not m:
            continue
        bits = [x.strip() for x in lines[2:] if x.strip()]
        # 竖屏单行，避免 \N 叠成双行
        text = (bits[0] if (h > w and bits) else r"\N".join(bits)).replace("{", r"\{")
        body.append(
            f"Dialogue: 0,{srt_ts_to_ass(m.group(1))},{srt_ts_to_ass(m.group(2))},"
            f"Default,,0,0,0,,{text}\n"
        )
    ass.write_text(header + "".join(body), encoding="utf-8")


def mux(visual: Path, voice: Path, bgm: Path | None, ass: Path, out: Path, dur: float):
    # cwd=ass 目录，字幕用相对路径，避开 Windows 盘符转义
    afmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    fc = (
        f"[0:v]subtitles={ass.name}[v];"
        f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=5,{afmt},apad=whole_dur={dur:.3f}[voice]"
    )
    cmd = [
        which_ffmpeg(), "-y",
        "-stream_loop", "-1", "-i", str(visual.resolve()),
        "-i", str(voice.resolve()),
    ]
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm.resolve())]
        fc += (
            f";[2:a]{afmt},volume={BGM_VOL}[bgm];"
            "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
    else:
        fc += ";[voice]anull[a]"
    cmd += [
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(out.resolve()),
    ]
    subprocess.run(cmd, check=True, cwd=ass.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def work_assets(folder: Path):
    images = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        and p.name.startswith("image_")
    )
    videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".mp4", ".webm", ".mov"} and p.name.startswith("video_"))
    return images, videos


def compose_one(folder: Path):
    info = json.loads((folder / "info.json").read_text(encoding="utf-8"))
    images, videos = work_assets(folder)
    if not images:
        print("skip no images", folder.name)
        return
    cover = Image.open(images[0]).convert("RGB")
    av_path = next(iter(folder.glob("avatar.*")), None)
    avatar = Image.open(av_path).convert("RGB") if av_path else cover
    # 封面只出片头；后面轮播其余图/视频
    slides = images[1:] if (len(images) > 1 or videos) else images
    durs = [probe_dur(v) for v in videos]
    visual = INTRO_SEC + IMAGE_SEC * len(slides) + sum(durs)
    voice = folder / "voice.wav"
    if not voice.exists():
        voice = folder / "voice.mp3"
    if not voice.exists():
        print("skip no voice", folder.name)
        return
    voice_dur = probe_dur(voice)
    # 轮播长于口播：播完画面就结束；否则口播播完再加 7 秒
    total = visual if visual > voice_dur else voice_dur + TAIL_SEC
    write_subs_one(folder)
    bgm = pick_bgm()
    PRODUCT.mkdir(parents=True, exist_ok=True)
    print(
        f"{folder.name}  画面{visual:.1f}s 口播{voice_dur:.1f}s → {total:.1f}s  "
        f"轮播图{len(slides)} 视频{len(videos)}  bgm={bgm.name if bgm else '无'}"
    )

    for label, size in SIZES.items():
        tmp = TMP / folder.name / ("v" if label == "竖屏" else "h")
        tmp.mkdir(parents=True, exist_ok=True)
        intro = tmp / "intro.png"
        draw_intro(info, cover, avatar, size, label == "竖屏").save(intro, "PNG")
        still_mp4(intro, INTRO_SEC, tmp / "00_intro.mp4", size)
        body = []
        for i, img in enumerate(slides, 1):
            slide = tmp / f"slide_{i:02d}.png"
            contain(Image.open(img).convert("RGB"), size).save(slide, "PNG")
            mp4 = tmp / f"01_img_{i:02d}.mp4"
            still_mp4(slide, IMAGE_SEC, mp4, size)
            body.append(mp4)
        for i, vid in enumerate(videos, 1):
            mp4 = tmp / f"02_vid_{i:02d}.mp4"
            video_mp4(vid, mp4, size, durs[i - 1])
            body.append(mp4)
        if not body:
            slide = tmp / "slide_01.png"
            contain(cover, size).save(slide, "PNG")
            mp4 = tmp / "01_img_01.mp4"
            still_mp4(slide, IMAGE_SEC, mp4, size)
            body.append(mp4)
        body_raw = tmp / "body.mp4"
        concat_copy(body, body_raw)
        body_loop = tmp / "body_loop.mp4"
        rest = max(0.1, total - INTRO_SEC)
        run(
            [
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(body_raw),
                "-t", f"{rest:.3f}",
                "-c", "copy",
                str(body_loop),
            ]
        )
        silent = tmp / "silent.mp4"
        concat_fade([tmp / "00_intro.mp4", body_loop], silent, total)
        srt = folder / f"subs_{label}.srt"
        if not srt.exists():
            print("skip no srt", srt.name)
            continue
        ass = tmp / "subs.ass"
        spec = dict(SUB_STYLE[label])
        if label == "竖屏":
            ref = Image.open(slides[0]).convert("RGB") if slides else cover
            spec["margin_v"] = portrait_margin_v(ref, size, spec["fs"])
        srt_to_ass(srt, ass, size, spec)
        out = PRODUCT / f"{folder.name}_{label}.mp4"
        mux(silent, voice, bgm, ass, out, total)
        print(f"  -> {out.name}")


def main():
    folders = sorted(
        p for p in SOURCE.iterdir()
        if p.is_dir() and p.name != "Sample" and (p / "info.json").exists()
    )
    if len(sys.argv) > 1:
        key = sys.argv[1]
        folders = [p for p in folders if p.name.startswith(key)]
    if not folders:
        sys.exit("no work folders")
    for folder in folders:
        compose_one(folder)


if __name__ == "__main__":
    main()
