"""选题 → 下载 → 文案 →（可选 TTS_URL）→ 成片。TTS 由独立容器后期接入。"""
import json
import os
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from download_top5 import CTX, UA, download_work, safe_name
from paths import PRODUCT, SOURCE, which_ffmpeg
from write_copy import ai_copy, build_auto
from compose import compose_one

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("AS_CACHE", str(ROOT / "_cache")))
SEEN = ROOT / "seen.json"
SAMPLE = 100
N = 5


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            **UA,
            "Accept": "application/json",
            "Referer": "https://www.artstation.com/?sort_by=trending&dimension=3d",
        },
    )
    with urllib.request.urlopen(req, context=CTX, timeout=40) as r:
        return json.load(r)


def load_seen() -> list[str]:
    if not SEEN.exists():
        SEEN.write_text("[]\n", encoding="utf-8")
        print("新建", SEEN.name)
        return []
    try:
        data = json.loads(SEEN.read_text(encoding="utf-8"))
    except Exception:
        SEEN.write_text("[]\n", encoding="utf-8")
        print("seen 损坏，已重建", SEEN.name)
        return []
    if not isinstance(data, list):
        data = []
    return [str(x) for x in data if x]


def save_seen(extra: list[str]):
    cur = load_seen()
    have = set(cur)
    added = []
    for h in extra:
        if h and h not in have:
            cur.append(h)
            have.add(h)
            added.append(h)
    SEEN.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("查重尾缀 +", " ".join(added) or "(无新)", "→", SEEN.name, "共", len(cur))


def trending(n=SAMPLE) -> list[dict]:
    pool, have = [], set()
    page = 1
    while len(pool) < n:
        data = get_json(f"https://www.artstation.com/projects.json?page={page}&sorting=trending&dimension=3d")
        items = data.get("data") or []
        if not items:
            break
        for p in items:
            hid = p.get("hash_id")
            if not hid or hid in have:
                continue
            have.add(hid)
            pool.append(p)
            if len(pool) >= n:
                break
        page += 1
    return pool[:n]


def pick(n=N) -> list[dict]:
    seen = load_seen()
    pool = trending(SAMPLE)
    fresh = [p for p in pool if p.get("hash_id") not in seen]
    fresh.sort(key=lambda p: p.get("likes_count") or 0, reverse=True)
    picked = fresh[:n]
    print(f"样本 {len(pool)}  已选过 {sum(1 for p in pool if p.get('hash_id') in seen)}  新作 {len(fresh)}  取前{n}")
    if len(picked) < n:
        sys.exit(f"前{SAMPLE}里未选过的只剩 {len(picked)} 个")
    return picked


def project_detail(hid: str) -> dict:
    cache = CACHE / f"{hid}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        d = get_json(f"https://www.artstation.com/projects/{hid}.json")
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d
    except Exception as e:
        sys.exit(f"详情被拦 {hid}: {e}\n先打开 https://www.artstation.com/projects/{hid}.json 存到 {cache}")


def merge_work(listed: dict, detail: dict) -> dict:
    u = {**(detail.get("user") or {}), **(listed.get("user") or {})}
    w = {**listed, **detail, "user": u}
    w["hash"] = detail.get("hash_id") or listed.get("hash_id")
    w["likes"] = detail.get("likes_count") or listed.get("likes_count")
    w["views"] = detail.get("views_count") or listed.get("views_count")
    w["permalink"] = detail.get("permalink") or listed.get("permalink")
    return w


def verify(folder: Path, work: dict) -> list[str]:
    assets = [a for a in (work.get("assets") or []) if (a.get("asset_type") or a.get("type")) != "cover"]
    need_img = sum(
        1
        for a in assets
        if (a.get("asset_type") or a.get("type")) not in {"video_clip", "video"} and a.get("image_url")
    )
    need_vid = sum(
        1
        for a in assets
        if (a.get("asset_type") or a.get("type")) in {"video_clip", "video"} and a.get("video_url")
    )
    imgs = [p for p in folder.glob("image_*") if p.stat().st_size > 1024]
    vids = [p for p in folder.glob("video_*.mp4") if p.stat().st_size > 1024]
    av = next((p for p in folder.glob("avatar.*") if p.stat().st_size > 256), None)
    bad = []
    if not (folder / "info.json").exists():
        bad.append("no info.json")
    if not av:
        bad.append("no avatar")
    if len(imgs) < need_img:
        bad.append(f"images {len(imgs)}/{need_img}")
    if need_vid and len(vids) < need_vid:
        bad.append(f"videos {len(vids)}/{need_vid}")
    return bad


def user_profile(username: str) -> dict:
    if not username:
        return {}
    cache = CACHE / f"user_{username}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        d = get_json(f"https://www.artstation.com/users/{username}.json")
        cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d
    except Exception:
        return {}


def write_copy(folder: Path, info: dict, i: int):
    text = ai_copy(info, "a", i) or build_auto(info, i, "a")
    (folder / "copy.txt").write_text(text, encoding="utf-8")
    print("  copy", len(text), "字")


def tts_one(folder: Path):
    url = os.environ.get("TTS_URL")
    if not url:
        print("  skip tts（未设置 TTS_URL，口播容器后期接入）")
        return
    req = urllib.request.Request(f"{url.rstrip('/')}/tts", data=folder.name.encode(), method="POST")
    with urllib.request.urlopen(req, timeout=900) as r:
        print("  tts", r.read().decode().strip())
    if not (folder / "voice.wav").exists():
        sys.exit(f"TTS 失败 {folder.name}")


def ensure_schedule():
    if os.environ.get("AS_SKIP_SCHEDULE") or not os.environ.get("AS_ENABLE_SCHEDULE"):
        return
    py = sys.executable
    tr = f'"{py}" "{Path(__file__).resolve()}"'
    cmd = ["schtasks", "/Create", "/F", "/TN", "as_picker_pipeline", "/SC", "HOURLY", "/MO", "12", "/TR", tr]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        print("已登记每 12 小时任务 as_picker_pipeline")
    else:
        print("计划任务未写入:", (r.stderr or r.stdout or "")[:200])


def main():
    SOURCE.mkdir(parents=True, exist_ok=True)
    PRODUCT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    which_ffmpeg()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    picked = pick()
    print("PICK", stamp)
    works = []
    for i, listed in enumerate(picked, 1):
        hid = listed["hash_id"]
        print(f"{i} {listed.get('likes_count')} {hid} {listed.get('title')}")
        detail = project_detail(hid)
        w = merge_work(listed, detail)
        prof = user_profile((w.get("user") or {}).get("username") or "")
        if prof:
            u = {**prof, **(w.get("user") or {})}
            if prof.get("experience_items"):
                u["experience_items"] = prof["experience_items"]
            w["user"] = u
        works.append(w)

    folders = []
    for i, w in enumerate(works, 1):
        hid = w["hash"]
        folder = SOURCE / f"{hid}_{safe_name(w.get('title') or hid)}"
        download_work(w, folder, i)
        bad = verify(folder, w)
        print("  check", "OK" if not bad else "FAIL " + "; ".join(bad))
        if bad:
            sys.exit(f"资源不齐 {folder.name}")
        write_copy(folder, json.loads((folder / "info.json").read_text(encoding="utf-8")), i - 1)
        folders.append(folder)

    print("TTS")
    for folder in folders:
        tts_one(folder)

    print("COMPOSE")
    for folder in folders:
        if not (folder / "voice.wav").exists() and not (folder / "voice.mp3").exists():
            print("  skip compose 无口播", folder.name)
            continue
        compose_one(folder)

    save_seen([w["hash"] for w in works])
    print("DONE", stamp)
    for folder in folders:
        for lab in ("竖屏", "横屏"):
            p = PRODUCT / f"{folder.name}_{lab}.mp4"
            print(" ", p.name if p.exists() else f"MISSING {lab}", p.stat().st_size // 1024 if p.exists() else 0, "KB")
    ensure_schedule()


if __name__ == "__main__":
    main()
