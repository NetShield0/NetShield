# speedtest_manager.py
import threading
import time
import urllib.request
from logger import get_logger

log = get_logger()


def test_download(progress_cb=None, cancel_event=None, duration=8):
    """Cloudflare (yedek: Hetzner) üzerinden download hızı ölçer (Mbps)."""
    # Birden fazla sunucu dene
    servers = [
        "https://speed.cloudflare.com/__down?bytes=100000000",
        "https://speedtest.tele2.net/100MB.zip",
        "https://proof.ovh.net/files/100Mb.dat",
        "http://ipv4.download.thinkbroadband.com/100MB.zip",
    ]

    for url in servers:
        if cancel_event and cancel_event.is_set():
            return None

        log.info(f"Download sunucusu deneniyor: {url.split('/')[2]}")

        try:
            start = time.time()
            bytes_read = 0

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",
                    "Connection": "keep-alive",
                },
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    log.warning(f"HTTP {resp.status}, sonraki sunucuya geçiliyor")
                    continue

                chunk = 65536
                while True:
                    if cancel_event and cancel_event.is_set():
                        return None
                    if time.time() - start > duration:
                        break

                    try:
                        data = resp.read(chunk)
                    except Exception as e:
                        log.warning(f"Read hatası: {e}")
                        break

                    if not data:
                        break
                    bytes_read += len(data)

                    if progress_cb:
                        elapsed = time.time() - start
                        if elapsed > 0.3:
                            speed = (bytes_read * 8) / (elapsed * 1_000_000)
                            progress_cb(speed)

            elapsed = time.time() - start
            if bytes_read < 100_000:
                log.warning(f"Az veri ({bytes_read} byte), sonraki sunucu")
                continue

            speed_mbps = (bytes_read * 8) / (elapsed * 1_000_000)
            log.info(f"✅ Download: {speed_mbps:.2f} Mbps ({url.split('/')[2]})")
            return round(speed_mbps, 2)

        except urllib.error.HTTPError as e:
            log.warning(f"HTTP {e.code} ({url.split('/')[2]}), sonraki sunucu")
            continue
        except Exception as e:
            log.warning(f"Hata ({url.split('/')[2]}): {type(e).__name__}")
            continue

    log.error("Tüm download sunucuları başarısız")
    return None


def test_upload(progress_cb=None, cancel_event=None, duration=8):
    """Cloudflare üzerinden upload hızı ölçer (Mbps)."""
    url = "https://speed.cloudflare.com/__up"

    try:
        # 5 MB veri hazırla
        data = b"0" * (5 * 1024 * 1024)

        start = time.time()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={
                "User-Agent": "DPI-App/1.0",
                "Content-Type": "application/octet-stream",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()

        elapsed = time.time() - start
        speed_mbps = (len(data) * 8) / (elapsed * 1_000_000)

        if progress_cb:
            progress_cb(speed_mbps)

        return round(speed_mbps, 2)

    except Exception as e:
        log.error(f"Upload testi hatası: {e}")
        return None


def test_ping(host="1.1.1.1", count=4):
    """Ping testi - ortalama ms döner."""
    import subprocess
    from logger import get_logger

    try:
        r = subprocess.run(
            ["ping", "-n", str(count), host],
            capture_output=True, text=True,
            encoding="utf-8", errors="ignore",
            creationflags=0x08000000, timeout=15,
        )
        import re
        m = re.search(r"(?:Ortalama|Average)\s*=\s*(\d+)ms", r.stdout)
        if m:
            return int(m.group(1))
        m = re.search(r"=\s*(\d+)ms", r.stdout)
        if m:
            return int(m.group(1))
    except Exception as e:
        log.error(f"Ping hatası: {e}")
    return None


def run_full_test(progress_cb=None, cancel_event=None):
    """
    Tam hız testi: ping → download → upload.
    progress_cb(stage, value) şeklinde çağrılır.
    Sonuç: {"ping": int, "download": float, "upload": float}
    """
    result = {"ping": None, "download": None, "upload": None}

    # 1) Ping
    if progress_cb:
        progress_cb("ping", None)
    result["ping"] = test_ping()

    if cancel_event and cancel_event.is_set():
        return result

    # 2) Download
    if progress_cb:
        progress_cb("download_start", None)

    def dl_progress(speed):
        if progress_cb:
            progress_cb("download", speed)

    result["download"] = test_download(
        progress_cb=dl_progress, cancel_event=cancel_event
    )

    if cancel_event and cancel_event.is_set():
        return result

    # 3) Upload
    if progress_cb:
        progress_cb("upload_start", None)

    def ul_progress(speed):
        if progress_cb:
            progress_cb("upload", speed)

    result["upload"] = test_upload(
        progress_cb=ul_progress, cancel_event=cancel_event
    )

    if progress_cb:
        progress_cb("done", result)

    return result