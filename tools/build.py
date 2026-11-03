"""Windows 빌드: PyInstaller(폴더형) → 마고에듀 통합 클라우드용 묶음 파일(zip) → SHA-256.

사용법 (Windows, 프로젝트 폴더에서):
    python tools\\build.py            # 실행 파일 폴더 + 묶음 파일
    python tools\\build.py --no-zip   # 실행 파일 폴더만

결과:
    dist\\Mataf\\Mataf.exe                          (실행 파일 폴더, magoedu-app.json·LICENSE.txt 포함)
    dist\\MaplTajong-x.y.z-win-x64.zip             (배포용 묶음 파일 — 통합 클라우드가 받아 설치)
    dist\\MaplTajong-x.y.z-win-x64.zip.sha256
"""
import argparse
import ast
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

# 검토한 순수 Python 로직만 컴파일한다. 누락/컴파일 실패 시 .py 로 대체하지 않는다.
# 제외: main.py, ui/** (진입점/Qt), core/cloud_sync.py, single_instance.py,
# startup.py (Qt import), core/paths.py, ytpot.py (__file__ 기반 경로).
# core/weather.py 는 정의되지 않은 _shorter() 호출로 Cython 컴파일 불가 (원본 유지).
CYTHON_INCLUDE = (
    "app.core.audio_edit",
    "app.core.backup",
    "app.core.bootstrap",
    "app.core.data_sign",
    "app.core.ffmpeg",
    "app.core.google_login",
    "app.core.magoedu_cloud",
    "app.core.net",
    "app.core.player",
    "app.core.scheduler",
    "app.core.sound_files",
    "app.core.timeutil",
    "app.core.version",
    "app.core.watchdog",
    "app.core.youtube",
    "app.data.db",
    "app.data.repo",
)


def cython_hidden_imports(stage):
    """네이티브화로 보이지 않게 되는 import 를 삭제 전 복사본에서 수집한다."""
    hidden = set(CYTHON_INCLUDE)
    for name in CYTHON_INCLUDE:
        source = stage.joinpath(*name.split(".")).with_suffix(".py")
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                hidden.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
                module = node.module or ""
                if node.level:
                    module = importlib.util.resolve_name("." * node.level + module, name.rpartition(".")[0])
                hidden.add(module)
                # from app.core import ffmpeg 등: 함수/상수가 아닌 하위 모듈도 포함.
                for alias in node.names:
                    child = f"{module}.{alias.name}"
                    path = stage.joinpath(*child.split("."))
                    if path.with_suffix(".py").is_file() or path.is_dir():
                        hidden.add(child)
    return sorted(hidden)


def native_module_exists(base, name):
    path = base.joinpath(*name.split("."))
    return any(path.with_suffix(suffix).is_file() for suffix in importlib.machinery.EXTENSION_SUFFIXES)


def prepare_cython_app():
    """app 원본은 건드리지 않고 build/cyapp 안에서만 복사·컴파일·소스 정리."""
    stage = BUILD / "cyapp"
    # junction/symlink 를 통해 작업 폴더 밖이나 원본을 지우지 않도록 확인한다.
    if stage.resolve() != stage:
        raise RuntimeError(f"스테이징 경로가 다른 위치를 가리켜요: {stage}")
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(ROOT / "app", stage / "app",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.pyd", "*.so", "*.c"))
    hidden = cython_hidden_imports(stage)
    setup = stage / "setup.py"
    setup.write_text(
        "from setuptools import Extension, setup\n"
        "from Cython.Build import cythonize\n\n"
        f"modules = {CYTHON_INCLUDE!r}\n"
        "setup(\n"
        "    name='tajong-native',\n"
        "    packages=[],\n"
        "    ext_modules=cythonize(\n"
        "        [Extension(name, [name.replace('.', '/') + '.py']) for name in modules],\n"
        "        language_level=3,\n"
        # 타입 힌트/자동 추론으로 Python 객체가 C 타입으로 바뀌지 않게 한다.
        "        compiler_directives={'annotation_typing': False, 'infer_types': False, 'binding': True},\n"
        "    ),\n"
        ")\n",
        encoding="utf-8",
    )
    run([sys.executable, setup, "build_ext", "--inplace"], cwd=stage)
    missing = [name for name in CYTHON_INCLUDE if not native_module_exists(stage, name)]
    if missing:
        raise RuntimeError("Cython 컴파일 결과가 없어요: " + ", ".join(missing))
    # 모든 모듈 성공을 확인한 뒤에만 스테이징의 .py/.c 를 없앤다.
    for name in CYTHON_INCLUDE:
        source = stage.joinpath(*name.split(".")).with_suffix(".py")
        source.unlink()
        source.with_suffix(".c").unlink()
    return stage, hidden


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


def windows_icon():
    """exe/설치 파일 아이콘. app.ico 는 tools/build_icons.py 가 만든 진짜 ICO(16~256)라 그대로 쓰고, PNG 그림이면 ICO로 바꾼다."""
    src = ROOT / "app" / "assets" / "ui" / "app.ico"
    if src.read_bytes()[:4] == b"\x00\x00\x01\x00":
        return src
    from PIL import Image
    BUILD.mkdir(parents=True, exist_ok=True)
    dst = BUILD / "app_win.ico"
    im = Image.open(src).convert("RGBA").resize((256, 256), Image.LANCZOS)
    sizes = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 100, 128, 256)]
    im.save(dst, format="ICO", sizes=sizes, bitmap_format="bmp")
    return dst


def find_deno():
    """YouTube 처리에 필요한 deno(자바스크립트 실행기). pip 패키지 'deno' 에 들어 있다."""
    try:
        import deno
        p = deno.find_deno_bin()
        if p and Path(p).exists():
            return Path(p)
    except Exception:
        pass
    w = shutil.which("deno")
    return Path(w) if w else None


def find_pot():
    """YouTube 봇 확인을 통과하는 증명값(PO 토큰) 생성기 bgutil-pot.
    CI가 build/bin 에 받아 두고(체크섬 확인), 직접 빌드할 때는 BGUTIL_POT 로 위치를 알려 줄 수 있다."""
    name = "bgutil-pot.exe" if os.name == "nt" else "bgutil-pot"
    for c in (os.environ.get("BGUTIL_POT"), BUILD / "bin" / name, shutil.which("bgutil-pot")):
        if c and Path(c).is_file():
            return Path(c)
    return None


# 쓰지 않는 Qt 파일 (_internal 기준). 묶음 파일과 업데이트 크기를 줄인다.
PRUNE = [
    "PyQt6/Qt6/translations",
    "PyQt6/Qt6/plugins/tls",
    "PyQt6/Qt6/plugins/networkinformation",
    "PyQt6/Qt6/plugins/generic",
    "PyQt6/Qt6/plugins/imageformats/*pdf*",
    "PyQt6/Qt6/plugins/imageformats/*tiff*",
    "PyQt6/Qt6/plugins/imageformats/*wbmp*",
    "PyQt6/Qt6/plugins/imageformats/*icns*",
    "PyQt6/Qt6/plugins/imageformats/*tga*",
    "PyQt6/Qt6/bin/opengl32sw.dll",
    "PyQt6/Qt6/bin/d3dcompiler_47.dll",
    "PyQt6/Qt6/bin/Qt6Pdf.dll",
    # Qt6Network 는 지우지 않는다: 두 번째 실행이 켜진 창을 여는 데 씀 (app/core/single_instance.py)
]


def _size(p):
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def prune(app_dir):
    internal = app_dir / "_internal"
    saved = 0
    for pattern in PRUNE:
        for target in internal.glob(pattern):
            saved += _size(target)
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
    print(f"쓰지 않는 파일 정리: {saved / 1048576:.1f}MB 줄임", flush=True)


def run(cmd, cwd=ROOT):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def build_exe(version, icon, need_deno=True):
    stage, hidden = prepare_cython_app()
    vi = write_version_info(version)
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "Mataf",
        "--icon", icon,
        "--version-file", vi,
        "--paths", stage,
        "--add-data", f"{ROOT / 'app' / 'assets'}{sep}assets",
        "--add-data", f"{ROOT / 'app' / 'data' / 'schema.sql'}{sep}app/data",
        "--add-data", f"{ROOT / 'CHANGELOG.md'}{sep}.",
        "--add-data", f"{ROOT / 'THIRD_PARTY_NOTICES.md'}{sep}.",
        "--exclude-module", "tkinter",
        "--collect-all", "imageio_ffmpeg",
        "--collect-all", "yt_dlp",
        "--distpath", DIST, "--workpath", BUILD / "pyinstaller", "--specpath", BUILD,
    ]
    for name in hidden:
        args += ["--hidden-import", name]
    if importlib.util.find_spec("yt_dlp_ejs"):
        args += ["--collect-all", "yt_dlp_ejs"]
    deno = find_deno()
    if deno:
        args += ["--add-binary", f"{deno}{sep}."]
        print(f"deno 포함: {deno}", flush=True)
    elif need_deno:
        sys.exit("deno 를 찾지 못했어요. 'pip install deno' 후 다시 빌드해 주세요. (YouTube 받기에 필요)")
    pot = find_pot()
    if pot:
        if pot.name != ("bgutil-pot.exe" if os.name == "nt" else "bgutil-pot"):
            sys.exit(f"{pot} 의 이름을 bgutil-pot(.exe) 로 바꿔 주세요.")
        args += ["--add-binary", f"{pot}{sep}."]
        print(f"bgutil-pot 포함: {pot}", flush=True)
    elif need_deno:
        sys.exit("bgutil-pot 을 찾지 못했어요. build/bin 에 넣거나 BGUTIL_POT 로 알려 주세요. "
                 "(--no-deno 로 YouTube 구성 요소 없이 빌드할 수 있어요)")
    args.append(stage / "app" / "main.py")
    # 작업 디렉터리도 스테이징으로 고정해 저장소의 app/*.py 가 섞이지 않게 한다.
    run(args, cwd=stage)
    exe = DIST / "Mataf" / ("Mataf.exe" if os.name == "nt" else "Mataf")
    if not exe.exists():
        sys.exit("실행 파일이 만들어지지 않았어요.")
    missing = [name for name in CYTHON_INCLUDE if not native_module_exists(exe.parent / "_internal", name)]
    if missing:
        raise RuntimeError("배포 폴더에 Cython 모듈이 없어요: " + ", ".join(missing))
    prune(exe.parent)
    return exe.parent


def write_manifest(app_dir, version):
    """magoedu-app.json (저장소 맨 위) 에 버전을 넣어 실행 파일 폴더에 둔다. 통합 클라우드가 이것을 읽는다."""
    m = json.loads((ROOT / "magoedu-app.json").read_text(encoding="utf-8"))
    m["version"] = version
    exe = m.get("exe", "")
    if not (app_dir / exe).exists():
        sys.exit(f"magoedu-app.json 의 exe({exe})가 {app_dir} 에 없어요.")
    (app_dir / "magoedu-app.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_license(app_dir):
    """저장소의 LICENSE(GitHub 와 같은 AGPL-3.0)를 실행 파일 폴더 맨 위에 LICENSE.txt 로 둔다 (묶음 파일에도 들어감)."""
    shutil.copyfile(ROOT / "LICENSE", app_dir / "LICENSE.txt")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_zip(version, app_dir):
    """실행 파일 폴더의 내용을 zip 맨 위에 담는다 (magoedu-app.json 포함)."""
    out = DIST / f"MaplTajong-{version}-win-x64.zip"
    part = out.with_name(out.name + ".part")
    files = sorted(f for f in app_dir.rglob("*") if f.is_file())
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(app_dir).as_posix())
    part.replace(out)
    (DIST / (out.name + ".sha256")).write_text(f"{_sha256(out)}  {out.name}\n", encoding="utf-8")
    print(f"묶음 파일: {out.name} ({out.stat().st_size / 1048576:.1f}MB, 파일 {len(files)}개)", flush=True)
    return out


def main():
    # 영어 Windows 콘솔(cp1252)에서도 한글 메시지가 깨지거나 멈추지 않도록
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true", help="묶음 파일(zip)은 만들지 않음")
    ap.add_argument("--no-deno", action="store_true", help="deno 없이 빌드 (YouTube 받기가 제한될 수 있음)")
    a = ap.parse_args()
    version = app_version()
    print(f"마고 타종 {version} 빌드", flush=True)
    icon = windows_icon()
    src = build_exe(version, icon, need_deno=not a.no_deno)
    write_manifest(src, version)
    copy_license(src)
    if a.no_zip:
        print(f"완료: {src}")
        return
    pack = build_zip(version, src)
    print(f"완료: {pack}")


if __name__ == "__main__":
    main()
