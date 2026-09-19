# blockcheck.py
import os
import socket
import ssl
import subprocess
import time

from config import CONFIG_DIR, LUA_DIR, ZAPRET_DIR
from logger import get_logger

log = get_logger()
CREATE_NO_WINDOW = 0x08000000

WINWS_EXE  = os.path.join(ZAPRET_DIR, "winws.exe")
WINWS2_EXE = os.path.join(ZAPRET_DIR, "winws2.exe")

# ------------- HEDEF TEST -------------
def _test_tls(host: str, timeout: float = 3.0) -> bool:
    """Host'a TLS bağlantısı kurulabiliyorsa True."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return True
    except Exception:
        return False


# ------------- MOTOR YÖNETİMİ -------------
def _start_engine(exe: str, args: list):
    if not os.path.exists(exe):
        log.error(f"Motor yok: {exe}")
        return None
    try:
        return subprocess.Popen(
            [exe] + args,
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            cwd=os.path.dirname(exe),
        )
    except Exception as e:
        log.error(f"Motor başlatılamadı: {e}")
        return None


def _stop_engine(proc):
    if not proc:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
    except Exception:
        pass


# ------------- STRATEJİ LİSTESİ -------------
def get_all_strategies():
    """Denenecek tüm stratejileri döner."""
    strategies = []

    lua_common = [
        "--wf-l3=ipv4", "--wf-tcp-out=0-65535", "--wf-udp-out=0-65535",
        f"--hostlist-exclude={os.path.join(CONFIG_DIR, 'excludelist.txt')}",
        "--payload=tls_client_hello",
    ]
    lua_inits = [
        f"--lua-init=@{os.path.join(LUA_DIR, 'zapret-lib.lua')}",
        f"--lua-init=@{os.path.join(LUA_DIR, 'zapret-antidpi.lua')}",
        f"--lua-init=@{os.path.join(LUA_DIR, 'zapret-auto.lua')}",
    ]

    lua_desyncs = [
        ("Lua: tcpseg rnd1", "tcpseg:pos=0,1:ip_id=rnd:repeats=1"),
        ("Lua: tcpseg rnd2", "tcpseg:pos=0,1:ip_id=rnd:repeats=2"),
        ("Lua: tcpseg zero", "tcpseg:pos=0,1:ip_id=zero:repeats=1"),
        ("Lua: split 1",     "split:pos=1"),
        ("Lua: split 2",     "split:pos=2"),
        ("Lua: split midsld","split:pos=midsld"),
        ("Lua: fake rnd1",   "fake:repeats=1"),
        ("Lua: fake rnd2",   "fake:repeats=2"),
    ]
    for name, desync in lua_desyncs:
        strategies.append({
            "name": name,
            "exe": WINWS2_EXE,
            "args": lua_common + [f"--lua-desync={desync}"] + lua_inits,
        })

    classic_common = ["--wf-l3=ipv4", "--wf-tcp=443"]
    classic_excl = [f"--hostlist-exclude={os.path.join(CONFIG_DIR, 'excludelist.txt')}"]

    classic_desyncs = [
        ("Klasik: fake TTL1", ["--dpi-desync=fake", "--dpi-desync-ttl=1"]),
        ("Klasik: fake TTL2", ["--dpi-desync=fake", "--dpi-desync-ttl=2"]),
        ("Klasik: fake TTL3", ["--dpi-desync=fake", "--dpi-desync-ttl=3"]),
        ("Klasik: fake TTL4", ["--dpi-desync=fake", "--dpi-desync-ttl=4"]),
        ("Klasik: fake TTL5", ["--dpi-desync=fake", "--dpi-desync-ttl=5"]),
        ("Klasik: fake TTL5 + TLS mod", [
            "--dpi-desync=fake", "--dpi-desync-ttl=5",
            "--dpi-desync-fake-tls-mod=rnd,dupsid,rndsni,padencap",
        ]),
        ("Klasik: multisplit 1", ["--dpi-desync=multisplit", "--dpi-desync-split-pos=1"]),
        ("Klasik: multisplit 2", ["--dpi-desync=multisplit", "--dpi-desync-split-pos=2"]),
        ("Klasik: multisplit midsld", ["--dpi-desync=multisplit", "--dpi-desync-split-pos=midsld"]),
        ("Klasik: multisplit sniext+1", ["--dpi-desync=multisplit", "--dpi-desync-split-pos=sniext+1"]),
        ("Klasik: multidisorder 1", ["--dpi-desync=multidisorder", "--dpi-desync-split-pos=1"]),
        ("Klasik: multidisorder 2", ["--dpi-desync=multidisorder", "--dpi-desync-split-pos=2"]),
        ("Klasik: multidisorder midsld", ["--dpi-desync=multidisorder", "--dpi-desync-split-pos=midsld"]),
        ("Klasik: disorder 1", ["--dpi-desync=disorder", "--dpi-desync-split-pos=1"]),
        ("Klasik: disorder 2", ["--dpi-desync=disorder", "--dpi-desync-split-pos=2"]),
    ]
    for name, args in classic_desyncs:
        strategies.append({
            "name": name,
            "exe": WINWS_EXE,
            "args": classic_common + args + classic_excl,
        })

    return strategies


# ------------- ANA TEST -------------
def run_blockcheck(targets, strategy_limit, progress_cb, result_cb, cancel_event):
    """
    targets: list[str]
    strategy_limit: int (kaç strateji denenecek)
    progress_cb: function(current, total, message)
    result_cb: function(result_dict)  # her strateji sonucu
    cancel_event: threading.Event
    """
    all_strategies = get_all_strategies()

    if strategy_limit >= len(all_strategies):
        strategies = all_strategies
    else:
        # Lua stratejilerinden başla, sonra klasik
        strategies = all_strategies[:strategy_limit]

    total = len(strategies)
    results = []

    for idx, strat in enumerate(strategies):
        if cancel_event.is_set():
            break

        name = strat["name"]
        progress_cb(idx, total, f"[{idx+1}/{total}] {name} başlatılıyor...")

        proc = _start_engine(strat["exe"], strat["args"])
        if not proc:
            result = {
                "name": name, "exe": strat["exe"], "args": strat["args"],
                "success": 0, "total": len(targets), "details": [],
                "error": "Motor başlatılamadı",
            }
            results.append(result)
            result_cb(result)
            continue

        time.sleep(1.0)  # Motor stabil olsun

        if proc.poll() is not None:
            _stop_engine(proc)
            result = {
                "name": name, "exe": strat["exe"], "args": strat["args"],
                "success": 0, "total": len(targets), "details": [],
                "error": "Motor çöktü",
            }
            results.append(result)
            result_cb(result)
            continue

        details = []
        success = 0
        for target in targets:
            if cancel_event.is_set():
                break
            ok = _test_tls(target, timeout=3.0)
            details.append((target, ok))
            if ok:
                success += 1
            progress_cb(
                idx, total,
                f"[{idx+1}/{total}] {name} → {target}: {'✓' if ok else '✗'}",
            )

        _stop_engine(proc)
        time.sleep(0.4)  # Sürücü temizliği için

        result = {
            "name": name,
            "exe": strat["exe"],
            "args": strat["args"],
            "success": success,
            "total": len(targets),
            "details": details,
            "error": "",
        }
        results.append(result)
        result_cb(result)

    progress_cb(total, total, "Test tamamlandı.")
    return results


def pick_best(results):
    """En çok hedefe ulaşan stratejiyi döner."""
    if not results:
        return None
    best = max(results, key=lambda r: (r["success"], -len(r.get("error", ""))))
    return best if best["success"] > 0 else None