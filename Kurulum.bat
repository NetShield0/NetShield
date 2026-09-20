@echo off
chcp 65001 >nul
title NetShield - Kurulum
color 0B

echo.
echo  ███╗   ██╗███████╗████████╗███████╗██╗  ██╗██╗███████╗██╗     ██████╗ 
echo  ████╗  ██║██╔════╝╚══██╔══╝██╔════╝██║  ██║██║██╔════╝██║     ██╔══██╗
echo  ██╔██╗ ██║█████╗     ██║   ███████╗███████║██║█████╗  ██║     ██║  ██║
echo  ██║╚██╗██║██╔══╝     ██║   ╚════██║██╔══██║██║██╔══╝  ██║     ██║  ██║
echo  ██║ ╚████║███████╗   ██║   ███████║██║  ██║██║███████╗███████╗██████╔╝
echo  ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═════╝ 
echo.
echo  DPI Bypass + VPN + DNS Gizliligi
echo  -----------------------------------
echo.

:: Python kontrolu
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python bulunamadi!
    echo.
    echo Lutfen Python 3.10+ kurun: https://www.python.org/downloads/
    echo Kurulum sirasinda "Add Python to PATH" secenegini isaretleyin.
    echo.
    pause
    exit /b 1
)

echo [OK] Python bulundu.
echo.
echo [*] Gerekli paketler yukleniyor...
echo.

pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [!] Paket yukleme hatasi!
    pause
    exit /b 1
)

echo.
echo [OK] Kurulum tamamlandi!
echo.
echo Simdi "Baslat.bat" dosyasina cift tiklayarak uygulamayi acabilirsiniz.
echo.
pause