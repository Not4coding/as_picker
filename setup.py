"""首次部署：建虚拟环境、装依赖、拉便携 ffmpeg。"""
import io
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
FFMPEG_ZIP = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.check_call(cmd)


def ensure_venv() -> Path:
    venv = BIN / ".venv"
    py = venv / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if not py.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    run([str(py), "-m", "pip", "install", "-U", "pip"])
    run([str(py), "-m", "pip", "install", "-r", str(BIN / "requirements.txt")])
    return py


def ensure_ffmpeg():
    exe = BIN / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if exe.exists():
        print("ffmpeg 已在", exe)
        return
    print("下载 ffmpeg …")
    data = urllib.request.urlopen(FFMPEG_ZIP, timeout=180).read()
    dest = BIN / "ffmpeg"
    dest.mkdir(parents=True, exist_ok=True)
    import shutil

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.namelist():
            base = Path(member).name.lower()
            if base not in {"ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"}:
                continue
            if Path(member).parent.name.lower() not in {"bin", ""} and "/" in member.replace("\\", "/"):
                if "/bin/" not in member.replace("\\", "/"):
                    continue
            raw = z.read(member)
            (dest / base).write_bytes(raw)
    if not exe.exists():
        sys.exit("ffmpeg 解压失败")
    print("ffmpeg →", exe)


def main():
    (BIN / "data" / "source").mkdir(parents=True, exist_ok=True)
    (BIN / "data" / "product").mkdir(parents=True, exist_ok=True)
    (BIN / "fonts").mkdir(parents=True, exist_ok=True)
    ensure_venv()
    ensure_ffmpeg()
    print("就绪。运行 run.bat 或: .venv\\Scripts\\python.exe pipeline.py")


if __name__ == "__main__":
    main()
