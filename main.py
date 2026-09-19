# main.py
import ctypes
import os
import sys
import threading
import customtkinter as ctk
from tkinter import filedialog

from engine import DPIEngineManager, is_admin
from config import ENGINES_CONFIG
from dns_manager import (
    get_current_dns, set_doh_dns, reset_dns_to_dhcp,
    test_dns_leak, ping_host,
)
from targets import PACKAGES, COUNTRIES, get_targets
from blockcheck import run_blockcheck, pick_best
from profile_manager import (
    load_profile, save_profile, mark_first_run_done,
    save_last_strategy, add_test_history,
)
from vpn_manager import (
    is_wireguard_installed, install_wireguard,
    list_configs, import_config, save_config_text,
    connect, disconnect, get_active_tunnel,
    set_allowed_ips, create_warp_config,
)
from logger import get_logger
from settings_manager import (
    load_settings, save_settings,
    get_bar_config, get_bar_style_config, calc_position,
)
from tray_manager import TrayManager, notify
from startup_manager import (
    is_enabled as startup_is_enabled,
    enable as startup_enable,
    disable as startup_disable,
)
from hotkey_manager import HotkeyManager, is_available as hotkey_available
from stats_manager import StatsManager, is_available as stats_available
from killswitch_manager import KillSwitch, force_unlock
import webbrowser
from version_manager import check_update, CURRENT_VERSION

def _hide_from_taskbar(tk_window):
    """Pencereyi taskbar ve Alt+Tab'dan gizler (araç penceresi yapar)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(tk_window.winfo_id())
        if hwnd == 0:
            hwnd = tk_window.winfo_id()

        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_APPWINDOW  = 0x00040000

        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        # Pencere durumunu DEĞİŞTİRMEDEN stil değişikliğini uygula
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE
        )
    except Exception as e:
        log.warning(f"Taskbar gizleme hatası: {e}")

ctk.set_appearance_mode("Dark")
log = get_logger()

MODE_IDLE = "Boşta"


class ModeCard(ctk.CTkFrame):
    def __init__(self, parent, title, subtitle, icon, command, is_danger=False):
        super().__init__(
            parent,
            fg_color="#242428" if not is_danger else "#2A1515",
            corner_radius=10, border_width=1,
            border_color="#323238" if not is_danger else "#4A1E1E",
        )
        self.command = command
        self.is_danger = is_danger
        widgets = []

        lbl_icon = ctk.CTkLabel(self, text=icon, font=ctk.CTkFont(size=18))
        lbl_icon.pack(side="left", padx=(14, 10), pady=10)
        widgets.append(lbl_icon)

        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.pack(side="left", fill="both", expand=True, pady=6)
        widgets.append(text_frame)

        lbl_title = ctk.CTkLabel(
            text_frame, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F2F2F7" if not is_danger else "#FF453A",
            anchor="w",
        )
        lbl_title.pack(fill="x")
        widgets.append(lbl_title)

        lbl_sub = ctk.CTkLabel(
            text_frame, text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color="#8E8E93" if not is_danger else "#FF9F9A",
            anchor="w",
        )
        lbl_sub.pack(fill="x")
        widgets.append(lbl_sub)

        for w in widgets:
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", self.on_enter)
            w.bind("<Leave>", self.on_leave)

    def on_enter(self, e):
        if self.is_danger:
            self.configure(fg_color="#3A1C1C", border_color="#FF453A")
        else:
            self.configure(fg_color="#2C2C32", border_color="#0A84FF")

    def on_leave(self, e):
        if self.is_danger:
            self.configure(fg_color="#2A1515", border_color="#4A1E1E")
        else:
            self.configure(fg_color="#242428", border_color="#323238")


class MainDashboard(ctk.CTkToplevel):
    def __init__(self, parent, engine_manager):
        super().__init__(parent)
        self.parent_bar = parent
        self.manager = engine_manager
        self.profile = load_profile()

        self._test_cancel = threading.Event()
        self._test_results = []
        self._vpn_active = None
        self.tray = None
        self.stats = StatsManager()
        self.killswitch = KillSwitch()
        self._stats_job = None

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#18181A")

        self.card = ctk.CTkFrame(
            self, fg_color="#18181A", corner_radius=16,
            border_width=1, border_color="#2C2C30",
        )
        self.card.pack(fill="both", expand=True)

        # Başlık
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))

        # Logo
        try:
            from PIL import Image
            from pathlib import Path
            logo_path = Path(__file__).parent / "assets" / "netshield.ico"
            if logo_path.exists():
                logo_img = ctk.CTkImage(
                    light_image=Image.open(str(logo_path)),
                    dark_image=Image.open(str(logo_path)),
                    size=(24, 24),
                )
                ctk.CTkLabel(header, image=logo_img, text="").pack(side="left", padx=(0, 8))
        except Exception:
            pass

        ctk.CTkLabel(
            header, text="NetShield",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#0A84FF",
        ).pack(side="left")

        ctk.CTkButton(
            header, text="✕", width=22, height=22, corner_radius=11,
            fg_color="transparent", hover_color="#2C2C30",
            text_color="#8E8E93", font=ctk.CTkFont(size=11),
            command=self.withdraw,
        ).pack(side="right")

        # Sekmeler
        self.tabs = ctk.CTkTabview(
            self.card,
            fg_color="#18181A",
            segmented_button_fg_color="#242428",
            segmented_button_selected_color="#0A84FF",
            segmented_button_selected_hover_color="#007AFF",
            segmented_button_unselected_color="#242428",
            segmented_button_unselected_hover_color="#2C2C32",
            text_color="#F2F2F7",
            corner_radius=10,
            border_width=1,
            border_color="#2C2C30",
        )
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        self.tab_ana = self.tabs.add("Ana")
        self.tab_akilli = self.tabs.add("Akıllı")
        self.tab_vpn = self.tabs.add("VPN")
        self.tab_test = self.tabs.add("Test")
        self.tab_dns = self.tabs.add("DNS")
        self.tab_teshis = self.tabs.add("Teşhis")
        self.tab_ayarlar = self.tabs.add("Ayarlar")
        self.tab_yardim = self.tabs.add("Yardım")
        self.tab_hakkinda = self.tabs.add("Hakkında")

        self._build_tab_ana()
        self._build_tab_akilli()
        self._build_tab_vpn()
        self._build_tab_test()
        self._build_tab_dns()
        self._build_tab_teshis()
        self._build_tab_ayarlar()
        self._build_tab_yardim()
        self._build_tab_hakkinda()

        self.after(100, self._restore_last_strategy)
        self.after(150, self._refresh_vpn_status)
        if self.parent_bar.settings.get("killswitch_enabled", False):
            self.killswitch.enable()
        self.after(3000, self._killswitch_watchdog)

        self.after(100, lambda: _hide_from_taskbar(self))
        self.withdraw()

    # ===== ANA SEKMESİ =====
    def _build_tab_ana(self):
        self.banner = ctk.CTkFrame(
            self.tab_ana, fg_color="#1A261C", corner_radius=10,
            border_width=1, border_color="#30D158",
        )
        self._refresh_banner()

        self.status_pill = ctk.CTkFrame(
            self.tab_ana, fg_color="#261A1A", corner_radius=12,
        )
        self.status_pill.pack(anchor="w", padx=4, pady=(8, 6))

        self.lbl_status = ctk.CTkLabel(
            self.status_pill, text="● Servis Kapalı",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#FF453A",
        )
        self.lbl_status.pack(padx=10, pady=3)

        # ---- İstatistik paneli ----
        self.stats_frame = ctk.CTkFrame(
            self.tab_ana, fg_color="#1F1F23", corner_radius=10,
            border_width=1, border_color="#2C2C30",
        )

        grid = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=8)
        grid.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            grid, text="⏱️ Süre",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
        ).grid(row=0, column=0, sticky="w")
        self.lbl_stat_uptime = ctk.CTkLabel(
            grid, text="--:--:--",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F2F2F7",
        )
        self.lbl_stat_uptime.grid(row=1, column=0, sticky="w")

        ctk.CTkLabel(
            grid, text="🔗 Bağlantı",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
        ).grid(row=0, column=1, sticky="w")
        self.lbl_stat_conns = ctk.CTkLabel(
            grid, text="0",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F2F2F7",
        )
        self.lbl_stat_conns.grid(row=1, column=1, sticky="w")

        ctk.CTkLabel(
            grid, text="💾 Bellek",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
        ).grid(row=0, column=2, sticky="w")
        self.lbl_stat_mem = ctk.CTkLabel(
            grid, text="0 MB",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F2F2F7",
        )
        self.lbl_stat_mem.grid(row=1, column=2, sticky="w")

        speed_row = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        speed_row.pack(fill="x", padx=10, pady=(0, 8))

        self.lbl_stat_speed = ctk.CTkLabel(
            speed_row, text="⬇ 0 MB/s   ⬆ 0 MB/s",
            font=ctk.CTkFont(size=10), text_color="#8FCB9E",
        )
        self.lbl_stat_speed.pack(side="left")

        self._stats_visible = False

        # Motor
        ctk.CTkLabel(
            self.tab_ana, text="Motor:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        engine_list = list(ENGINES_CONFIG.keys())
        self.engine_var = ctk.StringVar(value=engine_list[0])
        self.engine_menu = ctk.CTkOptionMenu(
            self.tab_ana, values=engine_list, variable=self.engine_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28, command=self._on_engine_change,
        )
        self.engine_menu.pack(fill="x", padx=4, pady=(0, 6))

        # Strateji
        ctk.CTkLabel(
            self.tab_ana, text="Strateji:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        first_modes = list(ENGINES_CONFIG[engine_list[0]]["modes"].keys())
        self.strategy_var = ctk.StringVar(value=first_modes[0])
        self.strategy_menu = ctk.CTkOptionMenu(
            self.tab_ana, values=first_modes, variable=self.strategy_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        )
        self.strategy_menu.pack(fill="x", padx=4, pady=(0, 8))

        self.lbl_msg = ctk.CTkLabel(
            self.tab_ana, text="", font=ctk.CTkFont(size=10),
            text_color="#FF9F9A", anchor="w", wraplength=320,
        )
        self.lbl_msg.pack(fill="x", padx=4, pady=(0, 4))

        self.card_start = ModeCard(
            self.tab_ana, "Bypass'ı Başlat",
            "Seçili motor ve stratejiyle başlat", "⚡",
            lambda: self.apply_mode(self.strategy_var.get()),
        )
        self.card_start.pack(padx=4, pady=3, fill="x")

        self.card_stop = ModeCard(
            self.tab_ana, "Servisi Durdur",
            "Bypass'ı kapat ve varsayılana dön", "⏹",
            lambda: self.apply_mode(MODE_IDLE),
            is_danger=True,
        )
        self.card_stop.pack(padx=4, pady=3, fill="x")

        ctk.CTkButton(
            self.tab_ana, text="🚪 Uygulamayı Tamamen Kapat",
            height=28, corner_radius=8, fg_color="transparent",
            hover_color="#3A1C1C", text_color="#FF453A",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.parent_bar.exit_application,
        ).pack(padx=4, pady=(8, 4), fill="x")

    def _refresh_banner(self):
        for w in self.banner.winfo_children():
            w.destroy()

        if self.profile.get("first_run", True):
            self.banner.configure(fg_color="#1F1A08", border_color="#FFD60A")
            ctk.CTkLabel(
                self.banner, text="👋 NetShield'a Hoş Geldiniz",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#FFD60A", anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 0))
            ctk.CTkLabel(
                self.banner,
                text="Ağınızı analiz edip size en uygun stratejiyi bulalım.",
                font=ctk.CTkFont(size=10), text_color="#FFE580",
                anchor="w", justify="left", wraplength=300,
            ).pack(fill="x", padx=12, pady=(2, 6))
            ctk.CTkLabel(
                self.banner,
                text="ℹ️ Sıfır telemetri. Hiçbir veri gönderilmez.",
                font=ctk.CTkFont(size=9), text_color="#8E8E93",
                anchor="w", wraplength=300,
            ).pack(fill="x", padx=12, pady=(0, 6))
            ctk.CTkButton(
                self.banner,
                text="🔬 Ağ Analizini Başlat (30 sn)",
                height=28, corner_radius=8,
                fg_color="#FFD60A", hover_color="#FFC300",
                text_color="#1A1A00",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda: self.tabs.set("Test"),
            ).pack(fill="x", padx=12, pady=(0, 10))
            self.banner.pack(fill="x", padx=4, pady=(8, 4))
        else:
            last = self.profile.get("last_strategy")
            if last:
                self.banner.configure(fg_color="#1A261C", border_color="#30D158")
                ctk.CTkLabel(
                    self.banner,
                    text=f"✓ Kayıtlı: {last.get('name', '?')}",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#30D158", anchor="w",
                ).pack(fill="x", padx=12, pady=(8, 2))
                ctk.CTkLabel(
                    self.banner,
                    text=f"Motor: {last.get('engine', '?')}  •  Başarı: {last.get('success', 0)}/{last.get('total', 0)}",
                    font=ctk.CTkFont(size=10), text_color="#8FCB9E",
                    anchor="w",
                ).pack(fill="x", padx=12, pady=(0, 8))
                self.banner.pack(fill="x", padx=4, pady=(8, 4))
            else:
                self.banner.pack_forget()

    def _restore_last_strategy(self):
        last = self.profile.get("last_strategy")
        if not last:
            return
        engine_name = last.get("engine")
        mode_name = last.get("mode")
        if not engine_name or engine_name not in ENGINES_CONFIG:
            return
        ENGINES_CONFIG[engine_name]["modes"].setdefault(
            mode_name, last.get("args", []),
        )
        self.engine_var.set(engine_name)
        self._on_engine_change(engine_name)
        modes = list(ENGINES_CONFIG[engine_name]["modes"].keys())
        if mode_name in modes:
            self.strategy_var.set(mode_name)
        log.info(f"Kayıtlı strateji yüklendi: {engine_name} / {mode_name}")

    def _on_engine_change(self, engine_name):
        modes = list(ENGINES_CONFIG.get(engine_name, {}).get("modes", {}).keys())
        if not modes:
            modes = ["Standart"]
        self.strategy_menu.configure(values=modes)
        self.strategy_var.set(modes[0])

    # ===== VPN SEKMESİ =====
    def _build_tab_vpn(self):
        ctk.CTkLabel(
            self.tab_vpn, text="VPN Modu",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.tab_vpn,
            text="Cloudflare WARP ile tek tuşla VPN, ya da kendi\nWireGuard config dosyanı ekle.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(anchor="w", padx=4, pady=(0, 6))

        self.vpn_install_frame = ctk.CTkFrame(
            self.tab_vpn, fg_color="#1F1A08", corner_radius=10,
            border_width=1, border_color="#FFD60A",
        )

        self.lbl_vpn_status = ctk.CTkLabel(
            self.tab_vpn, text="● VPN: Kapalı",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8E8E93", anchor="w",
        )
        self.lbl_vpn_status.pack(fill="x", padx=4, pady=(4, 6))

        ctk.CTkLabel(
            self.tab_vpn, text="📋 Config Listesi:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.vpn_list_frame = ctk.CTkScrollableFrame(
            self.tab_vpn, fg_color="#242428",
            corner_radius=10, height=130,
        )
        self.vpn_list_frame.pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkButton(
            self.tab_vpn, text="🌐 Otomatik VPN Kur (Cloudflare WARP)",
            height=32, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._vpn_auto_warp,
        ).pack(fill="x", padx=4, pady=(4, 6))

        row1 = ctk.CTkFrame(self.tab_vpn, fg_color="transparent")
        row1.pack(fill="x", padx=4, pady=2)

        ctk.CTkButton(
            row1, text="📁 Config İçe Aktar (.conf)",
            height=26, corner_radius=6, fg_color="#242428",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=10),
            command=self._vpn_import_file,
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        ctk.CTkButton(
            row1, text="✏️ Manuel Ekle",
            height=26, corner_radius=6, fg_color="#242428",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=10),
            command=self._vpn_manual_add,
        ).pack(side="left", fill="x", expand=True, padx=(2, 0))

        ctk.CTkLabel(
            self.tab_vpn, text="🎯 Yönlendirme Modu:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(8, 2))

        self.vpn_mode_var = ctk.StringVar(value="Full Tunnel (Tüm trafik)")
        self.vpn_mode_menu = ctk.CTkOptionMenu(
            self.tab_vpn,
            values=["Full Tunnel (Tüm trafik)", "Split - Sadece DNS", "Split - Sadece Web"],
            variable=self.vpn_mode_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=10), dropdown_font=ctk.CTkFont(size=10),
            corner_radius=6, height=26,
        )
        self.vpn_mode_menu.pack(fill="x", padx=4, pady=(0, 6))

        row2 = ctk.CTkFrame(self.tab_vpn, fg_color="transparent")
        row2.pack(fill="x", padx=4, pady=(2, 4))

        self.btn_vpn_connect = ctk.CTkButton(
            row2, text="🔌 Bağlan",
            height=30, corner_radius=8, fg_color="#30D158",
            hover_color="#28B94E",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._vpn_connect,
        )
        self.btn_vpn_connect.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_vpn_disconnect = ctk.CTkButton(
            row2, text="⛔ Ayır",
            height=30, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#4A1E1E",
            hover_color="#3A1C1C", text_color="#FF453A",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._vpn_disconnect,
        )
        self.btn_vpn_disconnect.pack(side="left", fill="x", expand=True, padx=(3, 0))

        self.lbl_vpn_msg = ctk.CTkLabel(
            self.tab_vpn, text="", font=ctk.CTkFont(size=10),
            text_color="#30D158", anchor="w", wraplength=340,
        )
        self.lbl_vpn_msg.pack(fill="x", padx=4, pady=(2, 4))

    def _refresh_vpn_status(self):
        for w in self.vpn_install_frame.winfo_children():
            w.destroy()

        if not is_wireguard_installed():
            self.vpn_install_frame.pack(fill="x", padx=4, pady=(0, 6))
            ctk.CTkLabel(
                self.vpn_install_frame,
                text="⚠️ WireGuard kurulu değil",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#FFD60A", anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 0))
            ctk.CTkLabel(
                self.vpn_install_frame,
                text="VPN özelliği için WireGuard gerekli.",
                font=ctk.CTkFont(size=10), text_color="#FFE580",
                anchor="w", wraplength=320,
            ).pack(fill="x", padx=12, pady=(2, 6))
            ctk.CTkButton(
                self.vpn_install_frame,
                text="📦 WireGuard'ı Kur (otomatik)",
                height=28, corner_radius=8,
                fg_color="#FFD60A", hover_color="#FFC300",
                text_color="#1A1A00",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=self._install_wg,
            ).pack(fill="x", padx=12, pady=(0, 10))
        else:
            self.vpn_install_frame.pack_forget()

        for w in self.vpn_list_frame.winfo_children():
            w.destroy()

        configs = list_configs()
        if not configs:
            ctk.CTkLabel(
                self.vpn_list_frame,
                text="Henüz config yok.\nOtomatik kur ya da .conf içe aktar.",
                font=ctk.CTkFont(size=10), text_color="#8E8E93",
                anchor="w", justify="left",
            ).pack(fill="x", padx=10, pady=10)
        else:
            self.vpn_radio_var = ctk.StringVar(value=configs[0]["name"])
            for c in configs:
                rb = ctk.CTkRadioButton(
                    self.vpn_list_frame,
                    text=c["label"],
                    variable=self.vpn_radio_var,
                    value=c["name"],
                    fg_color="#0A84FF", hover_color="#007AFF",
                    text_color="#F2F2F7",
                    font=ctk.CTkFont(size=11),
                )
                rb.pack(anchor="w", padx=10, pady=3)

        active = get_active_tunnel()
        self._vpn_active = active
        if active:
            self.lbl_vpn_status.configure(
                text=f"● VPN: Bağlı ({active})",
                text_color="#30D158",
            )
        else:
            self.lbl_vpn_status.configure(
                text="● VPN: Kapalı", text_color="#8E8E93",
            )

    def _install_wg(self):
        self._vpn_msg("WireGuard kuruluyor...", warn=True)

        def worker():
            ok, msg = install_wireguard(
                progress_cb=lambda m: self.after(0, lambda: self._vpn_msg(m, warn=True))
            )
            self.after(0, lambda: self._vpn_msg(msg, warn=not ok))
            self.after(0, self._refresh_vpn_status)
        threading.Thread(target=worker, daemon=True).start()

    def _vpn_msg(self, text, warn=False):
        self.lbl_vpn_msg.configure(
            text=text,
            text_color="#FF9F9A" if warn else "#30D158",
        )

    def _vpn_auto_warp(self):
        if not is_wireguard_installed():
            self._vpn_msg("⚠ Önce WireGuard'ı kur.", warn=True)
            return

        self._vpn_msg("Cloudflare WARP hazırlanıyor...", warn=True)

        def worker():
            ok, msg = create_warp_config(
                progress_cb=lambda m: self.after(0, lambda: self._vpn_msg(m, warn=True))
            )
            self.after(0, lambda: self._vpn_msg(msg, warn=not ok))
            self.after(0, self._refresh_vpn_status)
        threading.Thread(target=worker, daemon=True).start()

    def _vpn_import_file(self):
        path = filedialog.askopenfilename(
            title="WireGuard Config Seç",
            filetypes=[("WireGuard Config", "*.conf"), ("Tüm Dosyalar", "*.*")],
        )
        if not path:
            return
        ok, msg = import_config(path)
        self._vpn_msg(msg, warn=not ok)
        self._refresh_vpn_status()

    def _vpn_manual_add(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Manuel Config Ekle")
        dialog.geometry("500x460")
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color="#18181A")

        ctk.CTkLabel(
            dialog, text="Config Adı:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7",
        ).pack(anchor="w", padx=16, pady=(12, 2))

        name_entry = ctk.CTkEntry(
            dialog, fg_color="#242428", text_color="#F2F2F7",
            border_color="#323238", corner_radius=8, height=28,
        )
        name_entry.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            dialog, text="WireGuard Config Metni:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7",
        ).pack(anchor="w", padx=16, pady=(2, 2))

        txt = ctk.CTkTextbox(
            dialog, fg_color="#242428", text_color="#F2F2F7",
            font=ctk.CTkFont(family="Consolas", size=10),
            corner_radius=8, border_width=1, border_color="#2C2C30",
        )
        txt.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        txt.insert(
            "end",
            "[Interface]\nPrivateKey = \nAddress = \nDNS = \n\n"
            "[Peer]\nPublicKey = \nAllowedIPs = 0.0.0.0/0, ::/0\nEndpoint = ",
        )

        msg_lbl = ctk.CTkLabel(
            dialog, text="", font=ctk.CTkFont(size=10),
            text_color="#FF9F9A",
        )
        msg_lbl.pack(fill="x", padx=16)

        def save():
            name = name_entry.get().strip()
            body = txt.get("1.0", "end").strip()
            if not name:
                msg_lbl.configure(text="⚠ İsim gerekli.")
                return
            ok, msg = save_config_text(body, name)
            msg_lbl.configure(
                text=("✅ " if ok else "⚠ ") + msg,
                text_color="#30D158" if ok else "#FF9F9A",
            )
            if ok:
                self._refresh_vpn_status()
                dialog.after(800, dialog.destroy)

        ctk.CTkButton(
            dialog, text="💾 Kaydet",
            height=32, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=save,
        ).pack(fill="x", padx=16, pady=(4, 12))

    def _vpn_mode_to_key(self):
        val = self.vpn_mode_var.get()
        if "DNS" in val:
            return "split_dns"
        if "Web" in val:
            return "split_web"
        return "full"

    def _vpn_connect(self):
        configs = list_configs()
        if not configs:
            self._vpn_msg("⚠ Önce bir config ekleyin.", warn=True)
            return

        name = self.vpn_radio_var.get()
        if not name:
            self._vpn_msg("⚠ Config seçin.", warn=True)
            return

        mode = self._vpn_mode_to_key()
        set_allowed_ips(name, mode)

        self._vpn_msg(f"Bağlanıyor: {name}...", warn=True)

        self.manager.stop()
        self.parent_bar.set_active_status(False)
        self.status_pill.configure(fg_color="#261A1A")
        self.lbl_status.configure(
            text="● Servis Kapalı", text_color="#FF453A",
        )

        def worker():
            ok, msg = connect(name)
            self.after(0, lambda: self._vpn_msg(msg, warn=not ok))
            self.after(0, self._refresh_vpn_status)
        threading.Thread(target=worker, daemon=True).start()

    def _vpn_disconnect(self):
        active = get_active_tunnel()
        if not active:
            self._vpn_msg("Zaten bağlı değil.", warn=True)
            return

        self._vpn_msg(f"Ayrılıyor: {active}...", warn=True)

        def worker():
            ok, msg = disconnect(active)
            self.after(0, lambda: self._vpn_msg(msg, warn=not ok))
            self.after(0, self._refresh_vpn_status)
        threading.Thread(target=worker, daemon=True).start()

    # ===== TEST SEKMESİ =====
    def _build_tab_test(self):
        ctk.CTkLabel(
            self.tab_test, text="Otomatik Ağ Testi",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.tab_test,
            text="Farklı stratejileri dener, hangisinin sende çalıştığını bulur.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(anchor="w", padx=4, pady=(0, 8))

        ctk.CTkLabel(
            self.tab_test, text="📦 Paket:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.test_pkg_var = ctk.StringVar(value="Discord")
        ctk.CTkOptionMenu(
            self.tab_test, values=list(PACKAGES.keys()),
            variable=self.test_pkg_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        ).pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkLabel(
            self.tab_test, text="🌍 Ülke (opsiyonel):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.test_country_var = ctk.StringVar(value="Yok")
        ctk.CTkOptionMenu(
            self.tab_test, values=list(COUNTRIES.keys()),
            variable=self.test_country_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        ).pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkLabel(
            self.tab_test, text="🔗 Özel URL (opsiyonel):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.test_custom_entry = ctk.CTkEntry(
            self.tab_test, placeholder_text="ornek.com",
            fg_color="#242428", text_color="#F2F2F7",
            border_color="#323238", font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        )
        self.test_custom_entry.pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkLabel(
            self.tab_test, text="🎚️ Kaç strateji denenecek?",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.test_count_var = ctk.StringVar(value="Hızlı (8)")
        ctk.CTkOptionMenu(
            self.tab_test,
            values=["Hızlı (8)", "Orta (16)", "Tam (23)", "Otomatik (En iyi)"],
            variable=self.test_count_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        ).pack(fill="x", padx=4, pady=(0, 8))

        btn_row = ctk.CTkFrame(self.tab_test, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=4)

        self.btn_start_test = ctk.CTkButton(
            btn_row, text="🔬 Testi Başlat",
            height=30, corner_radius=8, fg_color="#30D158",
            hover_color="#28B94E",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._start_test,
        )
        self.btn_start_test.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_cancel_test = ctk.CTkButton(
            btn_row, text="⏹ İptal",
            height=30, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#4A1E1E",
            hover_color="#3A1C1C", text_color="#FF453A",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._cancel_test, state="disabled",
        )
        self.btn_cancel_test.pack(side="left", fill="x", expand=True, padx=(3, 0))

        self.test_progress = ctk.CTkProgressBar(
            self.tab_test, height=8, corner_radius=4,
            fg_color="#242428", progress_color="#0A84FF",
        )
        self.test_progress.pack(fill="x", padx=4, pady=(4, 6))
        self.test_progress.set(0)

        self.btn_apply_best = ctk.CTkButton(
            self.tab_test, text="🏆 En İyi Stratejiyi Uygula",
            height=30, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._apply_best, state="disabled",
        )
        self.btn_apply_best.pack(fill="x", padx=4, pady=(0, 6))

        self.txt_test = ctk.CTkTextbox(
            self.tab_test, height=140, corner_radius=10,
            fg_color="#242428", text_color="#F2F2F7",
            font=ctk.CTkFont(family="Consolas", size=10),
            border_width=1, border_color="#2C2C30",
        )
        self.txt_test.pack(fill="both", expand=True, padx=4, pady=4)
        self.txt_test.insert("end", "Test başlatmak için butona bas.\n")
        self.txt_test.configure(state="disabled")

    def _test_write(self, text):
        self.txt_test.configure(state="normal")
        self.txt_test.insert("end", text + "\n")
        self.txt_test.see("end")
        self.txt_test.configure(state="disabled")

    def _test_clear(self):
        self.txt_test.configure(state="normal")
        self.txt_test.delete("1.0", "end")
        self.txt_test.configure(state="disabled")

    def _parse_strategy_count(self):
        val = self.test_count_var.get()
        if "8" in val:
            return 8
        if "16" in val:
            return 16
        if "23" in val:
            return 23
        return 999

    def _start_test(self):
        targets = get_targets(
            self.test_pkg_var.get(),
            self.test_country_var.get(),
            self.test_custom_entry.get(),
        )
        if not targets:
            self._test_write("⚠ Hedef bulunamadı.")
            return

        limit = self._parse_strategy_count()
        self._test_cancel.clear()
        self._test_results = []

        self._test_clear()
        self._test_write(f"▶ Hedefler: {', '.join(targets)}")
        self._test_write(f"▶ Strateji limiti: {limit}")
        self._test_write("─" * 40)

        self.btn_start_test.configure(state="disabled")
        self.btn_cancel_test.configure(state="normal")
        self.btn_apply_best.configure(state="disabled")
        self.test_progress.set(0)

        def progress_cb(current, total, msg):
            self.after(0, lambda: self._on_progress(current, total, msg))

        def result_cb(result):
            self._test_results.append(result)
            self.after(0, lambda r=result: self._on_result(r))

        def worker():
            self.manager.stop()
            self.after(0, lambda: self.parent_bar.set_active_status(False))
            self.after(0, lambda: self.status_pill.configure(fg_color="#261A1A"))
            self.after(0, lambda: self.lbl_status.configure(
                text="● Servis Kapalı", text_color="#FF453A"))

            run_blockcheck(
                targets, limit,
                progress_cb, result_cb,
                self._test_cancel,
            )
            self.after(0, self._test_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, current, total, msg):
        if total > 0:
            self.test_progress.set(current / total)
        self._test_write(msg)

    def _on_result(self, result):
        if result["success"] > 0:
            self._test_write(
                f"✅ {result['name']}: {result['success']}/{result['total']}"
            )
        else:
            err = result.get("error", "")
            suffix = f" ({err})" if err else ""
            self._test_write(f"❌ {result['name']}: 0/{result['total']}{suffix}")

    def _test_done(self):
        self.btn_start_test.configure(state="normal")
        self.btn_cancel_test.configure(state="disabled")
        self.test_progress.set(1)

        best = pick_best(self._test_results)
        if best:
            self._test_write("─" * 40)
            self._test_write(
                f"🏆 En iyi: {best['name']} ({best['success']}/{best['total']})"
            )
            self.btn_apply_best.configure(state="normal")
            add_test_history(self.profile, {
                "best": best["name"],
                "success": best["success"],
                "total": best["total"],
            })
        else:
            self._test_write("─" * 40)
            self._test_write("⚠ Hiçbir strateji çalışmadı.")

    def _cancel_test(self):
        self._test_cancel.set()
        self._test_write("⏹ İptal ediliyor...")

    def _apply_best(self):
        best = pick_best(self._test_results)
        if not best:
            return
        self._test_write(f"▶ Uygulanıyor: {best['name']}")

        self.manager.stop()

        exe_path = best["exe"]
        engine_name = "Zapret Lua" if "winws2" in exe_path else "Zapret Classic"
        mode_name = f"🏆 {best['name']}"

        ENGINES_CONFIG[engine_name]["modes"][mode_name] = best["args"]

        self.engine_var.set(engine_name)
        self._on_engine_change(engine_name)
        self.strategy_var.set(mode_name)

        save_last_strategy(self.profile, best, engine_name, mode_name)
        mark_first_run_done(self.profile)
        self._refresh_banner()

        self.apply_mode(mode_name)
        self.tabs.set("Ana")
        self._test_write(f"✅ Uygulandı ve kaydedildi: {best['name']}")

    # ===== DNS SEKMESİ =====
    def _build_tab_dns(self):
        ctk.CTkLabel(
            self.tab_dns, text="DNS Gizliliği",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.tab_dns,
            text="DNS sorgularını şifreler ve reklamları engeller.\n"
                 "İkisi birbirinin yerine geçer — biri aktif olabilir.",
            font=ctk.CTkFont(size=15), text_color="#8E8E93",
            justify="left", anchor="w",
        ).pack(anchor="w", padx=4, pady=(0, 10))

        self.dns_info_frame = ctk.CTkFrame(
            self.tab_dns, fg_color="#242428", corner_radius=10,
        )
        self.dns_info_frame.pack(fill="x", padx=4, pady=4)

        self.lbl_dns_info = ctk.CTkLabel(
            self.dns_info_frame, text="DNS bilgisi yükleniyor...",
            font=ctk.CTkFont(size=13), text_color="#F2F2F7",
            anchor="w", justify="left", wraplength=300,
        )
        self.lbl_dns_info.pack(padx=10, pady=8, fill="x")

                # ---- Reklam Engelleme ----
        ctk.CTkLabel(
            self.tab_dns, text="🚫 Reklam Engelleme:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FF9500", anchor="w",
        ).pack(fill="x", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.tab_dns,
            text="AdGuard DNS ile tarayıcı, uygulama ve sistem\ngenelindeki reklamları engeller.",
            font=ctk.CTkFont(size=14), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkButton(
            self.tab_dns, text="🚫 Gizlilik + Reklam Engelle (Adguard DoH)",
            height=30, corner_radius=8, fg_color="#FF9500",
            hover_color="#E08400",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._enable_adblock,
        ).pack(fill="x", padx=4, pady=4)

        ctk.CTkButton(
            self.tab_dns, text="🔬 Reklam Engellemeyi Test Et",
            height=28, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#323238",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=10),
            command=self._test_adblock,
        ).pack(fill="x", padx=4, pady=(0, 6))

        # ---- Ayırıcı ----
        ctk.CTkLabel(
            self.tab_dns, text="─" * 40,
            font=ctk.CTkFont(size=8), text_color="#2C2C30",
        ).pack(fill="x", padx=4, pady=(2, 2))

        ctk.CTkLabel(
            self.tab_dns, text="🛡️ DNS Gizliliği:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#0A84FF", anchor="w",
        ).pack(fill="x", padx=4, pady=(4, 2))

        ctk.CTkButton(
            self.tab_dns, text="🛡️ Sadece Gizlilik (Cloudflare DoH)",
            height=30, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._enable_doh,
        ).pack(fill="x", padx=4, pady=4)

        ctk.CTkButton(
            self.tab_dns, text="♻️ Varsayılan DNS'e Dön (DHCP)",
            height=30, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#4A1E1E",
            hover_color="#3A1C1C", text_color="#FF453A",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._reset_dns,
        ).pack(fill="x", padx=4, pady=4)

        ctk.CTkButton(
            self.tab_dns, text="🔍 Mevcut DNS'i Yenile",
            height=28, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#323238",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11),
            command=self._refresh_dns_info,
        ).pack(fill="x", padx=4, pady=4)

        self.lbl_dns_msg = ctk.CTkLabel(
            self.tab_dns, text="", font=ctk.CTkFont(size=10),
            text_color="#30D158", anchor="w", wraplength=300,
        )
        self.lbl_dns_msg.pack(fill="x", padx=4, pady=(2, 4))

        self.after(300, self._refresh_dns_info)

    def _refresh_dns_info(self):
        dns = get_current_dns()
        if not dns:
            self.lbl_dns_info.configure(
                text="Aktif ağ arayüzü bulunamadı.", text_color="#FF453A",
            )
            return
        lines = []
        for iface, servers in dns.items():
            srv = ", ".join(servers) if servers else "Yok"
            lines.append(f"▸ {iface}\n   {srv}")
        self.lbl_dns_info.configure(
            text="\n".join(lines), text_color="#F2F2F7",
        )

    def _enable_adblock(self):
        from dns_manager import set_adblock_dns
        ok, msg = set_adblock_dns()
        self.lbl_dns_msg.configure(
            text=("✅ " if ok else "⚠ ") + msg,
            text_color="#30D158" if ok else "#FF9F9A",
        )
        self.after(800, self._refresh_dns_info)

    def _test_adblock(self):
        from dns_manager import test_adblock
        ok, msg = test_adblock()
        self.lbl_dns_msg.configure(
            text=("✅ " if ok else "⚠ ") + msg,
            text_color="#30D158" if ok else "#FF9F9A",
        )

    def _enable_doh(self):
        ok, msg = set_doh_dns()
        self.lbl_dns_msg.configure(
            text=("✅ " if ok else "⚠ ") + msg,
            text_color="#30D158" if ok else "#FF9F9A",
        )
        self.after(500, self._refresh_dns_info)

    def _reset_dns(self):
        ok, msg = reset_dns_to_dhcp()
        self.lbl_dns_msg.configure(
            text=("✅ " if ok else "⚠ ") + msg,
            text_color="#30D158" if ok else "#FF9F9A",
        )
        self.after(500, self._refresh_dns_info)

    # ===== TEŞHİS SEKMESİ =====
    def _build_tab_teshis(self):
        ctk.CTkLabel(
            self.tab_teshis, text="Ağ Teşhis",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.tab_teshis,
            text="Bağlantını test et: ping, DNS sızıntısı, dış IP.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w", justify="left",
        ).pack(anchor="w", padx=4, pady=(0, 10))

        self.txt_diag = ctk.CTkTextbox(
            self.tab_teshis, height=180, corner_radius=10,
            fg_color="#242428", text_color="#F2F2F7",
            font=ctk.CTkFont(family="Consolas", size=10),
            border_width=1, border_color="#2C2C30",
        )
        self.txt_diag.pack(fill="both", expand=True, padx=4, pady=4)
        self.txt_diag.insert("end", "Test başlatmak için butona bas.\n")
        self.txt_diag.configure(state="disabled")

        btn_row = ctk.CTkFrame(self.tab_teshis, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=4)

        ctk.CTkButton(
            btn_row, text="🌐 Dış IP + DNS Testi",
            height=30, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._run_dns_leak_test,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))

        ctk.CTkButton(
            btn_row, text="📡 Ping (1.1.1.1)",
            height=30, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._run_ping_test,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        ctk.CTkButton(
            self.tab_teshis, text="🗑️ Temizle",
            height=24, corner_radius=6, fg_color="transparent",
            hover_color="#2C2C32", text_color="#8E8E93",
            font=ctk.CTkFont(size=10),
            command=self._clear_diag,
        ).pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkButton(
            self.tab_teshis, text="📜 Logları Göster",
            height=28, corner_radius=8, fg_color="#242428",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11),
            command=self._show_logs,
        ).pack(fill="x", padx=4, pady=(4, 4))

            # ---- Hız Testi ----
        ctk.CTkLabel(
            self.tab_teshis, text="🌐 Hız Testi:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#30D158", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        speed_row = ctk.CTkFrame(self.tab_teshis, fg_color="transparent")
        speed_row.pack(fill="x", padx=4, pady=2)

        self.btn_speedtest = ctk.CTkButton(
            speed_row, text="🚀 Hız Testini Başlat",
            height=30, corner_radius=8, fg_color="#30D158",
            hover_color="#28B94E",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._start_speedtest,
        )
        self.btn_speedtest.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_speedtest_cancel = ctk.CTkButton(
            speed_row, text="⏹ İptal",
            height=30, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#4A1E1E",
            hover_color="#3A1C1C", text_color="#FF453A",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._cancel_speedtest, state="disabled",
        )
        self.btn_speedtest_cancel.pack(side="left", padx=(3, 0))

        # Sonuç kutusu
        self.speed_result_frame = ctk.CTkFrame(
            self.tab_teshis, fg_color="#1F1F23", corner_radius=10,
            border_width=1, border_color="#2C2C30",
        )
        self.speed_result_frame.pack(fill="x", padx=4, pady=(4, 8))

        speed_grid = ctk.CTkFrame(self.speed_result_frame, fg_color="transparent")
        speed_grid.pack(fill="x", padx=12, pady=10)
        speed_grid.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            speed_grid, text="📡 Ping",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
        ).grid(row=0, column=0, sticky="w")
        self.lbl_speed_ping = ctk.CTkLabel(
            speed_grid, text="-- ms",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F2F2F7",
        )
        self.lbl_speed_ping.grid(row=1, column=0, sticky="w")

        ctk.CTkLabel(
            speed_grid, text="⬇ İndirme",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
        ).grid(row=0, column=1, sticky="w")
        self.lbl_speed_down = ctk.CTkLabel(
            speed_grid, text="-- Mbps",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#0A84FF",
        )
        self.lbl_speed_down.grid(row=1, column=1, sticky="w")

        ctk.CTkLabel(
            speed_grid, text="⬆ Yükleme",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
        ).grid(row=0, column=2, sticky="w")
        self.lbl_speed_up = ctk.CTkLabel(
            speed_grid, text="-- Mbps",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#30D158",
        )
        self.lbl_speed_up.grid(row=1, column=2, sticky="w")

    def _diag_write(self, text):
        self.txt_diag.configure(state="normal")
        self.txt_diag.insert("end", text + "\n")
        self.txt_diag.see("end")
        self.txt_diag.configure(state="disabled")

    def _clear_diag(self):
        self.txt_diag.configure(state="normal")
        self.txt_diag.delete("1.0", "end")
        self.txt_diag.configure(state="disabled")

    def _run_dns_leak_test(self):
        self._diag_write("▶ Dış IP ve DNS testi çalışıyor...")

        def worker():
            res = test_dns_leak()
            if res["success"]:
                self.after(0, lambda: self._diag_write(
                    f"✅ Dış IP: {res['ip']}\n"
                    f"   Konum: {res['loc']} | Colo: {res['colo']}"
                ))
            else:
                self.after(0, lambda: self._diag_write(
                    f"❌ Hata: {res['error']}"
                ))
        threading.Thread(target=worker, daemon=True).start()

    def _run_ping_test(self):
        self._diag_write("▶ 1.1.1.1 adresine ping atılıyor...")

        def worker():
            ok, avg = ping_host("1.1.1.1", count=4)
            if ok:
                self.after(0, lambda: self._diag_write(
                    f"✅ Ortalama gecikme: {avg} ms"
                ))
            else:
                self.after(0, lambda: self._diag_write("❌ Ping başarısız."))
        threading.Thread(target=worker, daemon=True).start()

    # ===== YARDIM SEKMESİ =====
    def _build_tab_yardim(self):
        scroll = ctk.CTkScrollableFrame(
            self.tab_yardim, fg_color="transparent",
            scrollbar_button_color="#3A3A40",
            scrollbar_button_hover_color="#0A84FF",
        )
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            scroll, text="❓ Yardım & Kullanım",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#0A84FF", anchor="w",
        ).pack(fill="x", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            scroll,
            text="NetShield'a hoş geldiniz! Aşağıda kısa bir rehber var.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=360,
        ).pack(fill="x", padx=4, pady=(0, 10))

        sections = [
            ("🚀 Hızlı Başlangıç",
             "1. Ana sekmesi → 'Bypass'ı Başlat'\n"
             "2. Motor ve strateji seçili kalır\n"
             "3. Rozet yeşile dönerse çalışıyor demektir."),

            ("🔬 Otomatik Ağ Testi",
             "Test sekmesinde hedef paket/ülke seç.\n"
             "'Testi Başlat' → 23 strateji sırayla denenir.\n"
             "En iyi strateji otomatik uygulanır ve kaydedilir."),

            ("🎯 Akıllı Mod",
             "Zapret ve VPN'i aynı anda test eder.\n"
             "Hangisi daha başarılıysa onu başlatır."),

            ("🌐 VPN",
             "Tek tuşla Cloudflare WARP VPN kurulur.\n"
             "Kendi WireGuard .conf dosyanı da içe aktarabilirsin.\n"
             "Config'ler DPAPI ile şifreli saklanır."),

            ("🚫 DNS & Reklam Engelleme",
             "DNS sekmesinden:\n"
             "• Cloudflare DoH → gizli DNS\n"
             "• AdGuard DoH → reklam + gizli DNS"),

            ("🔒 Kill Switch",
             "Ayarlar → Kill Switch aç.\n"
             "VPN çökerse internet otomatik kesilir."),

            ("⌨️ Global Kısayollar",
             "Ctrl+Shift+B  →  Bypass aç/kapat\n"
             "Ctrl+Shift+P  →  Paneli aç\n"
             "Ayarlar'dan değiştirebilirsin."),

            ("🖱️ Bar Kullanımı",
             "Bar'a tıkla → panel açılır/kapanır.\n"
             "Bar'ın yerini, tarzını ve opaklığını Ayarlar'dan değiştir.\n"
             "Sağ alt köşedeki tray ikonuna sağ tık → hızlı menü."),

            ("📊 İstatistikler",
             "Bypass aktifken Ana sekmede görünür:\n"
             "süre, bağlantı sayısı, bellek, hız."),

            ("💡 İpuçları",
             "• Bir strateji çalışmazsa, diğerini dene.\n"
             "• Farklı ISS'ler farklı strateji sever.\n"
             "• Log dosyanı Ayarlar → 'Log Dosyasını Aç' ile inceleyebilirsin."),
        ]

        for title, body in sections:
            box = ctk.CTkFrame(
                scroll, fg_color="#1F1F23", corner_radius=10,
                border_width=1, border_color="#2C2C30",
            )
            box.pack(fill="x", padx=4, pady=4)

            ctk.CTkLabel(
                box, text=title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#F2F2F7", anchor="w",
            ).pack(fill="x", padx=12, pady=(8, 2))

            ctk.CTkLabel(
                box, text=body,
                font=ctk.CTkFont(size=15), text_color="#B8B8BD",
                anchor="w", justify="left", wraplength=340,
            ).pack(fill="x", padx=12, pady=(0, 10))

    # ===== HAKKINDA SEKMESİ =====
    def _build_tab_hakkinda(self):
        scroll = ctk.CTkScrollableFrame(
            self.tab_hakkinda, fg_color="transparent",
            scrollbar_button_color="#3A3A40",
            scrollbar_button_hover_color="#0A84FF",
        )
        scroll.pack(fill="both", expand=True)

        # Logo + başlık
        logo_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        logo_frame.pack(fill="x", padx=4, pady=(10, 8))

        try:
            from PIL import Image
            from pathlib import Path
            logo_path = Path(__file__).parent / "assets" / "netshield.ico"
            if logo_path.exists():
                img = ctk.CTkImage(
                    light_image=Image.open(str(logo_path)),
                    dark_image=Image.open(str(logo_path)),
                    size=(64, 64),
                )
                ctk.CTkLabel(logo_frame, image=img, text="").pack(pady=(0, 6))
        except Exception:
            pass

        ctk.CTkLabel(
            logo_frame, text="NetShield",
            font=ctk.CTkFont(size=25, weight="bold"),
            text_color="#0A84FF",
        ).pack()

        ctk.CTkLabel(
            logo_frame, text=f"Sürüm {CURRENT_VERSION}",
            font=ctk.CTkFont(size=11), text_color="#8E8E93",
        ).pack(pady=(2, 0))

        # Açıklama
        ctk.CTkLabel(
            scroll,
            text="Ağ gizliliği ve DPI bypass için\ntek tıkla çalışan masaüstü aracı.",
            font=ctk.CTkFont(size=13), text_color="#B8B8BD",
            anchor="center", justify="center",
        ).pack(fill="x", padx=4, pady=(8, 12))

        # Özellikler
        ctk.CTkLabel(
            scroll, text="✨ Özellikler",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(4, 4))

        features = [
            "🚀 DPI Bypass (3 motor: GoodbyeDPI, Zapret Classic/Lua)",
            "🔬 23+ strateji otomatik test",
            "🌐 VPN (Cloudflare WARP + WireGuard)",
            "🚫 DNS gizliliği + reklam engelleme",
            "🔒 Kill Switch",
            "📊 Canlı istatistikler",
            "⌨️ Global kısayollar",
            "🖥️ Sistem tepsisi + arka plan modu",
        ]
        for f in features:
            ctk.CTkLabel(
                scroll, text=f,
                font=ctk.CTkFont(size=13), text_color="#8FCB9E",
                anchor="w",
            ).pack(fill="x", padx=8, pady=1)

        # Güvenlik
        ctk.CTkLabel(
            scroll, text="🔒 Gizlilik",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#30D158", anchor="w",
        ).pack(fill="x", padx=4, pady=(12, 4))

        for g in [
            "✓ Sıfır telemetri",
            "✓ Sıfır log gönderimi",
            "✓ Şifreli VPN config (DPAPI)",
            "✓ Tüm veri cihazınızda kalır",
        ]:
            ctk.CTkLabel(
                scroll, text=g,
                font=ctk.CTkFont(size=13), text_color="#8FCB9E",
                anchor="w",
            ).pack(fill="x", padx=8, pady=1)

        # Sürüm kontrolü
        self.update_frame = ctk.CTkFrame(
            scroll, fg_color="#242428", corner_radius=10,
            border_width=1, border_color="#2C2C30",
        )
        self.update_frame.pack(fill="x", padx=4, pady=(12, 6))

        self.lbl_update = ctk.CTkLabel(
            self.update_frame, text="🔄 Sürüm kontrol ediliyor...",
            font=ctk.CTkFont(size=11), text_color="#8E8E93",
            anchor="w",
        )
        self.lbl_update.pack(fill="x", padx=12, pady=8)

        # Sürüm kontrolünü tetikle
        self.after(500, self._check_version)

        # Linkler
        ctk.CTkLabel(
            scroll, text="🌐 Bağlantılar",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(12, 4))

        links = [
            ("📦 GitHub", "https://github.com/netshield"),
            ("🐛 Hata Bildir", "https://github.com/netshield/issues"),
            ("📖 Dokümantasyon", "https://github.com/netshield/wiki"),
        ]
        for label, url in links:
            ctk.CTkButton(
                scroll, text=label,
                height=28, corner_radius=8, fg_color="#242428",
                hover_color="#2C2C32", text_color="#0A84FF",
                border_width=1, border_color="#323238",
                font=ctk.CTkFont(size=10),
                command=lambda u=url: webbrowser.open(u),
            ).pack(fill="x", padx=4, pady=2)

        # Lisans
        ctk.CTkLabel(
            scroll,
            text="\n📄 Lisans: MIT\n"
                 "© 2026 NetShield Project\n"
                 "Açık kaynak, ücretsiz, sıfır telemetri.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="center", justify="center",
        ).pack(fill="x", padx=4, pady=(12, 12))

    def _check_version(self):
        def cb(new_ver, url):
            if new_ver:
                self.after(0, lambda: self.lbl_update.configure(
                    text=f"Yeni sürüm: v{new_ver}  (şu an v{CURRENT_VERSION})\n"
                         f"İndirmek için tıkla → {url}",
                    text_color="#FFD60A",
                ))
            else:
                self.after(0, lambda: self.lbl_update.configure(
                    text="✅ En son sürümü kullanıyorsunuz.",
                    text_color="#30D158",
                ))

        check_update(cb)

    # ===== AYARLAR SEKMESİ =====
    def _build_tab_ayarlar(self):
        self.ayar_scroll = ctk.CTkScrollableFrame(
            self.tab_ayarlar,
            fg_color="transparent",
            scrollbar_button_color="#3A3A40",
            scrollbar_button_hover_color="#0A84FF",
        )
        self.ayar_scroll.pack(fill="both", expand=True)

        s = self.parent_bar.settings

        ctk.CTkLabel(
            self.ayar_scroll, text="Ayarlar",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="Uygulama görünümü ve davranışını buradan ayarlayın.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(anchor="w", padx=4, pady=(0, 10))

        # ---- Bar Konumu ----
        ctk.CTkLabel(
            self.ayar_scroll, text="📍 Bar Konumu:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.bar_position_var = ctk.StringVar(
            value=s.get("bar_position", "bottom_center")
        )
        position_labels = {
            "bottom_center": "Alt-Orta",
            "bottom_left": "Alt-Sol",
            "bottom_right": "Alt-Sağ",
            "top_center": "Üst-Orta",
            "top_left": "Üst-Sol",
            "top_right": "Üst-Sağ",
        }
        self.bar_position_menu = ctk.CTkOptionMenu(
            self.ayar_scroll,
            values=list(position_labels.values()),
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=6, height=28,
            command=self._on_bar_position_change,
        )
        current_label = position_labels.get(
            s.get("bar_position", "bottom_center"), "Alt-Orta"
        )
        self.bar_position_menu.set(current_label)
        self.bar_position_menu.pack(fill="x", padx=4, pady=(0, 8))

        # ---- Bar Tarzı ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🎨 Bar Tarzı:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.bar_style_var = ctk.StringVar(value=s.get("bar_style", "line"))
        style_labels = {
            "line": "Çizgi",
            "dot": "Nokta",
            "button": "Buton",
            "tray_only": "Sadece Tray",
        }
        self.bar_style_menu = ctk.CTkOptionMenu(
            self.ayar_scroll,
            values=list(style_labels.values()),
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=6, height=28,
            command=self._on_bar_style_change,
        )
        current_style = style_labels.get(s.get("bar_style", "line"), "Çizgi")
        self.bar_style_menu.set(current_style)
        self.bar_style_menu.pack(fill="x", padx=4, pady=(0, 8))


        # ---- Bar Boyutu ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🎚️ Alt Bar Boyutu:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.bar_size_var = ctk.StringVar(value=s.get("bar_size", "medium"))
        ctk.CTkSegmentedButton(
            self.ayar_scroll,
            values=["small", "medium", "large"],
            variable=self.bar_size_var,
            selected_color="#0A84FF",
            unselected_color="#242428",
            selected_hover_color="#007AFF",
            unselected_hover_color="#2C2C32",
            font=ctk.CTkFont(size=11),
            height=28,
            command=self._on_bar_size_change,
        ).pack(fill="x", padx=4, pady=(0, 8))

        # ---- Bar Görünürlük ----
        self.bar_visible_var = ctk.BooleanVar(value=s.get("bar_visible", True))
        ctk.CTkSwitch(
            self.ayar_scroll, text="Bar'ı göster",
            variable=self.bar_visible_var,
            font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
            progress_color="#0A84FF",
            command=self._on_bar_visible_change,
        ).pack(anchor="w", padx=4, pady=(0, 4))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="Kapalıysa bar gizlenir (silinmez). Panelden geri açabilirsiniz.",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(fill="x", padx=4, pady=(0, 10))

        # ---- Bar Opaklık ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🌫️ Bar Opaklığı:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.opacity_slider = ctk.CTkSlider(
            self.ayar_scroll, from_=0.3, to=1.0,
            number_of_steps=14,
            progress_color="#0A84FF",
            button_color="#0A84FF",
            button_hover_color="#007AFF",
            command=self._on_opacity_change,
        )
        self.opacity_slider.set(s.get("bar_opacity", 0.9))
        self.opacity_slider.pack(fill="x", padx=4, pady=(0, 2))

        self.lbl_opacity = ctk.CTkLabel(
            self.ayar_scroll, text=f"{int(s.get('bar_opacity', 0.9) * 100)}%",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w",
        )
        self.lbl_opacity.pack(fill="x", padx=4, pady=(0, 10))

        # ---- Pencere Boyutu ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🪟 Panel Boyutu:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        row_win = ctk.CTkFrame(self.ayar_scroll, fg_color="transparent")
        row_win.pack(fill="x", padx=4, pady=(0, 8))

        self.win_w_var = ctk.StringVar(value=str(s.get("window_width", 520)))
        self.win_h_var = ctk.StringVar(value=str(s.get("window_height", 800)))

        ctk.CTkLabel(
            row_win, text="G:", font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
        ).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(
            row_win, textvariable=self.win_w_var, width=70,
            fg_color="#242428", text_color="#F2F2F7",
            border_color="#323238", corner_radius=6, height=28,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            row_win, text="Y:", font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
        ).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(
            row_win, textvariable=self.win_h_var, width=70,
            fg_color="#242428", text_color="#F2F2F7",
            border_color="#323238", corner_radius=6, height=28,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row_win, text="Uygula",
            width=70, height=28, corner_radius=6,
            fg_color="#0A84FF", hover_color="#007AFF",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._on_window_size_apply,
        ).pack(side="left")

        # ---- Otomatik Başlatma ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🚀 Otomatik Başlatma:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        self.startup_var = ctk.BooleanVar(value=startup_is_enabled())
        ctk.CTkSwitch(
            self.ayar_scroll, text="Windows açılınca otomatik başlat",
            variable=self.startup_var,
            font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
            progress_color="#0A84FF",
            command=self._on_startup_change,
        ).pack(anchor="w", padx=4, pady=(0, 4))

        # ---- Global Kısayollar ----
        ctk.CTkLabel(
            self.ayar_scroll, text="⌨️ Global Kısayollar:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="Örnek: ctrl+shift+b, alt+f1, ctrl+alt+x",
            font=ctk.CTkFont(size=9), text_color="#8E8E93",
            anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 2))

        # Toggle kısayolu
        ctk.CTkLabel(
            self.ayar_scroll, text="Bypass Aç/Kapat:",
            font=ctk.CTkFont(size=10), text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        hk_row1 = ctk.CTkFrame(self.ayar_scroll, fg_color="transparent")
        hk_row1.pack(fill="x", padx=4, pady=(0, 4))

        self.hk_toggle_var = ctk.StringVar(
            value=s.get("hotkey_toggle", "ctrl+shift+b")
        )
        ctk.CTkEntry(
            hk_row1, textvariable=self.hk_toggle_var,
            fg_color="#242428", text_color="#F2F2F7",
            border_color="#323238", corner_radius=6, height=28,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            hk_row1, text="Kaydet", width=70, height=28,
            corner_radius=6, fg_color="#0A84FF", hover_color="#007AFF",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._on_hotkey_toggle_save,
        ).pack(side="left")

        # Show kısayolu
        ctk.CTkLabel(
            self.ayar_scroll, text="Paneli Aç:",
            font=ctk.CTkFont(size=10), text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(4, 2))

        hk_row2 = ctk.CTkFrame(self.ayar_scroll, fg_color="transparent")
        hk_row2.pack(fill="x", padx=4, pady=(0, 6))

        self.hk_show_var = ctk.StringVar(
            value=s.get("hotkey_show", "ctrl+shift+p")
        )
        ctk.CTkEntry(
            hk_row2, textvariable=self.hk_show_var,
            fg_color="#242428", text_color="#F2F2F7",
            border_color="#323238", corner_radius=6, height=28,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            hk_row2, text="Kaydet", width=70, height=28,
            corner_radius=6, fg_color="#0A84FF", hover_color="#007AFF",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._on_hotkey_show_save,
        ).pack(side="left")

        # ---- Gizlilik ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🔒 Gizlilik:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#30D158", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="✓ Sıfır telemetri\n"
                 "✓ Sıfır log gönderimi\n"
                 "✓ Sıfır takip\n"
                 "✓ %100 gizlilik — tüm veri cihazınızda kalır",
            font=ctk.CTkFont(size=10), text_color="#8FCB9E",
            anchor="w", justify="left", wraplength=340,
        ).pack(fill="x", padx=4, pady=(0, 8))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="🚫 Reklam Engelleme: DNS sekmesinden açılır",
            font=ctk.CTkFont(size=10), text_color="#FF9500",
            anchor="w", wraplength=340,
        ).pack(fill="x", padx=4, pady=(4, 8))

        # ---- İletişim & Destek ----
        ctk.CTkLabel(
            self.ayar_scroll, text="📞 İletişim & Destek:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(6, 2))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="Sorun yaşarsanız bize ulaşın. Log dosyanızı\n"
                 "açıp inceleyebilir, isterseniz bize gönderebilirsiniz.",
            font=ctk.CTkFont(size=13), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="📧 netshield_dpi@protonmail.com\n"
                 "🌐 github.com/NetShield0\n",
            font=ctk.CTkFont(size=15), text_color="#0A84FF",
            anchor="w", justify="left", wraplength=340,
        ).pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkButton(
            self.ayar_scroll, text="📜 Log Dosyasını Aç",
            height=28, corner_radius=8, fg_color="#242428",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=12),
            command=self._open_log_file,
        ).pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkButton(
            self.ayar_scroll, text="📋 Log Yolunu Kopyala",
            height=28, corner_radius=8, fg_color="#242428",
            hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=12),
            command=self._copy_log_path,
        ).pack(fill="x", padx=4, pady=(0, 4))

        # ---- Mesaj Kutusu ----
        self.lbl_ayar_msg = ctk.CTkLabel(
            self.ayar_scroll, text="", font=ctk.CTkFont(size=10),
            text_color="#30D158", anchor="w", wraplength=340,
        )
        self.lbl_ayar_msg.pack(fill="x", padx=4, pady=(8, 4))

        # ---- Kill Switch ----
        ctk.CTkLabel(
            self.ayar_scroll, text="🔒 Kill Switch:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#FF453A", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        ctk.CTkLabel(
            self.ayar_scroll,
            text="VPN bağlantısı koparsa interneti otomatik keser.\n"
                 "Böylece trafiğiniz asla açık ağdan akmaz.",
            font=ctk.CTkFont(size=11), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=340,
        ).pack(fill="x", padx=4, pady=(0, 4))

        self.killswitch_var = ctk.BooleanVar(
            value=s.get("killswitch_enabled", False)
        )
        ctk.CTkSwitch(
            self.ayar_scroll, text="Kill Switch'i etkinleştir",
            variable=self.killswitch_var,
            font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
            progress_color="#FF453A",
            command=self._on_killswitch_change,
        ).pack(anchor="w", padx=4, pady=(0, 4))

        ctk.CTkButton(
            self.ayar_scroll, text="🔓 İnternet Kilidini Zorla Kaldır",
            height=28, corner_radius=8, fg_color="#242428",
            hover_color="#3A1C1C", text_color="#FF453A",
            border_width=1, border_color="#4A1E1E",
            font=ctk.CTkFont(size=10),
            command=self._killswitch_panic,
        ).pack(fill="x", padx=4, pady=(0, 6))

    def _apply_setting(self, key, value):
        try:
            new = dict(self.parent_bar.settings)
            new[key] = value
            self.parent_bar.apply_settings(new)
            self._ayar_msg(f"✅ {key} = {value}")
        except Exception as e:
            log.error(f"Ayar uygulama hatası: {e}")

    def _ayar_msg(self, text):
        try:
            self.lbl_ayar_msg.configure(text=text)
            self.after(3000, lambda: self._ayar_msg_safe_clear())
        except Exception:
            pass

    def _ayar_msg_safe_clear(self):
        try:
            self.lbl_ayar_msg.configure(text="")
        except Exception:
            pass

    def _open_log_file(self):
        from logger import LOG_FILE
        import subprocess
        try:
            if not LOG_FILE.exists():
                LOG_FILE.write_text("Log dosyası henüz oluşmadı.", encoding="utf-8")
            subprocess.Popen(["notepad.exe", str(LOG_FILE)])
        except Exception as e:
            self._ayar_msg(f"⚠ Açma hatası: {e}")

    def _copy_log_path(self):
        from logger import LOG_FILE
        try:
            self.clipboard_clear()
            self.clipboard_append(str(LOG_FILE))
            self._ayar_msg(f"✅ Yol kopyalandı")
        except Exception as e:
            self._ayar_msg(f"⚠ Kopyalama hatası: {e}")

    def _on_bar_position_change(self, label):
        position_map = {
            "Alt-Orta": "bottom_center",
            "Alt-Sol": "bottom_left",
            "Alt-Sağ": "bottom_right",
            "Üst-Orta": "top_center",
            "Üst-Sol": "top_left",
            "Üst-Sağ": "top_right",
        }
        key = position_map.get(label, "bottom_center")
        self._apply_setting("bar_position", key)
        self._ayar_msg(f"✅ Konum: {label}")

    def _on_bar_style_change(self, label):
        style_map = {
            "Çizgi": "line",
            "Nokta": "dot",
            "Buton": "button",
            "Sadece Tray": "tray_only",
        }
        key = style_map.get(label, "line")
        self._apply_setting("bar_style", key)
        self._ayar_msg(f"✅ Tarz: {label}")

    def _on_hotkey_toggle_save(self):
        combo = self.hk_toggle_var.get().strip().lower()
        if not combo:
            self._ayar_msg("⚠ Boş olamaz.")
            return
        new = dict(self.parent_bar.settings)
        new["hotkey_toggle"] = combo
        self.parent_bar.apply_settings(new)
        self._ayar_msg(f"✅ Kaydedildi: {combo}")

    def _on_hotkey_show_save(self):
        combo = self.hk_show_var.get().strip().lower()
        if not combo:
            self._ayar_msg("⚠ Boş olamaz.")
            return
        new = dict(self.parent_bar.settings)
        new["hotkey_show"] = combo
        self.parent_bar.apply_settings(new)
        self._ayar_msg(f"✅ Kaydedildi: {combo}")

    def _on_bar_size_change(self, value):
        self._apply_setting("bar_size", value)

    def _on_bar_visible_change(self):
        self._apply_setting("bar_visible", self.bar_visible_var.get())

    def _on_opacity_change(self, value):
        self.lbl_opacity.configure(text=f"{int(value * 100)}%")
        new = dict(self.parent_bar.settings)
        new["bar_opacity"] = round(float(value), 2)
        self.parent_bar.settings.update(new)
        save_settings(self.parent_bar.settings)
        try:
            self.parent_bar.attributes("-alpha", float(value))
        except Exception:
            pass

    def _on_window_size_apply(self):
        try:
            w = int(self.win_w_var.get())
            h = int(self.win_h_var.get())
        except ValueError:
            self._ayar_msg("⚠ Geçersiz sayı.")
            return
        if w < 380 or w > 1200 or h < 500 or h > 1200:
            self._ayar_msg("⚠ 380-1200 arası olmalı.")
            return
        new = dict(self.parent_bar.settings)
        new["window_width"] = w
        new["window_height"] = h
        self.parent_bar.apply_settings(new)
        self._ayar_msg(f"✅ Panel: {w}x{h}")

    def _killswitch_watchdog(self):
        """Her 3 saniyede VPN durumunu kontrol eder."""
        try:
            vpn_active = get_active_tunnel() is not None
            result = self.killswitch.check(vpn_active)

            if result == "vpn_lost":
                notify("NetShield", "VPN kesildi! İnternet kilitlendi.")
                log.warning("NetShield: VPN çöktü, internet kilitlendi")

            elif result == "vpn_connected":
                notify("NetShields", "✓ VPN geri geldi, internet açıldı.")
                log.info("NetShield: VPN geri geldi, internet açıldı")

        except Exception as e:
            log.warning(f"Killswitch watchdog hatası: {e}")

        self.after(3000, self._killswitch_watchdog)

    def _on_killswitch_change(self):
        val = self.killswitch_var.get()
        if val:
            self.killswitch.enable()
            self._ayar_msg("✅ Kill Switch aktif")
        else:
            self.killswitch.disable()
            self._ayar_msg("✅ Kill Switch pasif")

        new = dict(self.parent_bar.settings)
        new["killswitch_enabled"] = val
        self.parent_bar.settings.update(new)
        save_settings(self.parent_bar.settings)

    def _killswitch_panic(self):
        ok = force_unlock()
        self.killswitch._dns_locked = False
        self.killswitch._was_vpn_active = False
        self._ayar_msg("✅ Kilit kaldırıldı" if ok else "⚠ Hata oluştu")

    def _on_startup_change(self):
        if self.startup_var.get():
            ok, msg = startup_enable()
        else:
            ok, msg = startup_disable()
        self._ayar_msg(("✅ " if ok else "⚠ ") + msg)

    # ===== HIZ TESTİ =====
    def _start_speedtest(self):
        from speedtest_manager import run_full_test

        self._speedtest_cancel = threading.Event()
        self.btn_speedtest.configure(state="disabled")
        self.btn_speedtest_cancel.configure(state="normal")
        self.lbl_speed_ping.configure(text="...")
        self.lbl_speed_down.configure(text="...")
        self.lbl_speed_up.configure(text="...")
        self._diag_write("▶ Hız testi başlıyor...")

        def progress_cb(stage, value):
            if stage == "ping":
                self.after(0, lambda: self._diag_write("  📡 Ping ölçülüyor..."))
            elif stage == "download_start":
                self.after(0, lambda: self._diag_write("  ⬇ İndirme hızı ölçülüyor (8 sn)..."))
            elif stage == "download":
                self.after(0, lambda v=value: self.lbl_speed_down.configure(
                    text=f"{v:.1f} Mbps"
                ))
            elif stage == "upload_start":
                self.after(0, lambda: self._diag_write("  ⬆ Yükleme hızı ölçülüyor..."))

        def worker():
            result = run_full_test(
                progress_cb=progress_cb,
                cancel_event=self._speedtest_cancel,
            )
            self.after(0, lambda: self._speedtest_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _speedtest_done(self, result):
        self.btn_speedtest.configure(state="normal")
        self.btn_speedtest_cancel.configure(state="disabled")

        if result.get("ping"):
            self.lbl_speed_ping.configure(text=f"{result['ping']} ms")
            self._diag_write(f"  ✅ Ping: {result['ping']} ms")
        else:
            self.lbl_speed_ping.configure(text="hata")

        if result.get("download"):
            self.lbl_speed_down.configure(text=f"{result['download']:.1f} Mbps")
            self._diag_write(f"  ✅ İndirme: {result['download']:.1f} Mbps")
        else:
            self.lbl_speed_down.configure(text="hata")

        if result.get("upload"):
            self.lbl_speed_up.configure(text=f"{result['upload']:.1f} Mbps")
            self._diag_write(f"  ✅ Yükleme: {result['upload']:.1f} Mbps")
        else:
            self.lbl_speed_up.configure(text="hata")

    def _cancel_speedtest(self):
        if hasattr(self, "_speedtest_cancel"):
            self._speedtest_cancel.set()
            self._diag_write("⏹ Hız testi iptal ediliyor...")

    # ===== LOG GÖRÜNTÜLEYİCİ =====
    def _show_logs(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Uygulama Logları")
        dialog.geometry("700x500")
        dialog.attributes("-topmost", True)
        dialog.configure(fg_color="#18181A")

        ctk.CTkLabel(
            dialog, text="📜 hata.log.txt",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            dialog, text="Konum: hata.log.txt",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 6))

        txt = ctk.CTkTextbox(
            dialog, fg_color="#242428", text_color="#F2F2F7",
            font=ctk.CTkFont(family="Consolas", size=10),
            corner_radius=8, border_width=1, border_color="#2C2C30",
        )
        txt.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        def load_logs():
            from logger import LOG_FILE
            try:
                if LOG_FILE.exists():
                    content = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    if len(lines) > 200:
                        lines = lines[-200:]
                        content = "[... ilk satırlar gizlendi ...]\n\n" + "\n".join(lines)
                else:
                    content = "Log dosyası bulunamadı."
            except Exception as e:
                content = f"Okuma hatası: {e}"

            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("end", content)
            txt.see("end")
            txt.configure(state="disabled")

        def clear_logs():
            from logger import LOG_FILE
            try:
                if LOG_FILE.exists():
                    LOG_FILE.write_text("", encoding="utf-8")
                txt.configure(state="normal")
                txt.delete("1.0", "end")
                txt.insert("end", "Log temizlendi.")
                txt.configure(state="disabled")
            except Exception as e:
                log.error(f"Log temizleme hatası: {e}")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(
            btn_row, text="🔄 Yenile",
            height=30, corner_radius=8, fg_color="#0A84FF",
            hover_color="#007AFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=load_logs,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))

        ctk.CTkButton(
            btn_row, text="🗑️ Logu Temizle",
            height=30, corner_radius=8, fg_color="transparent",
            border_width=1, border_color="#4A1E1E",
            hover_color="#3A1C1C", text_color="#FF453A",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=clear_logs,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

        load_logs()

    # ===== AKILLI MOD SEKMESİ =====
    def _build_tab_akilli(self):
        ctk.CTkLabel(
            self.tab_akilli, text="🎯 Akıllı Mod",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF",
        ).pack(anchor="w", padx=4, pady=(8, 2))

        ctk.CTkLabel(
            self.tab_akilli,
            text="Zapret ve VPN'i otomatik test eder, en iyi olanı bulur ve başlatır.",
            font=ctk.CTkFont(size=10), text_color="#8E8E93",
            anchor="w", justify="left", wraplength=360,
        ).pack(anchor="w", padx=4, pady=(0, 10))

        ctk.CTkLabel(
            self.tab_akilli, text="📦 Test Hedefi:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 2))

        self.akilli_pkg_var = ctk.StringVar(value="Discord")
        ctk.CTkOptionMenu(
            self.tab_akilli, values=list(PACKAGES.keys()),
            variable=self.akilli_pkg_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        ).pack(fill="x", padx=4, pady=(0, 8))

        ctk.CTkLabel(
            self.tab_akilli, text="🔬 Karşılaştırılacaklar:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 4))

        self.chk_zapret = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self.tab_akilli, text="Zapret (DPI Bypass)",
            variable=self.chk_zapret,
            font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
            fg_color="#0A84FF", hover_color="#007AFF",
        ).pack(anchor="w", padx=4, pady=2)

        self.chk_vpn = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            self.tab_akilli, text="VPN (Cloudflare WARP)",
            variable=self.chk_vpn,
            font=ctk.CTkFont(size=11),
            text_color="#F2F2F7",
            fg_color="#0A84FF", hover_color="#007AFF",
        ).pack(anchor="w", padx=4, pady=2)

        ctk.CTkLabel(
            self.tab_akilli, text="🎚️ Her motor için kaç strateji?",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F2F2F7", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        self.akilli_count_var = ctk.StringVar(value="Hızlı (5)")
        ctk.CTkOptionMenu(
            self.tab_akilli,
            values=["Hızlı (5)", "Orta (10)", "Tam (23)"],
            variable=self.akilli_count_var,
            fg_color="#242428", button_color="#0A84FF",
            button_hover_color="#007AFF", dropdown_fg_color="#242428",
            dropdown_hover_color="#2C2C32", text_color="#F2F2F7",
            font=ctk.CTkFont(size=11), dropdown_font=ctk.CTkFont(size=11),
            corner_radius=8, height=28,
        ).pack(fill="x", padx=4, pady=(0, 10))

        self.btn_akilli_start = ctk.CTkButton(
            self.tab_akilli, text="🎯 Karşılaştır ve En İyiyi Seç",
            height=40, corner_radius=10, fg_color="#30D158",
            hover_color="#28B94E",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_akilli,
        )
        self.btn_akilli_start.pack(fill="x", padx=4, pady=(4, 8))

        self.akilli_progress = ctk.CTkProgressBar(
            self.tab_akilli, height=8, corner_radius=4,
            fg_color="#242428", progress_color="#0A84FF",
        )
        self.akilli_progress.pack(fill="x", padx=4, pady=(0, 8))
        self.akilli_progress.set(0)

        self.akilli_result_frame = ctk.CTkFrame(
            self.tab_akilli, fg_color="#1F1F23",
            corner_radius=10, border_width=1, border_color="#2C2C30",
        )

        self.lbl_akilli_result = ctk.CTkLabel(
            self.akilli_result_frame, text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#30D158", anchor="w", justify="left",
            wraplength=360,
        )
        self.lbl_akilli_result.pack(fill="x", padx=12, pady=10)

        self.txt_akilli = ctk.CTkTextbox(
            self.tab_akilli, height=140, corner_radius=10,
            fg_color="#242428", text_color="#F2F2F7",
            font=ctk.CTkFont(family="Consolas", size=10),
            border_width=1, border_color="#2C2C30",
        )
        self.txt_akilli.pack(fill="both", expand=True, padx=4, pady=4)
        self.txt_akilli.insert("end", "Karşılaştırmayı başlatmak için butona bas.\n")
        self.txt_akilli.configure(state="disabled")

    def _akilli_write(self, text):
        self.txt_akilli.configure(state="normal")
        self.txt_akilli.insert("end", text + "\n")
        self.txt_akilli.see("end")
        self.txt_akilli.configure(state="disabled")

    def _start_akilli(self):
        targets = get_targets(self.akilli_pkg_var.get(), "Yok", "")
        if not targets:
            self._akilli_write("⚠ Hedef bulunamadı.")
            return

        use_zapret = self.chk_zapret.get()
        use_vpn = self.chk_vpn.get()

        if not use_zapret and not use_vpn:
            self._akilli_write("⚠ En az bir yöntem seç.")
            return

        val = self.akilli_count_var.get()
        limit = 5 if "5" in val else 10 if "10" in val else 23

        self.btn_akilli_start.configure(state="disabled")
        self.akilli_result_frame.pack_forget()

        self.txt_akilli.configure(state="normal")
        self.txt_akilli.delete("1.0", "end")
        self.txt_akilli.configure(state="disabled")

        self._akilli_write(f"▶ Hedefler: {', '.join(targets)}")
        self._akilli_write(f"▶ Strateji limiti: {limit}")
        self._akilli_write("─" * 40)

        self._akilli_results = {"zapret": [], "vpn": None}

        def worker():
            self.manager.stop()
            self.after(0, lambda: self.parent_bar.set_active_status(False))

            def result_cb(result):
                self._akilli_results["zapret"].append(result)
                self.after(0, lambda: self._akilli_result_line(result))

            if use_zapret:
                self.after(0, lambda: self._akilli_write("\n🔬 ZAPRET testi başlıyor..."))
                run_blockcheck(
                    targets, limit,
                    lambda c, t, m: self.after(0, lambda: self._akilli_write(m)),
                    result_cb,
                    self._test_cancel,
                )

            if use_vpn:
                self.after(0, lambda: self._akilli_write("\n🌐 VPN testi başlıyor..."))
                vpn_result = self._test_vpn(targets)
                self._akilli_results["vpn"] = vpn_result

            self.after(0, self._akilli_done)

        threading.Thread(target=worker, daemon=True).start()

    def _akilli_result_line(self, result):
        if result["success"] > 0:
            self._akilli_write(f"  ✅ {result['name']}: {result['success']}/{result['total']}")
        else:
            self._akilli_write(f"  ❌ {result['name']}: 0/{result['total']}")

    def _test_vpn(self, targets):
        from vpn_manager import (
            list_configs, connect, disconnect, get_active_tunnel,
        )
        from blockcheck import _test_tls

        configs = list_configs()
        if not configs:
            self.after(0, lambda: self._akilli_write("  ⚠ VPN config yok, atlanıyor."))
            return None

        warp_name = None
        for c in configs:
            if "WARP" in c["name"] or "Cloudflare" in c["name"]:
                warp_name = c["name"]
                break
        if not warp_name:
            warp_name = configs[0]["name"]

        self.after(0, lambda: self._akilli_write(f"  → Bağlanıyor: {warp_name}"))

        active = get_active_tunnel()
        if active:
            disconnect(active)

        ok, msg = connect(warp_name)
        if not ok:
            self.after(0, lambda: self._akilli_write(f"  ❌ VPN bağlantı hatası: {msg}"))
            return None

        import time
        time.sleep(3)

        details = []
        success = 0
        for t in targets:
            ok = _test_tls(t, timeout=4.0)
            details.append((t, ok))
            if ok:
                success += 1
            self.after(0, lambda h=t, o=ok: self._akilli_write(
                f"  → {h}: {'✓' if o else '✗'}"
            ))

        disconnect(warp_name)
        time.sleep(1)

        return {
            "name": f"VPN ({warp_name})",
            "success": success,
            "total": len(targets),
            "details": details,
        }

    def _akilli_done(self):
        self.btn_akilli_start.configure(state="normal")
        self.akilli_progress.set(1)

        self._akilli_write("\n" + "─" * 40)
        self._akilli_write("🏆 SONUÇLAR:")

        zapret_best = pick_best(self._akilli_results["zapret"])
        vpn_res = self._akilli_results["vpn"]

        zapret_score = zapret_best["success"] if zapret_best else 0
        vpn_score = vpn_res["success"] if vpn_res else 0

        zapret_total = zapret_best["total"] if zapret_best else 1
        vpn_total = vpn_res["total"] if vpn_res else 1

        if zapret_best:
            self._akilli_write(
                f"  🔬 Zapret: {zapret_best['name']} ({zapret_score}/{zapret_total})"
            )
        else:
            self._akilli_write("  🔬 Zapret: başarısız")

        if vpn_res:
            self._akilli_write(f"  🌐 {vpn_res['name']}: {vpn_score}/{vpn_total}")
        elif self.chk_vpn.get():
            self._akilli_write("  🌐 VPN: başarısız")

        if zapret_score >= vpn_score and zapret_best:
            winner_text = f"🏆 KAZANAN: Zapret → {zapret_best['name']}"
            self.lbl_akilli_result.configure(text=winner_text, text_color="#30D158")

            exe_path = zapret_best["exe"]
            engine_name = "Zapret Lua" if "winws2" in exe_path else "Zapret Classic"
            mode_name = f"🏆 {zapret_best['name']}"
            ENGINES_CONFIG[engine_name]["modes"][mode_name] = zapret_best["args"]

            self.engine_var.set(engine_name)
            self._on_engine_change(engine_name)
            self.strategy_var.set(mode_name)
            save_last_strategy(self.profile, zapret_best, engine_name, mode_name)
            self._refresh_banner()

            self.apply_mode(mode_name)
            self._akilli_write(f"\n✅ {winner_text}")
        elif vpn_res and vpn_score > 0:
            winner_text = f"🏆 KAZANAN: {vpn_res['name']}"
            self.lbl_akilli_result.configure(text=winner_text, text_color="#0A84FF")
            self._akilli_write(f"\n✅ {winner_text}")
            self._akilli_write("   VPN sekmesinden bağlanabilirsiniz.")
        else:
            self.lbl_akilli_result.configure(
                text="⚠ Hiçbir yöntem başarılı olmadı.",
                text_color="#FF453A",
            )
            self._akilli_write("\n⚠ Hiçbir yöntem çalışmadı.")

        self.akilli_result_frame.pack(fill="x", padx=4, pady=(0, 8))

    # ===== İSTATİSTİK =====
    def _start_stats(self, engine_name):
        if not stats_available():
            return
        proc = "winws2.exe" if "Lua" in engine_name else "winws.exe"
        self.stats.start(proc)

        if not self._stats_visible:
            self.stats_frame.pack(fill="x", padx=4, pady=(4, 6))
            self._stats_visible = True

        self._schedule_stats_update()

    def _stop_stats(self):
        self.stats.stop()
        if self._stats_job:
            try:
                self.after_cancel(self._stats_job)
            except Exception:
                pass
            self._stats_job = None
        if self._stats_visible:
            self.stats_frame.pack_forget()
            self._stats_visible = False

    def _schedule_stats_update(self):
        self._update_stats()
        self._stats_job = self.after(2000, self._schedule_stats_update)

    def _update_stats(self):
        try:
            self.lbl_stat_uptime.configure(text=self.stats.get_uptime_str())
            self.lbl_stat_conns.configure(text=str(self.stats.get_active_connections()))
            mem = self.stats.get_memory_mb()
            self.lbl_stat_mem.configure(text=f"{mem:.1f} MB")
            down, up = self.stats.get_net_speed()
            self.lbl_stat_speed.configure(text=f"⬇ {down} MB/s   ⬆ {up} MB/s")
        except Exception as e:
            log.warning(f"İstatistik güncelleme hatası: {e}")

    # ===== ORTAK =====
    def show_message(self, text, is_error=True):
        color = "#FF9F9A" if is_error else "#8E8E93"
        self.lbl_msg.configure(text=text, text_color=color)
        if text:
            self.after(6000, lambda: self.lbl_msg.configure(text=""))

    def apply_mode(self, mode_name):
        self.show_message("")

        active_vpn = get_active_tunnel()
        if active_vpn:
            disconnect(active_vpn)
            self._refresh_vpn_status()

        engine_name = self.engine_var.get()
        success = self.manager.start_mode(engine_name, mode_name)

        if mode_name == MODE_IDLE or not success:
            self.status_pill.configure(fg_color="#261A1A")
            self.lbl_status.configure(
                text="● Servis Kapalı", text_color="#FF453A",
            )
            self.parent_bar.set_active_status(False)
            if self.tray:
                self.tray.set_active(False)
            self._stop_stats()
            if mode_name != MODE_IDLE and not success:
                self.show_message(
                    "⚠ Motor başlatılamadı. hata.log.txt'yi kontrol edin."
                )
        else:
            self.status_pill.configure(fg_color="#1A261C")
            self.lbl_status.configure(
                text=f"● Aktif: {engine_name} / {mode_name}",
                text_color="#30D158",
            )
            self.parent_bar.set_active_status(True)
            if self.tray:
                self.tray.set_active(True)
            self._start_stats(engine_name)
            notify("NetShield", f"Aktif: {engine_name} / {mode_name}")


class MacStyleHandleBar(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.manager = DPIEngineManager()
        self.settings = load_settings()

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#000001")

        try:
            self.wm_attributes("-transparentcolor", "#000001")
        except Exception:
            pass

        self._build_bar()

        self.dashboard = MainDashboard(self, self.manager)

        self.tray = TrayManager(
            on_show=self._tray_show,
            on_toggle_bypass=self._tray_toggle,
            on_quit=self._tray_quit,
        )
        self.tray.start()
        self.dashboard.tray = self.tray

        self.tray.set_active(self.manager.is_running())

        # Global kısayollar
        self.hotkeys = HotkeyManager()
        self._register_hotkeys()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.after(200, lambda: _hide_from_taskbar(self))

    # ----- Kısayol -----
    def _register_hotkeys(self):
        if not hotkey_available():
            return
        self.hotkeys.unregister_all()
        tog = self.settings.get("hotkey_toggle", "ctrl+shift+b")
        shw = self.settings.get("hotkey_show", "ctrl+shift+p")
        if tog:
            self.hotkeys.register(tog, self._hotkey_toggle, "Bypass Aç/Kapat")
        if shw:
            self.hotkeys.register(shw, self._hotkey_show, "Paneli Aç")

    def _hotkey_toggle(self):
        self.after(0, self._tray_toggle_main)

    def _hotkey_show(self):
        self.after(0, self._tray_show_main)

    # ----- Tray -----
    def _tray_show(self):
        self.after(0, self._tray_show_main)

    def _tray_show_main(self):
        dw = self.settings.get("window_width", 520)
        dh = self.settings.get("window_height", 800)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = int((sw - dw) / 2)
        y = int((sh - dh) / 2)
        self.dashboard.geometry(f"{dw}x{dh}+{x}+{y}")
        self.dashboard.deiconify()
        self.dashboard.attributes("-topmost", True)
        self.dashboard.lift()
        self.dashboard.focus_force()
        self.after(50, lambda: _hide_from_taskbar(self.dashboard))

    def _tray_toggle(self):
        self.after(0, self._tray_toggle_main)

    def _tray_toggle_main(self):
        if self.manager.is_running():
            self.dashboard.apply_mode("Boşta")
        else:
            self.dashboard.apply_mode(self.dashboard.strategy_var.get())

    def _tray_quit(self):
        self.after(0, self.exit_application)

    def _on_window_close(self):
        self.exit_application()

    # ----- Bar -----
    def _build_bar(self):
        if hasattr(self, "line_btn") and self.line_btn is not None:
            try:
                self.line_btn.destroy()
            except Exception:
                pass

        style = self.settings.get("bar_style", "line")
        size = self.settings.get("bar_size", "medium")
        cfg = get_bar_style_config(style, size)

        win_w = cfg["win_w"]
        win_h = cfg["win_h"]

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        position = self.settings.get("bar_position", "bottom_center")
        x, y = calc_position(position, win_w, win_h, sw, sh)

        # tray_only modunda bar penceresini tamamen gizle
        if style == "tray_only" or not self.settings.get("bar_visible", True):
            self.withdraw()
            return

        # Görünür yap
        self.deiconify()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.lift()

        # Buton
        if style == "dot":
            btn_text = "●"
            btn_font = ctk.CTkFont(size=12, weight="bold")
            btn_fg = "#55555A"
        elif style == "button":
            btn_text = "🛡️ Bypass"
            btn_font = ctk.CTkFont(size=11, weight="bold")
            btn_fg = "#55555A"
        else:
            btn_text = ""
            btn_font = ctk.CTkFont(size=10)
            btn_fg = "#55555A"

        self.line_btn = ctk.CTkButton(
            self, text=btn_text,
            width=cfg["btn_w"], height=cfg["btn_h"],
            corner_radius=cfg["radius"],
            font=btn_font,
            text_color="#F2F2F7",
            fg_color=btn_fg, hover_color="#0A84FF",
            command=self.toggle_dashboard,
        )
        self.line_btn.place(relx=0.5, rely=0.5, anchor="center")

        if self.manager.is_running():
            self.line_btn.configure(fg_color="#30D158")

        try:
            self.attributes("-alpha", float(self.settings.get("bar_opacity", 0.9)))
        except Exception:
            pass

    def apply_settings(self, new_settings):
        self.settings.update(new_settings)
        save_settings(self.settings)
        self._build_bar()
        # Kısayollar değiştiyse yeniden kaydet
        self._register_hotkeys()

    def set_active_status(self, active: bool):
        color = "#30D158" if active else "#55555A"
        try:
            self.line_btn.configure(fg_color=color)
        except Exception:
            pass

    def toggle_dashboard(self):
        if self.dashboard.winfo_viewable():
            self.dashboard.withdraw()
        else:
            self._tray_show_main()

    def exit_application(self):
        log.info("Uygulama kapatılıyor...")
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        self.manager.stop()
        self.destroy()


if __name__ == "__main__":
    if not is_admin():
        log.warning("Yönetici yetkisi yok, UAC ile yeniden başlatılıyor.")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{sys.argv[0]}"', script_dir, 1
        )
        sys.exit(0)
    else:
        app = MacStyleHandleBar()
        app.mainloop()