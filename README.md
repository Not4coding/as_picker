# as_picker

ArtStation 3D Trending 选题 → 下载 → 口播文案 →（可选 TTS）→ 竖屏/横屏成片。

口播引擎已拆出，由你自行部署的独立容器后期接入（设置 `TTS_URL`）。本目录不含 CosyVoice、不含作品下载缓存、不含成片。

把整个 `bin` 拷到另一台 Windows 电脑，先跑一次 `setup.bat`，即可跑通选题/下载/文案；接上 TTS 后自动成片。

## 目录

```
bin/
  setup.bat / setup.py     首次安装：Python 虚拟环境 + 依赖 + 便携 ffmpeg
  run.bat                  跑一整轮流水线
  pipeline.py              编排：选题 100 取点赞前 5 → 下载 → 文案 → TTS → 成片
  download_top5.py         作品页资源下载
  write_copy.py            口播文案（规则模板；有 COPY_API_KEY 且 --ai 才走模型）
  write_subs.py            按 voice.wav 时长出字幕
  compose.py               ffmpeg 成片（竖屏 + 横屏）
  paths.py                 数据路径（默认同级 data\）
  prompt_copy.txt          文案提示词
  copy_samples.json        文案 few-shot
  lexicon_game_art.json    类型 / 看点词库
  copies_bank.json         历史口播样本
  seen.json                已选题尾缀（只增不删；没有则自动新建 []）
  requirements.txt         Pillow / soundfile / numpy
  ffmpeg/                  setup 后生成，勿提交
  .venv/                   setup 后生成，勿提交
  data/source/             下载的作品（运行时生成，勿当代码拷）
  data/product/            成片（运行时生成）
  fonts/                   可选：放入 msyh.ttc
```

## 另一台电脑怎么跑

1. 安装 [Python 3.10+](https://www.python.org/downloads/)，勾选 **Add python.exe to PATH**。
2. 复制整个 `bin` 文件夹。
3. 双击 `setup.bat`（需能访问外网：pip + ffmpeg 压缩包）。
4. 可选：把 `C:\Windows\Fonts\msyh.ttc`、`msyhbd.ttc` 拷进 `fonts\`。
5. 可选：把 BGM 的 mp3 放进 `data\source\Sample\Music\`（没有则成片不加背景乐）。
6. 双击 `run.bat`，或：

```bat
.venv\Scripts\python.exe pipeline.py
```

首次只做选题、下载、文案。没有 `TTS_URL` 时会跳过口播和成片，并写入 `seen.json`。

## 流水线做什么

1. 拉 ArtStation `projects.json?sorting=trending&dimension=3d` 前 100 条。
2. 去掉 `seen.json` 里已有的 `hash_id`。
3. 按点赞取 5 条。
4. 拉作品详情 / 作者资料（失败时把浏览器里的 JSON 存到 `_cache\{hash}.json`）。
5. 下载封面除外的图、视频、头像到 `data\source\{hash}_{标题}\`。
6. 写 `copy.txt`。
7. 若设置了 `TTS_URL`：向口播容器 `POST /tts`，正文为文件夹名，容器须把 `voice.wav` 写回同一目录。
8. 有 `voice.wav` 则出字幕并导出 `data\product\{文件夹}_竖屏.mp4` 与 `_横屏.mp4`。
9. 把这 5 个尾缀**追加**进 `seen.json`（自动化不删；人可以随便改、删文件）。

## 口播容器后期怎么接

容器与本流水线共享同一份 `data\source`（或设相同的 `AS_SOURCE`）。

- 环境变量：`TTS_URL=http://127.0.0.1:8080`（Docker 里写服务名，如 `http://tts:8080`）。
- 接口：`POST {TTS_URL}/tts`，body 为纯文本文件夹名（例如 `EYvLxK_City Of Umm Babir`）。
- 成功：该目录下出现 `voice.wav`，HTTP 200。
- 可选：`GET {TTS_URL}/health` 返回 `ok`。

本机示例：

```bat
set TTS_URL=http://127.0.0.1:8080
run.bat
```

## 环境变量

| 变量 | 默认 | 含义 |
|------|------|------|
| `AS_SOURCE` | `bin\data\source` | 作品目录 |
| `AS_PRODUCT` | `bin\data\product` | 成片目录 |
| `AS_DATA` | `bin\data` | 上面两项的根 |
| `AS_MUSIC` | `{AS_SOURCE}\Sample\Music` | BGM |
| `AS_FONT` / `AS_FONT_BD` | `fonts\` 或系统雅黑 | 成片字体 |
| `AS_CACHE` | `bin\_cache` | 作品/作者 JSON 缓存 |
| `TTS_URL` | 空 | 口播服务；空则跳过 TTS/成片 |
| `COPY_API_KEY` | 空 | 配合 `python write_copy.py --ai` 才走接口 |
| `AS_ENABLE_SCHEDULE` | 空 | 设为 1 才登记 Windows 每 12 小时任务 |
| `AS_SKIP_SCHEDULE` | 空 | 设了则不登记任务 |

## 单独跑某一步

```bat
.venv\Scripts\python.exe write_copy.py
.venv\Scripts\python.exe write_subs.py EYvLxK
.venv\Scripts\python.exe compose.py EYvLxK
```

`seen.json` 可手改。自动化只会往里加尾缀。文件不存在或坏了会重建为 `[]`。

## 依赖

- Python 3.10+（`requirements.txt`：Pillow、soundfile、numpy）
- ffmpeg / ffprobe（`setup.bat` 装到 `bin\ffmpeg\`）
- 成片需要中文字体（雅黑或 `AS_FONT`）
- 跑流水线需要能访问 ArtStation

不含：CosyVoice、GPU、作品原片、成片、BGM 曲库。

## 故障

**详情被拦 / 403**  
列表接口通常能通，作品页 JSON 可能被 Cloudflare 拦。用浏览器打开提示里的 `projects/{hash}.json`，另存为 `bin\_cache\{hash}.json` 后再跑。作者资料同理：`_cache\user_{username}.json`。

**找不到 ffmpeg**  
先跑 `setup.bat`，或把系统 `ffmpeg` 加到 PATH。

**成片缺字 / 方框**  
拷雅黑到 `fonts\`，或设 `AS_FONT` 指向任意中文 ttc/ttf。

**成片跳过**  
没有 `voice.wav`。先接入 `TTS_URL`，或自己把口播 wav 放到作品目录后再 `compose.py <hash>`。

**选题不够 5 条**  
`seen.json` 已覆盖当前 Trending 前 100 的大部分。人手删掉想重做的尾缀即可。

## 和本机目录的关系

本仓库就是 `as_picker\bin`。不要把 `source\`、`product\`、`cosyvoice\` 打进 git。拷到别的电脑时只拷这个文件夹。
