# 🛡️ NetShield

**Sıfır telemetri ile çalışan, DPI bypass + VPN + DNS gizliliği sunan Windows ağ aracı.**

[İndir](https://github.com/NetShield0/NetShield/releases)

---

## 🎯 NetShield Nedir?

NetShield, **Türkiye'deki internet engellerini** aşmak ve **çevrimiçi gizliliğinizi** korumak için tasarlanmış, tek tıkla çalışan bir Windows uygulamasıdır.

**Kime uygun?**
- 🎮 Discord, Roblox gibi engellenen platformlara erişmek isteyenler
- 🔒 İSS'nin hangi sitelere girdiğini görmesini istemeyenler
- 🚫 Reklam ve izleyicilerden kurtulmak isteyenler
- 🌐 Tek tıkla VPN açmak isteyenler

---

## ✨ Özellikler

### 🚀 DPI Bypass
- **3 motor:** GoodbyeDPI, Zapret Classic, Zapret Lua
- **23+ strateji** otomatik test
- Ağınıza en uygun stratejiyi **otomatik bulur ve kaydeder**
- Discord, Roblox, YouTube ve daha fazlası

### 🌐 VPN
- **Cloudflare WARP** ile tek tuşla VPN
- Kendi WireGuard `.conf` dosyanı içe aktar
- **Şifreli saklama** (Windows DPAPI)
- Split Tunnel (Full / DNS-only / Web-only)

### 🚫 DNS Gizliliği + Ad Block
- **Cloudflare DoH** → şifreli DNS
- **AdGuard DoH** → reklam + şifreli DNS
- Sistem geneli reklam engelleme
- İSS'nin hangi sitelere girdiğini göremez

### 🔒 Güvenlik
- **Kill Switch** → VPN çökerse internet otomatik keser
- **Sıfır telemetri** → hiçbir veri sunucuya gitmez
- **Şifreli VPN config** → başkası okuyamaz

### 📊 Kontrol & İzleme
- Canlı istatistikler (süre, bağlantı, hız, bellek)
- Hız testi (ping, indirme, yükleme)
- Dış IP ve DNS testi
- Detaylı log görüntüleyici

### 🎨 Kullanıcı Deneyimi
- **Modern arayüz** (macOS tarzı)
- **Sistem tepsisi** → arka planda çalışır
- **Global kısayollar** (Ctrl+Shift+B/P)
- **Taskbar/Alt+Tab'dan gizlenir** → hayalet gibi çalışır
- **Özelleştirilebilir bar** (konum, tarz, boyut, opaklık)
- **Otomatik başlatma** (Windows açılışında)

---

## 📥 Kurulum

### 🟢 Hazır Sürüm (Önerilen)

**Şu an sadece Python sürümü mevcut** — EXE sürümü yakında!

1. **[Son sürümü indir](https://github.com/NetShield0/NetShield/releases/latest)** → `NetShield-PYT-vX.X.X.zip`
2. Zip'i bir klasöre **çıkar**
3. **`Kurulum.bat`** dosyasına çift tıkla (gerekli Python paketlerini kurar)
4. **`Baslat.bat`** dosyasına çift tıkla (uygulama açılır)

**Gereksinim:** [Python 3.10+](https://www.python.org/downloads/) (kurulumda **"Add Python to PATH"** seçeneğini işaretleyin)
