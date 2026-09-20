# version_manager.py
import json
import threading
import urllib.request

from logger import get_logger

log = get_logger()

CURRENT_VERSION = "1.0.0"
GITHUB_REPO = "NetShield0/NetShield" 
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_update(callback):
    """Arka planda güncelleme kontrolü yapar.
    callback(new_version, download_url) - yeni sürüm yoksa None, None
    """
    def worker():
        try:
            req = urllib.request.Request(
                GITHUB_API,
                headers={"User-Agent": "NetShield/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latest = data.get("tag_name", "").lstrip("v")
            if latest and latest != CURRENT_VERSION:
                # Sürüm karşılaştırması (basit)
                if _is_newer(latest, CURRENT_VERSION):
                    url = data.get("html_url", "")
                    callback(latest, url)
                    return
            callback(None, None)
        except Exception as e:
            log.info(f"Sürüm kontrolü başarısız: {e}")
            callback(None, None)

    threading.Thread(target=worker, daemon=True).start()


def _is_newer(a, b):
    """a, b'den yeni mi? (1.2.0 > 1.1.5)"""
    try:
        pa = [int(x) for x in a.split(".")]
        pb = [int(x) for x in b.split(".")]
        return pa > pb
    except Exception:
        return False