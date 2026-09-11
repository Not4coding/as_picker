"""口播：提示词 + 游戏美术词库 + 100 条样本。有 COPY_API_KEY 且加 --ai 才走接口。"""
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from paths import MAIN as ROOT, PRODUCT, SOURCE

PROMPT = (ROOT / "prompt_copy.txt").read_text(encoding="utf-8")
LEX = json.loads((ROOT / "lexicon_game_art.json").read_text(encoding="utf-8"))
BANK = json.loads((ROOT / "copies_bank.json").read_text(encoding="utf-8")) if (ROOT / "copies_bank.json").exists() else []
SAMPLES = json.loads((ROOT / "copy_samples.json").read_text(encoding="utf-8")) if (ROOT / "copy_samples.json").exists() else []
PLACE = {
    "Thailand": "泰国", "France": "法国", "Poland": "波兰", "United States": "美国",
    "United Kingdom": "英国", "China": "中国", "Japan": "日本", "South Korea": "韩国",
    "Korea": "韩国", "Germany": "德国", "Canada": "加拿大", "Australia": "澳大利亚",
    "Brazil": "巴西", "Netherlands": "荷兰", "Spain": "西班牙", "Italy": "意大利",
}
CITY = {
    "Bangkok": "曼谷", "Paris": "巴黎", "Rouen": "鲁昂", "Warsaw": "华沙", "Seoul": "首尔",
    "London": "伦敦", "Dijon": "第戎", "Los Angeles": "洛杉矶", "New York": "纽约",
    "Shanghai": "上海", "Beijing": "北京", "Tokyo": "东京", "Berlin": "柏林",
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
    t = re.sub(r"\s+", " ", "".join(p.parts)).strip()
    t = t.replace("&amp;", "&").replace("&nbsp;", " ")
    t = re.sub(r"https?://\S+", "", t)
    return t.strip(" -|")


def kind_of(info: dict) -> str:
    blob = " ".join(
        [
            info.get("title") or "",
            (info.get("author") or {}).get("headline") or "",
            info.get("description") or "",
        ]
    ).lower()
    for label, keys in LEX["kinds"].items():
        if any(k.lower() in blob for k in keys):
            return label
    return "美术设定"


def focus_of(kind: str, i: int = 0) -> str:
    opts = LEX["focus"].get(kind) or LEX["focus"]["美术设定"]
    a, b = opts[i % len(opts)], opts[(i + 1) % len(opts)]
    return f"{a}和{b}" if a != b else a


def clean_role(raw: str) -> str:
    raw = (raw or "").replace("&amp;", "&")
    raw = raw.split("::")[0].split("联系")[0]
    raw = re.sub(r"[\w.+-]+@[\w.-]+", "", raw)
    raw = re.sub(r"(www\.\S+|https?://\S+)", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" .,:;|（）()")
    if not raw or re.search(r"(instagram|qq\s*:|ins\s*:)", raw, re.I) or raw.startswith("😊"):
        return ""
    return (raw[:36].rstrip() + "…") if len(raw) > 38 else raw


def place_of(loc: str) -> str:
    parts = [x.strip() for x in (loc or "").replace("，", ",").split(",") if x.strip()]
    if not parts or parts[0] in {"Fallgrim", "Earth"}:
        return CITY.get(parts[-1], parts[-1]) if len(parts) > 1 else ""
    if len(parts) >= 2:
        city, country = parts[0], parts[-1]
        return f"{PLACE.get(country, country)}{CITY.get(city, city)}"
    return PLACE.get(parts[0], CITY.get(parts[0], parts[0]))


def split_job(headline: str) -> tuple[str, str]:
    h = clean_role(headline)
    if not h:
        return "", ""
    m = re.search(r"(?i)\s+(?:at|@)\s+(.+)$", h)
    if m:
        return clean_role(h[: m.start()]) or "", re.sub(r"\s+", " ", m.group(1)).strip(" .")[:40]
    if "|" in h:
        h = h.split("|", 1)[0].strip()
    return h, ""


def from_experience(items: list) -> tuple[str, str]:
    if not items:
        return "", ""
    cur = next((x for x in items if not x.get("finish_date")), items[0])
    finish = (cur.get("finish_date") or "")[:4]
    if finish and finish.isdigit() and int(finish) < 2026:
        cur = items[0]
        finish = (cur.get("finish_date") or "")[:4]
        if finish and finish.isdigit() and int(finish) < 2026:
            return clean_role(cur.get("title") or ""), ""
    company = html_text(((cur.get("company") or {}).get("name") if isinstance(cur.get("company"), dict) else cur.get("company")) or "")
    return clean_role(cur.get("title") or ""), company[:40]


def author_bits(info: dict) -> tuple[str, str, str, str]:
    a = info.get("author") or {}
    name = (a.get("name") or a.get("username") or "这位作者").strip()
    role = a.get("role") or ""
    company = a.get("company") or ""
    if not role:
        role, c2 = split_job(a.get("headline") or "")
        company = company or c2
    if re.search(r"(?i)freelance|自由", (a.get("headline") or "") + role) and not company:
        company = ""
    role = zh_role(role)
    if not role:
        role = {"插画": "插画师", "概念设定": "概念设计师", "角色雕刻": "雕刻师", "场景概念": "环境概念设计师"}.get(kind_of(info), "美术")
    place = a.get("place") or place_of(a.get("location") or "")
    return name, role, place, company


def zh_role(role: str) -> str:
    r = role or ""
    r = re.sub(r"(?i)sr\.?\s*|senior\s*", "资深", r)
    r = re.sub(r"(?i)\bfreelance\b", "", r)
    for en, zh in (
        ("Art Director", "艺术总监"),
        ("Concept Artist", "概念设计师"),
        ("Sculptor", "雕刻师"),
        ("Illustrator", "插画师"),
        ("Character Artist", "角色艺术家"),
    ):
        r = re.sub(en, zh, r, flags=re.I)
    r = re.sub(r"\s+", " ", r).strip(" |,，")
    return r


def enrich_author(info: dict, profile: dict | None = None) -> dict:
    a = dict(info.get("author") or {})
    p = profile or {}
    loc = a.get("location") or ", ".join(x for x in [p.get("city"), p.get("country")] if x)
    role, company = split_job(a.get("headline") or p.get("headline") or "")
    r2, c2 = from_experience(p.get("experience_items") or a.get("experience") or [])
    if r2:
        role = role or r2
    if c2:
        company = c2
    a.update(
        {
            "location": loc,
            "place": place_of(loc),
            "role": role,
            "company": company,
            "followers": a.get("followers") or p.get("followers_count"),
            "projects": a.get("projects") or p.get("projects_count"),
            "headline": a.get("headline") or p.get("headline") or "",
        }
    )
    info["author"] = a
    return info


def excerpt_zh(desc: str, limit=70) -> str:
    desc = html_text(desc)
    desc = re.sub(
        r"^(hello[,!]?\s*(friends|everyone)?|hi[,!]?\s*(everyone)?|hey[,!]?|大家好)[!.！,， ]*",
        "",
        desc,
        flags=re.I,
    ).strip()
    if not desc or desc in {"爽爽", "Please enjoy!!", "Thank you"}:
        return ""
    if re.search(r"(instagram|linkedin|twitter|youtube|官网|公众号)", desc, re.I) and len(re.sub(r"[A-Za-z:/._ ]", "", desc)) < 8:
        return ""
    if re.search(r"[\u4e00-\u9fff]", desc):
        t = re.split(r"[。！？\n]", desc)[0].strip()
        return (t[: limit - 1] + "…") if len(t) > limit else t
    bits = []
    m = re.search(r"(?i)art director[:\s]+([A-Z][A-Za-z .'-]{2,40})", desc)
    if m:
        bits.append(f"艺术指导 {m.group(1).strip().rstrip('.')}")
    clients = []
    for pat, name in (
        (r"Wizards of the Coast", "威世智"),
        (r"\bD&D\b|Dungeons", "龙与地下城"),
        (r"Jellyfish Pictures", "Jellyfish Pictures"),
        (r"\bBBC\b", "BBC"),
        (r"Apple TV\+?", "Apple TV+"),
        (r"Naughty Dog", "Naughty Dog"),
        (r"Riot Games", "Riot"),
    ):
        if re.search(pat, desc, re.I) and name not in clients:
            clients.append(name)
    if clients:
        bits.append("给" + "、".join(clients) + "做的")
    tools = [t for t in ("ZBrush", "Marmoset", "Blender", "Maya", "Unreal") if t.lower() in desc.lower()]
    if tools:
        bits.append("用了" + "、".join(tools))
    return "，".join(bits[:3])


def likes_of(info: dict) -> int:
    try:
        return int(info.get("likes") or 0)
    except (TypeError, ValueError):
        return 0


def likes_line(n: int) -> str:
    if n <= 0:
        return ""
    if n >= 1000:
        return f"站内大约 {n} 个赞。"
    return f"目前 {n} 个赞。"


def who_line(info: dict) -> str:
    name, role, place, company = author_bits(info)
    head = f"作者是{place}的 {name}" if place else f"作者 {name}"
    tail = []
    if role and role != "美术":
        tail.append(role)
    if company:
        tail.append(f"目前在{company}" if "自由" not in company else company)
    return head + ("，" + "，".join(tail) if tail else "") + "。"


def clamp(text: str, close: str) -> str:
    text = re.sub(r"\s+", " ", text).replace(" 。", "。").strip()
    fills = ("信息以画面为准。", "过程图在原作页。")
    fi = 0
    while len(text) < 120 and fi < len(fills):
        text = text.replace(close, fills[fi] + close, 1)
        fi += 1
    if len(text) > 320:
        text = text[: 318 - len(close)].rstrip("。；，, ") + "。" + close
    return text


def build_auto(info: dict, i: int, variant: str) -> str:
    info = enrich_author(info)
    kind = kind_of(info)
    assets = int(info.get("assets_count") or 1)
    opens = LEX["open_set"] if assets >= 4 else LEX["open_one"]
    opening = opens[(i + (0 if variant == "a" else 3)) % len(opens)].format(kind=kind)
    title = (info.get("title") or "未命名").strip()
    mid = f"题目是《{title}》。" if variant == "a" else f"放出的是《{title}》。"
    ex = excerpt_zh(info.get("description") or "")
    body = f"简介里写到：{ex}。" if ex else "页面几乎没有说明，以画面为准。"
    likes = likes_line(likes_of(info))
    hint = (
        f"读图时优先看{focus_of(kind, i)}。"
        if variant == "a"
        else f"当项目材料看，盯{focus_of(kind, i + 1)}。"
    )
    close = LEX["close"][(i + (0 if variant == "a" else 2)) % len(LEX["close"])]
    return clamp(f"{opening}{who_line(info)}{mid}{body}{likes}{hint}{close}", close)


def fewshot(kind: str, n=3) -> list[str]:
    hits = [t for t in SAMPLES if kind in t]
    if len(hits) < n:
        hits = list(SAMPLES) + [r["text"] for r in BANK if kind in r.get("text", "")]
    return hits[:n]


def ai_copy(info: dict, variant: str, i: int) -> str | None:
    key = os.environ.get("COPY_API_KEY")
    if not key or "--ai" not in sys.argv:
        return None
    base = os.environ.get("COPY_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("COPY_MODEL", "gpt-4o-mini")
    info = enrich_author(info)
    kind = kind_of(info)
    name, role, place, company = author_bits(info)
    payload = {
        "model": model,
        "temperature": 0.8,
        "messages": [
            {"role": "system", "content": PROMPT + "\n词库看点：" + "、".join(LEX["focus"].get(kind, []))},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "variant": "读图" if variant == "a" else "项目背景",
                        "kind": kind,
                        "title": info.get("title"),
                        "author": name,
                        "role": role,
                        "place": place,
                        "company": company,
                        "likes": likes_of(info),
                        "description": html_text(info.get("description") or "")[:400],
                        "examples": fewshot(kind),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = json.load(r)["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("ai fail", e)
        return None
    text = re.sub(r"^```\w*\n?|```$", "", text).strip()
    close = LEX["close"][i % len(LEX["close"])]
    if "敬请欣赏" not in text:
        text = text.rstrip("。") + "。" + close
    return clamp(text, close)


def bank_map() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for r in BANK:
        out.setdefault(r["folder"], {})[r["variant"]] = r["text"]
    return out


def bigrams(s: str) -> set:
    s = re.sub(r"\s+", "", s)
    return {s[i : i + 2] for i in range(len(s) - 1)}


def jaccard(a: str, b: str) -> float:
    x, y = bigrams(a), bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def report(copies: list[str]):
    from collections import Counter

    opens = [re.split(r"[。！]", c, maxsplit=1)[0] + "。" for c in copies]
    cnt = Counter(opens)
    print("开场种类", len(cnt), "/", len(copies))
    worst = (0.0, -1, -1)
    for i in range(len(copies)):
        for j in range(i + 1, len(copies)):
            sim = jaccard(copies[i], copies[j])
            if sim > worst[0]:
                worst = (sim, i, j)
    print(f"最高两两重合 {worst[0]:.2f}  (#{worst[1]+1} vs #{worst[2]+1})")
    print("字数越界", sum(1 for c in copies if not (100 <= len(c) <= 300)))


def iter_works():
    folders = sorted(
        p
        for p in SOURCE.iterdir()
        if p.is_dir() and p.name != "Sample" and (p / "info.json").exists()
    )
    if "--top5" in sys.argv:
        folders = [p for p in folders if p.name[:2] in {"01", "02", "03", "04", "05"}]
    for folder in folders:
        info = enrich_author(json.loads((folder / "info.json").read_text(encoding="utf-8")))
        yield folder, info


def main():
    bm = bank_map()
    copies = []
    blocks = []
    for i, (folder, info) in enumerate(iter_works()):
        pair = bm.get(folder.name, {})
        for variant, dest in (("a", "copy.txt"), ("b", "copy_b.txt")):
            text = pair.get(variant) or ai_copy(info, variant, i) or build_auto(info, i, variant)
            (folder / dest).write_text(text, encoding="utf-8")
            copies.append(text)
            blocks.append(f"【{folder.name} / {variant}】\n{text}\n")
            print(folder.name[:24], variant, len(text), "字")
    out = PRODUCT / ("口播文案.txt" if "--top5" in sys.argv else "口播文案_100.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(blocks), encoding="utf-8")
    report(copies)
    print("->", out)


if __name__ == "__main__":
    main()
