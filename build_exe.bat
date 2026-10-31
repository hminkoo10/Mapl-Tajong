@echo off
chcp 65001 > nul
REM 마고 타종 - Windows 설치 파일 만들기
REM 필요: Python 3.10~3.12, Inno Setup 6.3 이상 (https://jrsoftware.org/isdl.php)
REM 결과: dist\installer\MaplTajong-Setup-x.y.z.exe
REM YouTube 쪽은 자주 바뀌므로 빌드할 때마다 yt-dlp 를 최신으로 올려 줍니다.

python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt pyinstaller
python tools\build.py
pause
