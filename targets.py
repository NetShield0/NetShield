# targets.py

# 📦 Uygulama paketleri
PACKAGES = {
    "Discord": ["discord.com", "discord.gg", "discordapp.com"],
    "Roblox": ["roblox.com", "www.roblox.com", "auth.roblox.com"],
    "Sosyal Medya": ["instagram.com", "twitter.com", "facebook.com"],
    "Video": ["youtube.com", "twitch.tv"],
    "Hepsi": [
        "discord.com", "discord.gg", "roblox.com", "rbxcdn.com",
        "instagram.com", "twitter.com", "facebook.com",
        "youtube.com", "twitch.tv",
    ],
}

# 🌍 Ülkeler ve o ülkede yaygın engellenen siteler
COUNTRIES = {
    "Yok": [],
    "Türkiye": ["discord.com", "roblox.com", "wikipedia.org"],
    "Çin": ["google.com", "youtube.com", "facebook.com", "twitter.com", "instagram.com"],
    "Rusya": ["facebook.com", "twitter.com", "linkedin.com"],
    "İran": ["facebook.com", "twitter.com", "youtube.com", "telegram.org"],
    "Kuzey Kore": ["google.com", "youtube.com", "facebook.com"],
}


def extract_host(url_or_host: str) -> str:
    """'https://example.com/path' → 'example.com' """
    if not url_or_host:
        return ""
    s = url_or_host.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s


def get_targets(package: str, country: str, custom_url: str) -> list:
    """UI'daki seçimlerden hedef listesi oluşturur."""
    targets = []
    if package in PACKAGES:
        targets.extend(PACKAGES[package])
    if country in COUNTRIES:
        targets.extend(COUNTRIES[country])
    host = extract_host(custom_url)
    if host:
        targets.append(host)
    # Tekrarları kaldır, sırayı koru
    seen = set()
    unique = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique