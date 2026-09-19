# crypto_manager.py
import ctypes
from ctypes import wintypes

from logger import get_logger

log = get_logger()


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(
        len(data),
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)),
    )


def dpapi_encrypt(data: bytes) -> bytes:
    """Windows DPAPI ile şifreler. Sadece bu Windows kullanıcısı çözebilir."""
    blob_in = _bytes_to_blob(data)
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None, None, None, None, 0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData başarısız")

    try:
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    return result


def dpapi_decrypt(data: bytes) -> bytes:
    """DPAPI ile şifrelenmiş veriyi çözer."""
    blob_in = _bytes_to_blob(data)
    blob_out = DATA_BLOB()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None, None, None, None, 0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData başarısız (farklı kullanıcı/bilgisayar?)")

    try:
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    return result