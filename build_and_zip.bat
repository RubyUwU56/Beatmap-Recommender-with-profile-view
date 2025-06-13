@echo off
cd /d %~dp0

echo [*] Baue EXE...
pyinstaller --noconfirm --onefile --windowed ^
--add-data "osu_logo.png;." ^
--add-data "config.json;." ^
main.py

if not exist dist\main.exe (
    echo [!] Fehler: EXE wurde nicht erstellt.
    pause
    exit /b
)

echo [*] Kopiere Ressourcen in dist...
copy config.json dist\ >nul
copy osu_logo.png dist\ >nul

echo [*] Erstelle ZIP...
cd dist
powershell -Command "Compress-Archive -Path main.exe, config.json, osu_logo.png -DestinationPath osu_viewer_release.zip -Force"

echo [✓] Fertig! Datei: dist\osu_viewer_release.zip
pause
