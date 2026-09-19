# dns_manager.py
import re
import subprocess
import urllib.request

from logger import get_logger

log = get_logger()

CREATE_NO_WINDOW = 0x08000000

DOH_PRIMARY   = "1.1.1.1"
DOH_SECONDARY = "1.0.0.1"
DOH_TEMPLATE  = "https://cloudflare-dns.com/dns-query"


def _run(cmd, timeout=30):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="ignore",
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "Zaman aşımı"
    except Exception as e:
        log.error(f"Komut hatası: {e}")
        return -1, "", str(e)


def get_active_interfaces():
    code, out, _ = _run(["netsh", "interface", "show", "interface"])
    interfaces = []
    for line in out.splitlines():
        m = re.match(
            r"\s*(Enabled|Disabled)\s+(Connected|Disconnected)\s+\S+\s+(.+)",
            line,
        )
        if m and m.group(1) == "Enabled" and m.group(2) == "Connected":
            interfaces.append(m.group(3).strip())
    return interfaces


def get_current_dns():
    result = {}
    for iface in get_active_interfaces():
        code, out, _ = _run(
            ["netsh", "interface", "ip", "show", "dns", f"name={iface}"]
        )
        servers = re.findall(r"(\d+\.\d+\.\d+\.\d+)", out)
        result[iface] = servers
    return result


def set_doh_dns():
    """Cloudflare DoH DNS'ini atar + Windows'a kaydeder."""
    interfaces = get_active_interfaces()
    if not interfaces:
        return False, "Aktif ağ arayüzü bulunamadı."

    # DoH sunucularını Windows'a kaydet
    for addr in (DOH_PRIMARY, DOH_SECONDARY):
        _run([
            "powershell", "-NoProfile", "-Command",
            f"Add-DnsClientDohServerAddress -ServerAddress '{addr}' "
            f"-DohTemplate '{DOH_TEMPLATE}' "
            f"-AllowFallbackToUdp $false -AutoUpgrade $true "
            f"-ErrorAction SilentlyContinue"
        ], timeout=10)

    for iface in interfaces:
        _run([
            "netsh", "interface", "ip", "set", "dns",
            f"name={iface}", "static", DOH_PRIMARY, "primary",
        ])
        _run([
            "netsh", "interface", "ip", "add", "dns",
            f"name={iface}", DOH_SECONDARY, "index=2",
        ])
        log.info(f"DoH DNS atandı: {iface}")

    _run(["ipconfig", "/flushdns"], timeout=10)
    return True, f"{len(interfaces)} arayüze DoH DNS atandı."


def reset_dns_to_dhcp():
    interfaces = get_active_interfaces()
    if not interfaces:
        return False, "Aktif ağ arayüzü bulunamadı."

    for iface in interfaces:
        _run([
            "netsh", "interface", "ip", "set", "dns",
            f"name={iface}", "source=dhcp",
        ])
        log.info(f"DNS DHCP'ye döndürüldü: {iface}")

    return True, f"{len(interfaces)} arayüz DHCP'ye döndürüldü."


def test_dns_leak():
    try:
        req = urllib.request.Request(
            "https://1.1.1.1/cdn-cgi/trace",
            headers={"User-Agent": "DPI-Bypass-Tool/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read().decode("utf-8", errors="ignore")

        info = {}
        for line in data.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v

        return {
            "success": True,
            "ip": info.get("ip", "?"),
            "colo": info.get("colo", "?"),
            "loc": info.get("loc", "?"),
        }
    except Exception as e:
        log.error(f"DNS testi başarısız: {e}")
        return {"success": False, "error": str(e)}


def ping_host(host, count=3):
    code, out, _ = _run(["ping", "-n", str(count), host])
    m = re.search(r"(?:Ortalama|Average)\s*=\s*(\d+)ms", out)
    if m:
        return True, int(m.group(1))
    m = re.search(r"=\s*(\d+)ms", out)
    if m:
        return True, int(m.group(1))
    return False, None

# ============ AD BLOCK (AdGuard DNS) ============
ADGUARD_PRIMARY   = "94.140.14.14"
ADGUARD_SECONDARY = "94.140.15.15"
ADGUARD_TEMPLATE  = "https://dns.adguard-dns.com/dns-query"


def set_adblock_dns():
    """AdGuard DNS atar + DoH'u Windows'a kaydeder."""
    interfaces = get_active_interfaces()
    if not interfaces:
        return False, "Aktif ağ arayüzü bulunamadı."

    # 1) DoH sunucularını Windows'a kaydet (admin gerektirir, biz admin'iz)
    for addr in (ADGUARD_PRIMARY, ADGUARD_SECONDARY):
        _run([
            "powershell", "-NoProfile", "-Command",
            f"Add-DnsClientDohServerAddress -ServerAddress '{addr}' "
            f"-DohTemplate '{ADGUARD_TEMPLATE}' "
            f"-AllowFallbackToUdp $false -AutoUpgrade $true "
            f"-ErrorAction SilentlyContinue"
        ], timeout=10)

    # 2) Arayüzlere DNS ata
    for iface in interfaces:
        _run([
            "netsh", "interface", "ip", "set", "dns",
            f"name={iface}", "static", ADGUARD_PRIMARY, "primary",
        ])
        _run([
            "netsh", "interface", "ip", "add", "dns",
            f"name={iface}", ADGUARD_SECONDARY, "index=2",
        ])
        log.info(f"AdGuard DNS atandı: {iface}")

    # 3) DNS cache'i temizle
    _run(["ipconfig", "/flushdns"], timeout=10)

    return True, "Reklam engelleme aktif (AdGuard DoH)."


def is_adblock_active():
    """AdGuard DNS aktif mi kontrol eder."""
    try:
        dns = get_current_dns()
        for iface, servers in dns.items():
            if ADGUARD_PRIMARY in servers:
                return True
    except Exception:
        pass
    return False


def test_adblock():
    """AdGuard DNS üzerinden bir reklam domainini sorgular."""
    import socket
    test_domains = ["doubleclick.net", "googleadservices.com", "adservice.google.com"]

    blocked = 0
    for d in test_domains:
        try:
            result = socket.gethostbyname(d)
            if result in ("0.0.0.0", "::", "127.0.0.1"):
                blocked += 1
        except socket.gaierror:
            # DNS çözülemedi = domain bloklandı = Başarı!
            blocked += 1
        except Exception:
            pass

    if blocked == len(test_domains):
        return True, f"Reklam engelleme çalışıyor ✓ ({blocked}/{len(test_domains)} test edildi)"
    elif blocked > 0:
        return True, f"Kısmen çalışıyor ({blocked}/{len(test_domains)})"
    else:
        return False, "Reklam engelleme kapalı"