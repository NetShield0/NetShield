# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ZAPRET_DIR   = os.path.join(BASE_DIR, "core", "zapret")
WINWS2_EXE   = os.path.join(ZAPRET_DIR, "winws2.exe")
WINWS_EXE    = os.path.join(ZAPRET_DIR, "winws.exe")
LUA_DIR      = os.path.join(ZAPRET_DIR, "lua")
CONFIG_DIR   = os.path.join(ZAPRET_DIR, "config")

GOODBYEDPI_DIR = os.path.join(BASE_DIR, "core", "goodbyedpi")
GOODBYEDPI_EXE = os.path.join(GOODBYEDPI_DIR, "goodbyedpi.exe")

LUA_INITS = [
    f"--lua-init=@{os.path.join(LUA_DIR, 'zapret-lib.lua')}",
    f"--lua-init=@{os.path.join(LUA_DIR, 'zapret-antidpi.lua')}",
    f"--lua-init=@{os.path.join(LUA_DIR, 'zapret-auto.lua')}",
]

ENGINES_CONFIG = {
    # ⚡ GoodbyeDPI
    "GoodbyeDPI": {
        "exe_path": GOODBYEDPI_EXE,
        "modes": {
            "Standart": [
                "-1",
                "--dns-addr", "1.1.1.1",
                "--dns-port", "53",
                "-e", "1",
                "--frag-by-sni",
            ],
            "Agresif": [
                "-5",
                "-e", "1",
                "-f", "1",
                "--frag-by-sni",
            ],
            "Hafif": [
                "-p",
                "-r",
                "-s",
                "-e", "2",
            ],
        },
    },

    # ⚙️ Zapret Classic
    "Zapret Classic": {
        "exe_path": WINWS_EXE,
        "modes": {
            "Blockcheck": [
                "--wf-l3=ipv4",
                "--wf-tcp=443",
                "--dpi-desync=fake",
                "--dpi-desync-ttl=5",
                "--dpi-desync-fake-tls-mod=rnd,dupsid,rndsni,padencap",
                f"--hostlist-exclude={os.path.join(CONFIG_DIR, 'excludelist.txt')}",
            ],
            "Klasik Fake": [
                "--wf-l3=ipv4",
                "--wf-tcp=443",
                "--dpi-desync=fake",
                "--dpi-desync-ttl=1",
                f"--hostlist-exclude={os.path.join(CONFIG_DIR, 'excludelist.txt')}",
            ],
            "Split": [
                "--wf-l3=ipv4",
                "--wf-tcp=443",
                "--dpi-desync=multisplit",
                "--dpi-desync-split-pos=midsld",
                f"--hostlist-exclude={os.path.join(CONFIG_DIR, 'excludelist.txt')}",
            ],
        },
    },

    # 🔮 Zapret Lua
    "Zapret Lua": {
        "exe_path": WINWS2_EXE,
        "modes": {
            "Standart": [
                "--wf-l3=ipv4",
                "--wf-tcp-out=0-65535",
                "--wf-udp-out=0-65535",
                f"--hostlist-exclude={os.path.join(CONFIG_DIR, 'excludelist.txt')}",
                "--payload=tls_client_hello",
                "--lua-desync=tcpseg:pos=0,1:ip_id=rnd:repeats=1",
                *LUA_INITS,
                f"--hostlist-auto={os.path.join(CONFIG_DIR, 'autohostlist.txt')}",
            ],
        },
    },
}