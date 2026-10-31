"""CI 확인용: 함께 넣는 PO 토큰 생성기와 YouTube 받기 흐름이 실제로 도는지 본다.

GitHub 러너는 데이터센터 IP라 YouTube가 막는 일이 잦으므로, 이 스크립트는 결과를 보여 주기만 하고
실패해도 빌드를 멈추지 않는다.  사용: python tools/yt_smoke.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.core import youtube, ytpot  # noqa: E402
from app.core.paths import app_data_dir, temp_dir  # noqa: E402

VIDEO = os.environ.get("SMOKE_VIDEO", "https://www.youtube.com/watch?v=jNQXAC9IVRw")


def main():
    print("yt-dlp:", youtube.version())
    print("deno:", youtube.deno_path())
    print("bgutil-pot:", ytpot.cli_path(), ytpot.cli_version())
    print("provider registered:", ytpot.register())

    if ytpot.available():
        t = time.monotonic()
        try:
            r = ytpot.run_cli(["-c", "jNQXAC9IVRw"], timeout=120)
            last = (r.stdout or "").strip().splitlines()[-1:] or [""]
            ok = r.returncode == 0 and "poToken" in last[0]
            print(f"PO 토큰 생성: {'성공' if ok else '실패'} ({time.monotonic() - t:.1f}s) rc={r.returncode}")
            if not ok:
                print((r.stderr or "")[-1500:])
        except Exception as e:
            print("PO 토큰 생성 오류:", e)

    t = time.monotonic()
    try:
        out = youtube.preview_clip(VIDEO, seconds=5, status_cb=lambda s: print("  ·", s))
        print(f"미리 듣기: 성공 {out} ({time.monotonic() - t:.1f}s)")
    except Exception as e:
        print(f"미리 듣기: 실패 ({time.monotonic() - t:.1f}s) {e}")
    log = app_data_dir() / "youtube.log"
    if log.exists():
        print("---- youtube.log ----")
        print(log.read_text(encoding="utf-8")[-4000:])
    for f in temp_dir().glob("yt_preview_*"):
        f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
