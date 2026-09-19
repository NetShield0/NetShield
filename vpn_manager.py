# vpn_manager.py
import base64
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from logger import get_logger
from crypto_manager import dpapi_encrypt, dpapi_decrypt

try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False


log = get_logger()
CREATE_NO_WINDOW = 0x08000000

BASE_DIR = Path(__file__).parent.resolve()
VPN_CONFIG_DIR = BASE_DIR / "core" / "vpn_configs"
VPN_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

WIREGUARD_EXE = Path("C:/Program Files/WireGuard/wireguard.exe")


# ============ YARDIMCI ============
def _run(cmd, timeout=60):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "Zaman aşımı"
    except Exception as e:
        return -1, "", str(e)


def is_crypto_available():
    return CRYPTO_OK


# ============ KURULUM ============
def is_wireguard_installed() -> bool:
    return WIREGUARD_EXE.exists()


def install_wireguard(progress_cb=None):
    if is_wireguard_installed():
        return True, "WireGuard zaten kurulu."

    if progress_cb:
        progress_cb("WireGuard indiriliyor (1-3 dk)...")
    log.info("WireGuard kuruluyor...")

    code, out, err = _run([
        "winget", "install", "--id", "WireGuard.WireGuard",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ], timeout=300)

    if is_wireguard_installed():
        return True, "WireGuard başarıyla kuruldu."

    if code == 0:
        return True, "Kurulum tamamlandı."

    return False, f"Kurulum başarısız: {err[:200]}"


# ============ CONFIG YÖNETİMİ (ŞİFRELİ) ============
def _enc_path(name: str) -> Path:
    return VPN_CONFIG_DIR / f"{name}.enc"


def _extract_label(text: str, fallback: str) -> str:
    """Config metninden 'Label' yorumunu okur."""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# Label"):
            if "=" in s:
                return s.split("=", 1)[1].strip()
    return fallback


def list_configs():
    """Şifreli .enc dosyalarını listeler."""
    configs = []
    if not VPN_CONFIG_DIR.exists():
        return configs

    for f in sorted(VPN_CONFIG_DIR.glob("*.enc")):
        label = f.stem
        try:
            enc = f.read_bytes()
            dec = dpapi_decrypt(enc)
            text = dec.decode("utf-8", errors="ignore")
            label = _extract_label(text, f.stem)
        except Exception as e:
            log.warning(f"Config okunamadı: {f.name} ({e})")
            label = f.stem + " (şifreli, okunamadı)"

        configs.append({
            "name": f.stem,
            "label": label,
            "path": str(f),
            "size": f.stat().st_size,
            "encrypted": True,
        })
    return configs


def _sanitize_name(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return "".join(c for c in name if c.isalnum() or c in "-_")


def save_config_text(text, name):
    """Config'i DPAPI ile şifreleyip .enc olarak kaydeder."""
    if "[Interface]" not in text or "[Peer]" not in text:
        return False, "Geçersiz WireGuard config."

    name = _sanitize_name(name)
    if not name:
        return False, "Geçersiz isim."

    try:
        data = text.encode("utf-8")
        enc = dpapi_encrypt(data)
        _enc_path(name).write_bytes(enc)
        log.info(f"Şifreli config kaydedildi: {name}")
        return True, f"Kaydedildi: {name}"
    except Exception as e:
        log.error(f"Şifreleme hatası: {e}")
        return False, f"Kaydetme hatası: {e}"


def load_config_text(name):
    """Şifreli config'i çözer ve metin olarak döner."""
    path = _enc_path(name)
    if not path.exists():
        return None
    try:
        enc = path.read_bytes()
        dec = dpapi_decrypt(enc)
        return dec.decode("utf-8", errors="ignore")
    except Exception as e:
        log.error(f"Config çözme hatası ({name}): {e}")
        return None


def import_config(source_path, name=None):
    src = Path(source_path)
    if not src.exists():
        return False, "Kaynak dosya bulunamadı."
    if not name:
        name = src.stem
    try:
        text = src.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return False, f"Okuma hatası: {e}"
    return save_config_text(text, name)


def delete_config(name):
    path = _enc_path(name)
    if not path.exists():
        return False, "Config bulunamadı."
    try:
        disconnect(name)
        path.unlink()
        return True, f"Silindi: {name}"
    except Exception as e:
        return False, f"Silme hatası: {e}"


# ============ OTOMATİK WARP ============
WARP_API = "https://api.cloudflareclient.com/v0a2158/reg"
WARP_CLIENT_VERSION = "a-6.10-2158"


def _gen_wg_keypair():
    priv = X25519PrivateKey.generate()
    pub = priv.public_key()
    priv_b64 = base64.b64encode(priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )).decode()
    pub_b64 = base64.b64encode(pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode()
    return priv_b64, pub_b64


def create_warp_config(progress_cb=None):
    if not CRYPTO_OK:
        return False, "cryptography paketi eksik."

    if progress_cb:
        progress_cb("WARP anahtarları üretiliyor...")

    priv_b64, pub_b64 = _gen_wg_keypair()

    body = json.dumps({
        "key": pub_b64,
        "install_id": "",
        "fcm_token": "",
        "to": "",
        "model": "PC",
        "locale": "en_US",
    }).encode("utf-8")

    req = urllib.request.Request(
        WARP_API, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "CF-Client-Version": WARP_CLIENT_VERSION,
            "User-Agent": "okhttp/3.12.1",
        },
    )

    if progress_cb:
        progress_cb("Cloudflare'e kayıt olunuyor...")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, f"WARP kayıt hatası: {e}"

    try:
        peer = data["config"]["peers"][0]
        peer_pub = peer["public_key"]
        endpoint = peer["endpoint"]["host"]
        v4 = data["config"]["interface"]["addresses"]["v4"]
        v6 = data["config"]["interface"]["addresses"]["v6"]
    except (KeyError, IndexError) as e:
        return False, f"WARP yanıt formatı beklenmedik: {e}"

    if progress_cb:
        progress_cb("Şifreli config oluşturuluyor...")

    config_text = (
        f"# Label = Cloudflare WARP (Otomatik)\n"
        f"[Interface]\n"
        f"PrivateKey = {priv_b64}\n"
        f"Address = {v4}/32, {v6}/128\n"
        f"DNS = 1.1.1.1\n"
        f"MTU = 1280\n"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {peer_pub}\n"
        f"AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {endpoint}\n"
        f"PersistentKeepalive = 25\n"
    )

    ok, msg = save_config_text(config_text, "Cloudflare_WARP")
    if not ok:
        return False, msg

    return True, "Cloudflare WARP hazır! (şifreli kaydedildi)"


# ============ BAĞLANTI ============
def get_active_tunnel():
    if not is_wireguard_installed():
        return None
    try:
        code, out, _ = _run([
            "powershell", "-Command",
            "Get-Service -Name 'WireGuardTunnel*' -ErrorAction SilentlyContinue | "
            "Where-Object {$_.Status -eq 'Running'} | "
            "Select-Object -ExpandProperty Name",
        ], timeout=10)
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("WireGuardTunnel$"):
                return line.replace("WireGuardTunnel$", "")
    except Exception as e:
        log.warning(f"Tunnel kontrol hatası: {e}")
    return None


def connect(config_name):
    """Şifreli config'i çözer, geçici dosyaya yazar, WireGuard'a verir."""
    if not is_wireguard_installed():
        return False, "WireGuard kurulu değil."

    config_text = load_config_text(config_name)
    if not config_text:
        return False, "Config okunamadı veya şifre çözülemedi."

    log.info(f"VPN bağlanıyor: {config_name}")

    # Geçici dosya oluştur
    tmp_dir = Path(tempfile.gettempdir()) / "agkontrol"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_conf = tmp_dir / f"{config_name}.conf"

    try:
        tmp_conf.write_text(config_text, encoding="utf-8")

        # Eski tunnel varsa temizle
        _run([str(WIREGUARD_EXE), "/uninstalltunnelservice", config_name], timeout=15)

        # Yeni tunnel kur
        code, out, err = _run([
            str(WIREGUARD_EXE), "/installtunnelservice", str(tmp_conf),
        ], timeout=20)

        import time
        time.sleep(1.5)
        active = get_active_tunnel()

        if active == config_name:
            return True, f"Bağlandı: {config_name}"

        if code != 0:
            err_clean = (err or out or "").strip()[:200]
            return False, f"Bağlantı başarısız: {err_clean}"

        return False, "Tünel kurulamadı."
    finally:
        # Geçici dosyayı temizle
        try:
            if tmp_conf.exists():
                tmp_conf.unlink()
        except Exception:
            pass
        # Boş klasörü de temizle
        try:
            if tmp_dir.exists() and not any(tmp_dir.iterdir()):
                tmp_dir.rmdir()
        except Exception:
            pass


def disconnect(config_name):
    if not is_wireguard_installed():
        return True, "WireGuard yok."
    log.info(f"VPN ayrılıyor: {config_name}")
    code, out, err = _run([
        str(WIREGUARD_EXE), "/uninstalltunnelservice", config_name,
    ], timeout=20)
    if code == 0:
        return True, f"Ayrıldı: {config_name}"
    return True, "Ayrıldı."


def disconnect_all():
    active = get_active_tunnel()
    if active:
        disconnect(active)


# ============ SPLIT TUNNELING ============
SPLIT_PRESETS = {
    "full": "0.0.0.0/0, ::/0",
    "split_dns": "1.1.1.1/32, 1.0.0.1/32, 8.8.8.8/32, 8.8.4.4/32",
    "split_web": "1.1.1.1/32, 8.8.8.8/32",
}


def set_allowed_ips(config_name, mode="full"):
    """Şifreli config'i çözer, AllowedIPs'i günceller, tekrar şifreler."""
    config_text = load_config_text(config_name)
    if not config_text:
        return False, "Config okunamadı."

    new_allowed = SPLIT_PRESETS.get(mode, SPLIT_PRESETS["full"])

    lines = config_text.splitlines()
    new_lines = []
    in_peer = False
    replaced = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[Peer]"):
            in_peer = True
            new_lines.append(line)
            continue
        if in_peer and stripped.startswith("AllowedIPs"):
            new_lines.append(f"AllowedIPs = {new_allowed}")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        final = []
        in_peer = False
        for line in new_lines:
            final.append(line)
            if line.strip().startswith("[Peer]"):
                in_peer = True
            elif in_peer and line.strip().startswith("Endpoint"):
                final.append(f"AllowedIPs = {new_allowed}")
                in_peer = False
                replaced = True
        new_lines = final

    new_text = "\n".join(new_lines)
    ok, msg = save_config_text(new_text, config_name)
    if not ok:
        return False, msg
    return True, f"Mod: {mode}"


def get_allowed_ips(config_name):
    config_text = load_config_text(config_name)
    if not config_text:
        return None
    for line in config_text.splitlines():
        if line.strip().startswith("AllowedIPs"):
            return line.split("=", 1)[1].strip()
    return None