import json
import re
import ssl
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from paths import SOURCE as SRC

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "top5.json"
CTX = ssl.create_default_context()
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://www.artstation.com/",
    "Accept": "*/*",
}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def html_text(s: str) -> str:
    p = _Text()
    p.feed(s or "")
    return re.sub(r"\n{3,}", "\n\n", "".join(p.parts)).strip()


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", (s or "untitled").strip())
    return s[:80].rstrip(". ") or "untitled"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, context=CTX, timeout=180) as r:
        return r.read()


def best_image(url: str) -> tuple[bytes, str]:
    for kind in ("4k", "large"):
        trial = url.replace("/large/", f"/{kind}/")
        try:
            data = fetch(trial)
            if data[:20].lstrip().startswith((b"<", b"{")):
                continue
            return data, trial
        except urllib.error.HTTPError:
            continue
    return fetch(url), url


def ext_from(url: str, data: bytes, default: str) -> str:
    low = url.lower().split("?", 1)[0]
    for e in (".png", ".webp", ".gif", ".mp4", ".webm", ".jpg", ".jpeg"):
        if low.endswith(e):
            return ".jpg" if e == ".jpeg" else e
    if data[:3] == b"GIF":
        return ".gif"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return default


def write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  {path.name}  {len(data)//1024} KB")


def download_work(w: dict, folder: Path, rank: int = 0):
    folder.mkdir(parents=True, exist_ok=True)
    u = w.get("user") or {}
    info = {
        "hash": w.get("hash") or w.get("hash_id") or folder.name.split("_", 1)[0],
        "rank": rank or w.get("rank") or 0,
        "title": w.get("title"),
        "url": w.get("permalink") or w.get("url"),
        "likes": w.get("likes") or w.get("likes_count"),
        "views": w.get("views") or w.get("views_count"),
        "description": html_text(w.get("description") or ""),
        "assets_count": len(w.get("assets") or []),
        "author": {
            "name": u.get("full_name") or u.get("name"),
            "username": u.get("username"),
            "headline": u.get("headline") or "",
            "location": u.get("location") or ", ".join(x for x in [u.get("city"), u.get("country")] if x),
            "role": u.get("role") or "",
            "company": u.get("company") or "",
            "experience": u.get("experience_items") or u.get("experience") or [],
            "followers": u.get("followers") or u.get("followers_count"),
            "following": u.get("following") or u.get("following_count"),
            "projects": u.get("projects") or u.get("projects_count"),
            "profile": u.get("permalink") or u.get("artstation_profile_url"),
        },
    }
    from write_copy import enrich_author

    info = enrich_author(info, u)
    (folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    a = info["author"]
    (folder / "info.txt").write_text(
        f"{info['title']}\n{info['url']}\n点赞 {info['likes']}\n\n"
        f"作者 {a['name']} (@{a['username']})\n{a.get('role') or a['headline']}\n"
        f"{a['location']}  {a.get('company') or ''}\n粉丝 {a['followers']}  作品 {a['projects']}\n"
        f"{a['profile']}\n\n{info['description']}\n",
        encoding="utf-8",
    )
    print(folder.name)
    avatar = u.get("avatar") or u.get("large_avatar_url") or u.get("medium_avatar_url")
    if avatar:
        try:
            data = fetch(avatar)
            write(folder / f"avatar{ext_from(avatar, data, '.jpg')}", data)
        except Exception as e:
            print("  avatar FAIL", e)

    n_img = n_vid = n_gif = 0
    for a in w.get("assets") or []:
        try:
            kind = a.get("asset_type") or a.get("type") or "image"
            if kind == "cover":
                continue
            if kind in {"video_clip", "video"} and a.get("video_url"):
                n_vid += 1
                data = fetch(a["video_url"])
                write(folder / f"video_{n_vid:02d}{ext_from(a['video_url'], data, '.mp4')}", data)
                if a.get("image_url"):
                    poster, _ = best_image(a["image_url"])
                    write(folder / f"video_{n_vid:02d}_poster.jpg", poster)
                continue
            url = a.get("image_url") or ""
            if not url or kind in {"video_clip", "video"}:
                continue
            data, used = best_image(url)
            ext = ext_from(used, data, ".jpg")
            if ext == ".gif":
                n_gif += 1
                name = f"gif_{n_gif:02d}.gif"
            else:
                n_img += 1
                name = f"image_{n_img:02d}_{kind}{ext}"
            write(folder / name, data)
        except Exception as e:
            print("  asset FAIL", a.get("id"), e)
    return info, n_img, n_vid, n_gif


def main():
    works = json.loads(MANIFEST.read_text(encoding="utf-8"))
    SRC.mkdir(parents=True, exist_ok=True)
    for i, w in enumerate(works, 1):
        download_work(w, SRC / f"{i:02d}_{safe_name(w['title'])}", i)


if __name__ == "__main__":
    main()
