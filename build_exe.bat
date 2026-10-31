@echo off
chcp 65001 > nul
REM 마고 타종 2.0 - Windows 실행 파일 만들기
REM 프로젝트 폴더에서 실행하면 dist\Mataf.exe 가 만들어집니다.
REM YouTube 쪽은 자주 바뀌므로 빌드할 때마다 yt-dlp 를 최신으로 올려 주세요.

python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Mataf ^
  --icon app\assets\ui\app.ico ^
  --version-file version_info.txt ^
  --add-data "app\assets;assets" ^
  --add-data "app\data\schema.sql;app\data" ^
  --collect-all imageio_ffmpeg ^
  --collect-all yt_dlp ^
  --collect-all yt_dlp_ejs ^
  app\main.py

echo.
echo 완료: dist\Mataf.exe
echo (선택) deno.exe 를 Mataf.exe 와 같은 폴더에 두면 YouTube 다운로드가 더 안정적이에요.
pause
