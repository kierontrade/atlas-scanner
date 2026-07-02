"""
ATLAS Desktop GUI

Koyu temalı masaüstü arayüz (CustomTkinter).

    - Tek tarama / sürekli mod başlat-durdur
    - READY trade card'ları (BingX'e elle girilecek plan)
    - WATCH / WAIT listeleri
    - Journal istatistikleri
    - Yeni READY çıkınca sesli uyarı

EXE derleme: build_exe.bat  (PyInstaller)
Çalıştırma:  python gui.py
"""

import io
import logging
import sys
import threading
import time
from pathlib import Path

# PyInstaller --windowed modunda stdout/stderr None olur;
# run_scan içindeki print'lerin patlamaması için güvenli tampon bağlanır.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

import customtkinter as ctk

from config.settings import (
    RISK_PER_TRADE,
    SCAN_INTERVAL_MINUTES,
)
from config.user_config import get_balance, get_scan_mode, save_user_config
from main import alert_sound, format_trade_card, run_scan


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

STATUS_COLORS = {
    "idle": "#8a8a8a",
    "scanning": "#e6b800",
    "ready": "#2ecc71",
    "error": "#e74c3c",
}


def setup_gui_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(log_dir / "atlas.log", encoding="utf-8")],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def format_candidate_block(item):
    """WATCH/WAIT adayı için detaylı görünüm."""
    direction = item.get("trade_direction") or item.get("trend_direction")
    side = "LONG" if direction == "BULLISH" else "SHORT" if direction == "BEARISH" else "-"

    tp_levels = item.get("plan_tp_levels") or []
    tp_parts = [str(level["price"]) for level in tp_levels]

    while len(tp_parts) < 3:
        tp_parts.append("-")

    lines = [
        (
            f"{item.get('symbol', '-'):<14} {side:<6}"
            f" Atlas: {str(item.get('atlas_score', '-')):<7}"
            f" Seq: {str(item.get('entry_sequence_state', '-')):<18}"
            f" Trigger: {item.get('trigger_status', '-')}"
        ),
        f"    Şu anki fiyat : {item.get('current_price', '-')}",
        (
            f"    Hedef Entry   : {item.get('entry', '-')}"
            f"    (uzaklık %{item.get('entry_distance_percent', '-')})"
        ),
        f"    Stop Loss     : {item.get('stop', '-')}",
        f"    TP1 / TP2 / TP3: {tp_parts[0]}  /  {tp_parts[1]}  /  {tp_parts[2]}",
        (
            f"    RR: {item.get('rr', '-')}"
            f"  |  Zamanlama: {item.get('timing_advice', '-')}"
        ),
        "",
    ]

    return "\n".join(lines)


class AtlasApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("KieronTradeEngine — SMC Trade Intelligence")
        self.geometry("1150x720")
        self.minsize(950, 600)

        self.scan_thread = None
        self.loop_active = False
        self.stop_requested = threading.Event()
        self.alerted_setups = set()
        self.next_scan_at = None

        self._build_layout()
        self._tick_countdown()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        header = ctk.CTkFrame(self, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)

        title = ctk.CTkLabel(
            header,
            text="  KieronTradeEngine",
            font=ctk.CTkFont(size=26, weight="bold"),
        )
        title.pack(side="left", padx=(15, 5), pady=12)

        subtitle = ctk.CTkLabel(
            header,
            text="SMC V5 / Entry Sequence V1",
            font=ctk.CTkFont(size=13),
            text_color="#8a8a8a",
        )
        subtitle.pack(side="left", padx=5)

        self.scan_button = ctk.CTkButton(
            header,
            text="▶  Tek Tarama",
            width=130,
            command=self.start_single_scan,
        )
        self.scan_button.pack(side="right", padx=(5, 15), pady=12)

        self.loop_button = ctk.CTkButton(
            header,
            text=f"♻  Sürekli Mod ({SCAN_INTERVAL_MINUTES} dk)",
            width=180,
            fg_color="#1f6f43",
            hover_color="#17532f",
            command=self.toggle_loop,
        )
        self.loop_button.pack(side="right", padx=5, pady=12)

        status_bar = ctk.CTkFrame(self, corner_radius=0, height=36)
        status_bar.pack(fill="x")

        self.status_label = ctk.CTkLabel(
            status_bar,
            text="● Hazır — tarama bekleniyor",
            text_color=STATUS_COLORS["idle"],
            font=ctk.CTkFont(size=13),
        )
        self.status_label.pack(side="left", padx=15, pady=6)

        self.session_label = ctk.CTkLabel(
            status_bar,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#8a8a8a",
        )
        self.session_label.pack(side="left", padx=15)

        self.countdown_label = ctk.CTkLabel(
            status_bar,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#8a8a8a",
        )
        self.countdown_label.pack(side="right", padx=15)

        # --- Ayar çubuğu: bakiye + tarama modu ---
        settings_bar = ctk.CTkFrame(self, corner_radius=0, height=42)
        settings_bar.pack(fill="x")

        balance_label = ctk.CTkLabel(
            settings_bar,
            text=f"Bakiye (USDT) — risk %{RISK_PER_TRADE}:",
            font=ctk.CTkFont(size=13),
        )
        balance_label.pack(side="left", padx=(15, 5), pady=8)

        self.balance_entry = ctk.CTkEntry(settings_bar, width=110)
        self.balance_entry.insert(0, f"{get_balance():g}")
        self.balance_entry.pack(side="left", padx=5, pady=8)

        self.balance_save_button = ctk.CTkButton(
            settings_bar,
            text="💾 Kaydet",
            width=90,
            command=self.save_balance,
        )
        self.balance_save_button.pack(side="left", padx=5, pady=8)

        self.balance_status = ctk.CTkLabel(
            settings_bar,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#2ecc71",
        )
        self.balance_status.pack(side="left", padx=10)

        mode_label = ctk.CTkLabel(
            settings_bar,
            text="Tarama modu:",
            font=ctk.CTkFont(size=13),
        )
        mode_label.pack(side="left", padx=(30, 5))

        self.mode_selector = ctk.CTkSegmentedButton(
            settings_bar,
            values=["Esnek (çok sinyal)", "Sıkı (sniper)"],
            command=self.change_mode,
        )
        self.mode_selector.set(
            "Sıkı (sniper)" if get_scan_mode() == "STRICT" else "Esnek (çok sinyal)"
        )
        self.mode_selector.pack(side="left", padx=5, pady=8)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        for name in ("🟢 READY", "🟡 WATCH", "⚪ WAIT", "📊 İstatistik"):
            self.tabs.add(name)

        self.ready_box = self._make_textbox(self.tabs.tab("🟢 READY"))
        self.watch_box = self._make_textbox(self.tabs.tab("🟡 WATCH"))
        self.wait_box = self._make_textbox(self.tabs.tab("⚪ WAIT"))
        self.stats_box = self._make_textbox(self.tabs.tab("📊 İstatistik"))

        self.ready_box.insert(
            "1.0",
            "Henüz tarama yapılmadı.\n\n"
            "READY sinyali geldiğinde burada BingX'e girilecek hazır işlem planı\n"
            "(Entry / Stop / TP1-TP3 / miktar / kaldıraç) görünecek.",
        )

    def _make_textbox(self, parent):
        box = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="none",
        )
        box.pack(fill="both", expand=True, padx=5, pady=5)
        return box

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def save_balance(self):
        raw = self.balance_entry.get().strip().replace(",", ".")

        try:
            balance = float(raw)

            if balance <= 0:
                raise ValueError
        except ValueError:
            self.balance_status.configure(
                text="Geçersiz değer!", text_color="#e74c3c"
            )
            return

        save_user_config(balance_usdt=balance)
        self.balance_status.configure(
            text=f"✓ {balance:g} USDT kaydedildi — sonraki taramadan itibaren geçerli",
            text_color="#2ecc71",
        )

    def change_mode(self, selection):
        mode = "STRICT" if "Sıkı" in selection else "FLEXIBLE"
        save_user_config(scan_mode=mode)
        self.balance_status.configure(
            text=f"✓ Mod: {'Sıkı' if mode == 'STRICT' else 'Esnek'} — sonraki taramadan itibaren geçerli",
            text_color="#2ecc71",
        )

    # ------------------------------------------------------------------
    # Scan control
    # ------------------------------------------------------------------

    def start_single_scan(self):
        if self.scan_thread and self.scan_thread.is_alive():
            return

        self.scan_thread = threading.Thread(target=self._scan_once, daemon=True)
        self.scan_thread.start()

    def toggle_loop(self):
        if self.loop_active:
            self.loop_active = False
            self.stop_requested.set()
            self.loop_button.configure(
                text=f"♻  Sürekli Mod ({SCAN_INTERVAL_MINUTES} dk)",
                fg_color="#1f6f43",
                hover_color="#17532f",
            )
            self.next_scan_at = None
            self._set_status("Sürekli mod durduruldu", "idle")
            return

        if self.scan_thread and self.scan_thread.is_alive():
            return

        self.loop_active = True
        self.stop_requested.clear()
        self.loop_button.configure(
            text="■  Durdur",
            fg_color="#8f2f2f",
            hover_color="#6e2424",
        )
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()

    def _scan_once(self):
        self._run_and_render()

    def _scan_loop(self):
        while self.loop_active and not self.stop_requested.is_set():
            self._run_and_render()

            if not self.loop_active:
                break

            self.next_scan_at = time.time() + SCAN_INTERVAL_MINUTES * 60

            if self.stop_requested.wait(timeout=SCAN_INTERVAL_MINUTES * 60):
                break

        self.next_scan_at = None

    def _run_and_render(self):
        self.after(0, self._set_status, "Tarama sürüyor... (1-2 dk)", "scanning")

        try:
            results = run_scan(self.alerted_setups)
        except Exception:
            logging.getLogger("atlas").exception("GUI taramasında hata")
            results = None

        if results is None:
            self.after(0, self._set_status, "Hata — logs/atlas.log'a bak", "error")
            return

        self.after(0, self._render_results, results)

    # ------------------------------------------------------------------
    # Rendering (main thread)
    # ------------------------------------------------------------------

    def _set_status(self, text, color_key):
        self.status_label.configure(
            text=f"● {text}",
            text_color=STATUS_COLORS[color_key],
        )

    def _render_results(self, results):
        session = results["session"]
        ready = results["ready"]
        watch = results["watch"]
        wait = results["wait"]

        self.session_label.configure(
            text=(
                f"Session: {session['session_name']} (UTC {session['utc_hour']}:00) — "
                f"{session['session_reason']}"
            )
        )

        now = time.strftime("%H:%M:%S")

        if ready:
            self._set_status(
                f"{len(ready)} READY sinyali var!  (son tarama {now})", "ready"
            )
        else:
            self._set_status(
                f"READY yok — {len(watch)} WATCH izleniyor  (son tarama {now})", "idle"
            )

        self.ready_box.delete("1.0", "end")

        if ready:
            cards = "\n\n".join(format_trade_card(item) for item in ready)
            self.ready_box.insert("1.0", cards)
        else:
            self.ready_box.insert(
                "1.0",
                "Şu an READY sinyal yok.\n\n"
                "Bu normaldir — sistem sadece sweep sonrası onaylı, yüksek\n"
                "confluence'lı fırsatları READY yapar. WATCH sekmesindeki\n"
                "adaylar sıradaki adaylardır.",
            )

        self.watch_box.delete("1.0", "end")
        self.watch_box.insert(
            "1.0",
            "\n".join(format_candidate_block(item) for item in watch) or "WATCH adayı yok.",
        )

        self.wait_box.delete("1.0", "end")
        self.wait_box.insert(
            "1.0",
            "\n".join(format_candidate_block(item) for item in wait) or "WAIT adayı yok.",
        )

        stats = results.get("stats") or {}
        outcome_stats = results.get("outcome_stats") or []

        stats_lines = [
            f"Son tarama         : {now}",
            f"Toplam futures     : {stats.get('total_futures', '-')}",
            f"USDT futures       : {stats.get('usdt_futures', '-')}",
            f"Market cap eşleşen : {stats.get('matched', '-')}",
            f"Hard filter geçen  : {stats.get('passed', '-')}",
            f"READY / WATCH / WAIT: {len(ready)} / {len(watch)} / {len(wait)}",
            "",
            "Journal — sequence bazlı gerçek başarı oranları:",
        ]

        if outcome_stats:
            for stat in outcome_stats:
                stats_lines.append(
                    f"  {stat['sequence_state'] or 'UNKNOWN':<20}"
                    f" %{stat['win_rate_percent']}"
                    f"  ({stat['wins']}W / {stat['losses']}L)"
                )
        else:
            stats_lines.append("  Henüz sonuçlanmış setup yok — veri birikiyor.")

        self.stats_box.delete("1.0", "end")
        self.stats_box.insert("1.0", "\n".join(stats_lines))

        if results.get("new_ready"):
            threading.Thread(target=alert_sound, daemon=True).start()

    def _tick_countdown(self):
        if self.next_scan_at:
            remaining = int(self.next_scan_at - time.time())

            if remaining > 0:
                minutes, seconds = divmod(remaining, 60)
                self.countdown_label.configure(
                    text=f"Sonraki tarama: {minutes:02d}:{seconds:02d}"
                )
            else:
                self.countdown_label.configure(text="Tarama başlıyor...")
        else:
            self.countdown_label.configure(text="")

        self.after(1000, self._tick_countdown)


def main():
    setup_gui_logging()
    app = AtlasApp()
    app.mainloop()


if __name__ == "__main__":
    main()
