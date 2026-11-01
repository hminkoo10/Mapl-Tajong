@echo off
chcp 65001 > nul
REM 마고 타종 - 마고에듀 통합 클라우드용 묶음 파일 만들기
REM 필요: Python 3.10~3.12
REM 결과: dist\Mataf (실행 파일 폴더), dist\MaplTajong-x.y.z-win-x64.zip (+ .sha256)
REM YouTube 쪽은 자주 바뀌므로 빌드할 때마다 yt-dlp 를 최신으로 올려 줍니다.

python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt pyinstaller pillow
python tools\build.py
pause
