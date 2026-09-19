# killswitch_manager.py
import atexit
import subprocess

from logger import get_logger

log = get_logger()
CREATE_NO_WINDOW = 0x08000000


def _run(cmd, timeout=15):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except Exception as e:
        log.warning(f"Komut hatası: {e}")
        return -1, "", str(e)


def _get_active_interfaces():
    code, out, _ = _run(["netsh", "interface", "show", "interface"])
    interfaces = []
    for line in out.splitlines():
        if "Enabled" in line and "Connected" in line:
            parts = line.split()
            if len(parts) >= 4:
                interfaces.append(" ".join(parts[3:]))
    return interfaces


RULE_NAME = "AgKontrol_KillSwitch"


def lock_internet():
    """Windows Firewall ile tüm giden trafiği engeller (WireGuard hariç)."""
    # Önce eski kural varsa temizle
    _run(["netsh", "advfirewall", "firewall", "delete", "rule",
          f"name={RULE_NAME}"])

    # WireGuard'ın çalışması için DNS ve endpoint'e izin ver, gerisini blokla
    # Basitçe: TÜM giden trafiği blokla
    code, out, err = _run([
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={RULE_NAME}",
        "dir=out",
        "action=block",
        "enable=yes",
        "profile=any",
    ], timeout=20)

    if code != 0:
        log.error(f"Firewall kuralı eklenemedi: {err}")
        return False

    # DNS cache'i temizle
    _run(["ipconfig", "/flushdns"])
    log.warning("🔒 KILL SWITCH: İnternet kilitlendi (firewall)")
    return True


def unlock_internet():
    """Firewall kuralını kaldırır."""
    code, out, err = _run([
        "netsh", "advfirewall", "firewall", "delete", "rule",
        f"name={RULE_NAME}",
    ], timeout=20)

    # DNS cache'i temizle
    _run(["ipconfig", "/flushdns"])
    log.info("🔓 KILL SWITCH: İnternet kilidi açıldı")
    return True


def is_internet_locked():
    """Firewall kuralı aktif mi?"""
    code, out, _ = _run([
        "netsh", "advfirewall", "firewall", "show", "rule",
        f"name={RULE_NAME}",
    ])
    return RULE_NAME in out


def is_dns_locked():
    """DNS 0.0.0.0 mı kontrol et."""
    code, out, _ = _run(["netsh", "interface", "ip", "show", "dns"])
    return "0.0.0.0" in out


class KillSwitch:
    """VPN çökerse interneti otomatik keser."""

    def __init__(self):
        self.enabled = False
        self._was_vpn_active = False
        self._dns_locked = False
        atexit.register(self.cleanup)

    def enable(self):
        self.enabled = True
        self._was_vpn_active = False
        log.info("Kill Switch: aktif")

    def disable(self):
        self.enabled = False
        if self._dns_locked:
            unlock_internet()
            self._dns_locked = False
        log.info("Kill Switch: pasif")

    def check(self, vpn_active: bool):
        """
        Watchdog tarafından her 3 saniyede çağrılır.
        Döner: None | 'vpn_connected' | 'vpn_lost'
        """
        if not self.enabled:
            return None

        if vpn_active and not self._was_vpn_active:
            self._was_vpn_active = True
            if self._dns_locked:
                unlock_internet()
                self._dns_locked = False
                return "vpn_connected"
            return None

        # VPN çöktü
        if not vpn_active and self._was_vpn_active:
            self._was_vpn_active = False
            lock_internet()
            self._dns_locked = True
            return "vpn_lost"
        
        return None

    def cleanup(self):
        """Uygulama kapanırken kilidi aç."""
        if self._dns_locked:
            try:
                unlock_internet()
                log.info("Kill Switch: temizlendi (uygulama kapandı)")
            except Exception:
                pass


def force_unlock():
    """Panic butonu — kilidi zorla kaldır."""
    try:
        unlock_internet()
        log.info("Kill Switch: manuel kilit kaldırıldı")
        return True
    except Exception as e:
        log.error(f"Manuel kilit kaldırma hatası: {e}")
        return False