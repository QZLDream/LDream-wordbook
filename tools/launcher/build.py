"""把 launcher.c 编译成 Windows 程序「小梦的词书.exe」，放在项目根目录。

    pip install ziglang
    python tools/launcher/build.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "小梦的词书.exe"
(ROOT / "启动辞书.exe").unlink(missing_ok=True)  # 旧版本的名字

cmd = [sys.executable, "-m", "ziglang", "build-exe", "launcher.c", "launcher.rc", "-lc", "-target", "x86_64-windows-gnu",
       "-O", "ReleaseSmall", "--subsystem", "windows", "-fstrip", "-lshell32", "-luser32", "--name", "launcher"]
subprocess.run(cmd, cwd=HERE, check=True)
shutil.move(str(HERE / "launcher.exe"), OUT)
for junk in HERE.glob("launcher.pdb"):
    junk.unlink()
print(f"{OUT.name}: {OUT.stat().st_size / 1024:.0f} KB")
