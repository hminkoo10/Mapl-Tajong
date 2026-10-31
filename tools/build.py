"""Windows 빌드: PyInstaller(폴더형) → Inno Setup 설치 파일 → SHA-256.

사용법 (Windows, 프로젝트 폴더에서):
    python tools\\build.py            # 실행 파일 + 설치 파일
    python tools\\build.py --no-installer

결과:
    dist\\Mataf\\Mataf.exe                         (설치 없이 실행해 볼 수 있는 폴더)
    dist\\installer\\MaplTajong-Setup-x.y.z.exe     (배포용 설치 파일)
    dist\\installer\\MaplTajong-Setup-x.y.z.exe.sha256
"""
import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def app_version():
    text = (ROOT / "app" / "core" / "version.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not m:
        sys.exit("app/core/version.py 에서 APP_VERSION 을 찾지 못했어요.")
    return m.group(1)


VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({t}),
    prodvers=({t}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Mapl'),
      StringStruct('FileDescription', 'Mapl Tajong'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'MaplTajong'),
      StringStruct('OriginalFilename', 'Mataf.exe'),
      StringStruct('ProductName', 'Mapl Tajong'),
      StringStruct('ProductVersion', '{v}')
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_version_info(version):
    BUILD.mkdir(parents=True, exist_ok=True)
    nums = [int(x) for x in version.split(".")] + [0]
    p = BUILD / "version_info.txt"
    p.write_text(VERSION_INFO.format(t=", ".join(map(str, nums[:4])), v=version), encoding="utf-8")
    return p


def run(cmd):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def build_exe(version):
    vi = write_version_info(version)
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "Mataf",
        "--icon", ROOT / "app" / "assets" / "ui" / "app.ico",
        "--version-file", vi,
        "--paths", ROOT,
        "--add-data", f"{ROOT / 'app' / 'assets'}{sep}assets",
        "--add-data", f"{ROOT / 'app' / 'data' / 'schema.sql'}{sep}app/data",
        "--collect-all", "imageio_ffmpeg",
        "--collect-all", "yt_dlp",
        "--distpath", DIST, "--workpath", BUILD / "pyinstaller", "--specpath", BUILD,
    ]
    if importlib.util.find_spec("yt_dlp_ejs"):
        args += ["--collect-all", "yt_dlp_ejs"]
    args.append(ROOT / "app" / "main.py")
    run(args)
    exe = DIST / "Mataf" / ("Mataf.exe" if os.name == "nt" else "Mataf")
    if not exe.exists():
        sys.exit("실행 파일이 만들어지지 않았어요.")
    return exe.parent


def find_iscc():
    cands = [os.environ.get("ISCC"), shutil.which("iscc"), shutil.which("ISCC")]
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            cands.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def build_installer(version, source_dir):
    iscc = find_iscc()
    if not iscc:
        sys.exit("Inno Setup 6(ISCC.exe)을 찾지 못했어요. https://jrsoftware.org/isdl.php 에서 설치해 주세요.")
    out = DIST / "installer"
    out.mkdir(parents=True, exist_ok=True)
    run([iscc, f"/DAppVersion={version}", f"/DSourceDir={source_dir}", f"/DOutputDir={out}",
         ROOT / "installer" / "MaplTajong.iss"])
    setup = out / f"MaplTajong-Setup-{version}.exe"
    if not setup.exists():
        sys.exit("설치 파일이 만들어지지 않았어요.")
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (out / (setup.name + ".sha256")).write_text(f"{digest}  {setup.name}\n", encoding="utf-8")
    return setup


def main():
    # 영어 Windows 콘솔(cp1252)에서도 한글 메시지가 깨지거나 멈추지 않도록
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-installer", action="store_true", help="설치 파일은 만들지 않음")
    a = ap.parse_args()
    version = app_version()
    print(f"마고 타종 {version} 빌드", flush=True)
    src = build_exe(version)
    if a.no_installer:
        print(f"완료: {src}")
        return
    setup = build_installer(version, src)
    print(f"완료: {setup}")


if __name__ == "__main__":
    main()
