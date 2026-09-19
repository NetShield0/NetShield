# tray_manager.py
import threading
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

from logger import get_logger

log = get_logger()

BASE_DIR = Path(__file__).parent.resolve()
ICON_PATH = BASE_DIR / "assets" / "netshield.ico"


def _make_fallback_icon(color="#0A84FF", size=64):
    """Basit daire ikon (fallback)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, size - 6, size - 6), fill=color)
    draw.ellipse((size//2 - 4, size//2 - 4, size//2 + 4, size//2 + 4), fill="#FFFFFF")
    return img


def _load_icon(active=False):
    """assets/netshield.ico dosyasını yükler. Aktifse yeşil nokta ekler."""
    try:
        if ICON_PATH.exists():
            icon = Image.open(str(ICON_PATH)).convert("RGBA")
            # 64x64'e getir
            icon = icon.resize((64, 64), Image.LANCZOS)

            if active:
                # Sağ alt köşeye yeşil nokta ekle
                draw = ImageDraw.Draw(icon)
                w, h = icon.size
                r = w // 4
                margin = 2
                draw.ellipse(
                    (w - r - margin, h - r - margin, w - margin, h - margin),
                    fill="#30D158",
                    outline="#FFFFFF",
                    width=2,
                )
            return icon
    except Exception as e:
        log.warning(f"İkon yükleme hatası: {e}")

    return _make_fallback_icon("#30D158" if active else "#55555A")


class TrayManager:
    def __init__(self, on_show, on_toggle_bypass, on_quit):
        self.on_show = on_show
        self.on_toggle_bypass = on_toggle_bypass
        self.on_quit = on_quit
        self.icon = None
        self._active = False
        self._thread = None

    def _menu(self):
        return pystray.Menu(
            pystray.MenuItem("Paneli Aç", self._on_show, default=True),
            pystray.MenuItem("Bypass Aç/Kapat", self._on_toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Çıkış", self._on_quit),
        )

    def start(self):
        if self.icon is not None:
            return
        self.icon = pystray.Icon(
            "NetShield",
            icon=_load_icon(active=False),
            title="NetShield",
            menu=self._menu(),
        )
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()
        log.info("Tray ikonu başlatıldı.")

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def set_active(self, active: bool):
        self._active = active
        if not self.icon:
            return
        try:
            self.icon.icon = _load_icon(active=active)
            self.icon.title = (
                "NetShield (Aktif)" if active else "NetShield"
            )
        except Exception as e:
            log.warning(f"Tray güncelleme hatası: {e}")

    def _on_show(self, icon, item):
        try:
            self.on_show()
        except Exception as e:
            log.error(f"Show hatası: {e}")

    def _on_toggle(self, icon, item):
        try:
            self.on_toggle_bypass()
        except Exception as e:
            log.error(f"Toggle hatası: {e}")

    def _on_quit(self, icon, item):
        try:
            self.stop()
            self.on_quit()
        except Exception as e:
            log.error(f"Quit hatası: {e}")


def notify(title, message, duration=5):
    """Windows toast bildirimi (paket gerekmez)."""
    try:
        import subprocess
        ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{title}</text>
            <text>{message}</text>
        </binding>
    </visual>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("NetShield").Show($toast)
'''
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script],
            creationflags=0x08000000,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass