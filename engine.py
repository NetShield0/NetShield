# engine.py
import atexit
import ctypes
import os
import subprocess
import time

from config import ENGINES_CONFIG
from logger import get_logger

log = get_logger()

CREATE_NO_WINDOW = 0x08000000

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class DPIEngineManager:
    def __init__(self):
        self.current_engine_name = None
        self.current_mode_name = "Boşta"
        self.process = None
        self._job = None

        atexit.register(self.stop)

    def _ensure_job(self):
        if self._job:
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                log.warning("Job Object oluşturulamadı.")
                return

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            ok = kernel32.SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok:
                log.warning("SetInformationJobObject başarısız.")
                return

            self._job = job
            log.debug("Job Object hazır.")
        except Exception as e:
            log.warning(f"Job Object kurulum hatası: {e}")

    def _assign_to_job(self, proc):
        if not self._job:
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = int(proc._handle)
            ok = kernel32.AssignProcessToJobObject(self._job, handle)
            if not ok:
                log.warning("AssignProcessToJobObject başarısız.")
        except Exception as e:
            log.warning(f"Job'a atama hatası: {e}")

    def start_mode(self, engine_name: str, mode_name: str) -> bool:
        self.stop()

        if mode_name == "Boşta":
            self.current_engine_name = engine_name
            self.current_mode_name = "Boşta"
            return True

        if engine_name not in ENGINES_CONFIG:
            log.error(f"Bilinmeyen motor: {engine_name}")
            return False

        engine_info = ENGINES_CONFIG[engine_name]
        exe_path = engine_info["exe_path"]

        if mode_name not in engine_info["modes"]:
            log.error(f"Bilinmeyen mod: {mode_name}")
            return False

        if not os.path.exists(exe_path):
            log.error(f"Motor bulunamadı: {exe_path}")
            return False

        args = engine_info["modes"][mode_name]
        command = [exe_path] + args
        log.info(f"Başlatılıyor: {engine_name} / {mode_name}")
        log.debug(f"Komut: {' '.join(command)}")

        try:
            self.process = subprocess.Popen(
                command,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                cwd=os.path.dirname(exe_path),
            )
        except Exception as e:
            log.exception(f"Popen hatası: {e}")
            self.process = None
            return False

        self._ensure_job()
        self._assign_to_job(self.process)

        time.sleep(0.8)
        if self.process.poll() is not None:
            log.error(f"Motor {self.process.returncode} koduyla çöktü.")
            self.process = None
            self.current_mode_name = "Boşta"
            return False

        self.current_engine_name = engine_name
        self.current_mode_name = mode_name
        log.info("Motor başarıyla başladı.")
        return True

    def stop(self):
        if self.process and self.process.poll() is None:
            log.info("Motor durduruluyor...")
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            except Exception as e:
                log.warning(f"Durdurma hatası: {e}")
            self.process = None
            log.info("Motor durduruldu.")
        self.current_mode_name = "Boşta"

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None