# stats_manager.py
import time
import psutil

from logger import get_logger

log = get_logger()

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False


class StatsManager:
    def __init__(self):
        self.start_time = None
        self.process_name = None
        self._last_net = None
        self._last_time = None

    def start(self, process_name):
        self.start_time = time.time()
        self.process_name = process_name
        self._last_net = None
        self._last_time = None

    def stop(self):
        self.start_time = None
        self.process_name = None

    def get_uptime_str(self):
        if not self.start_time:
            return "--:--:--"
        elapsed = int(time.time() - self.start_time)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def get_active_connections(self):
        if not PSUTIL_OK:
            return 0
        count = 0
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "ESTABLISHED":
                    count += 1
        except Exception:
            pass
        return count

    def get_memory_mb(self):
        if not PSUTIL_OK:
            return 0.0
        try:
            for p in psutil.process_iter(["name", "memory_info"]):
                try:
                    if p.info["name"] in ("winws.exe", "winws2.exe"):
                        return p.info["memory_info"].rss / (1024 * 1024)
                except Exception:
                    continue
        except Exception:
            pass
        return 0.0

    def get_net_speed(self):
        """Saniye başına (down, up) MB döner."""
        if not PSUTIL_OK:
            return 0.0, 0.0
        try:
            net = psutil.net_io_counters()
            now = time.time()
            if self._last_net is None:
                self._last_net = net
                self._last_time = now
                return 0.0, 0.0
            dt = now - self._last_time
            if dt <= 0:
                return 0.0, 0.0
            down = (net.bytes_recv - self._last_net.bytes_recv) / dt / (1024 * 1024)
            up = (net.bytes_sent - self._last_net.bytes_sent) / dt / (1024 * 1024)
            self._last_net = net
            self._last_time = now
            return round(down, 2), round(up, 2)
        except Exception:
            return 0.0, 0.0


def is_available():
    return PSUTIL_OK