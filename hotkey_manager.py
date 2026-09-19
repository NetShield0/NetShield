# hotkey_manager.py
import threading
from logger import get_logger

try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False

log = get_logger()


class HotkeyManager:
    def __init__(self):
        self._hotkeys = []
        self._enabled = False

    def register(self, combo, callback, description=""):
        """Kısayol kaydeder. combo örnek: 'ctrl+shift+b'"""
        if not KEYBOARD_OK:
            return False, "keyboard paketi kurulu değil."

        try:
            h = keyboard.add_hotkey(combo, callback, suppress=False)
            self._hotkeys.append((combo, h))
            log.info(f"Kısayol kaydedildi: {combo} ({description})")
            return True, f"Kısayol: {combo}"
        except Exception as e:
            log.error(f"Kısayol hatası: {e}")
            return False, str(e)

    def unregister_all(self):
        if not KEYBOARD_OK:
            return
        for combo, h in self._hotkeys:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        self._hotkeys = []
        log.info("Tüm kısayollar kaldırıldı.")

    def stop(self):
        self.unregister_all()


def is_available():
    return KEYBOARD_OK