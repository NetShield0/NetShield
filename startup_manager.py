# startup_manager.py
import os
import sys
import winreg
from pathlib import Path

from logger import get_logger

log = get_logger()

APP_NAME = "AgKontrolMerkezi"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_launch_command():
    """Uygulamanın başlatma komutunu üretir."""
    if getattr(sys, "frozen", False):
        # PyInstaller .exe
        return f'"{sys.executable}"'
    # Python script
    script = Path(__file__).parent / "main.py"
    return f'"{sys.executable}" "{script}"'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, APP_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception as e:
        log.error(f"Registry okuma hatası: {e}")
        return False


def enable():
    try:
        cmd = _get_launch_command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        log.info(f"Otomatik başlatma açıldı: {cmd}")
        return True, "Otomatik başlatma açıldı."
    except Exception as e:
        log.error(f"Registry yazma hatası: {e}")
        return False, f"Hata: {e}"


def disable():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        log.info("Otomatik başlatma kapatıldı.")
        return True, "Otomatik başlatma kapatıldı."
    except Exception as e:
        log.error(f"Registry silme hatası: {e}")
        return False, f"Hata: {e}"