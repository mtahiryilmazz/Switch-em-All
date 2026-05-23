from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import requests
except Exception:  # pragma: no cover - shown in the GUI at runtime
    requests = None


APP_TITLE = "Switch'em All"
USER_AGENT = "Emulator-Finder-Downloader-X3"

THEMES: dict[str, dict[str, str | int]] = {
    "Midnight Black": {
        "app_bg": "#000000",
        "panel_bg": "#050505",
        "surface_bg": "#0a0a0a",
        "surface_alt": "#151515",
        "text": "#f7f7f7",
        "muted": "#8a8f98",
        "accent": "#a855f7",
        "success": "#22c55e",
        "button": "#111111",
        "button_hover": "#202020",
        "log_bg": "#000000",
        "log_text": "#e5e7eb",
        "rowheight": 26,
        "pad": 10,
    },
    "Code Dark": {
        "app_bg": "#181a1f",
        "panel_bg": "#20242b",
        "surface_bg": "#282d35",
        "surface_alt": "#343b46",
        "text": "#d7dae0",
        "muted": "#9aa4b2",
        "accent": "#3794ff",
        "success": "#89d185",
        "button": "#303743",
        "button_hover": "#3d4654",
        "log_bg": "#16191e",
        "log_text": "#cbd5e1",
        "rowheight": 25,
        "pad": 10,
    },
    "Code Light": {
        "app_bg": "#f3f3f3",
        "panel_bg": "#ffffff",
        "surface_bg": "#ffffff",
        "surface_alt": "#e8e8e8",
        "text": "#1f1f1f",
        "muted": "#616161",
        "accent": "#006ab1",
        "success": "#16825d",
        "button": "#e5e5e5",
        "button_hover": "#d4d4d4",
        "log_bg": "#ffffff",
        "log_text": "#1f1f1f",
        "rowheight": 24,
        "pad": 8,
    },
}

THEME_ALIASES = {
    "Modern": "Code Dark",
    "Minimal": "Code Light",
    "Klasik": "Code Dark",
    "Black": "Midnight Black",
    "Dark": "Midnight Black",
    "Gray/Dark": "Code Dark",
    "Light": "Code Light",
}

LAYOUTS = ("Modern Sekmeli", "Minimal Sekmeli", "Klasik Sekmeli")


@dataclass
class SourceResult:
    name: str
    channel: str
    version: str
    date: str
    file_name: str
    source_type: str
    page_url: str
    download_url: str
    raw: dict[str, Any]


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Any,
        bg: str,
        fg: str = "#ffffff",
        hover_bg: str | None = None,
        padx: int = 12,
        pady: int = 7,
        font: tuple[str, int, str] = ("Segoe UI", 9, "bold"),
    ) -> None:
        self.text = text
        self.command = command
        self.fill = bg
        self.normal_fill = bg
        self.hover_fill = hover_bg or bg
        self.fg = fg
        self.padx = padx
        self.pady = pady
        self.font_value = font
        self.canvas_bg = parent.cget("bg")
        width = max(74, len(text) * 8 + padx * 2)
        height = max(28, font[1] + pady * 2 + 8)
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, bg=self.canvas_bg, relief="flat")
        self.bind("<Button-1>", lambda event: self.command())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.draw()

    def _on_enter(self, event: tk.Event) -> None:
        self.fill = self.hover_fill
        self.draw()

    def _on_leave(self, event: tk.Event) -> None:
        self.fill = self.normal_fill
        self.draw()

    def configure(self, cnf: Any = None, **kwargs: Any) -> None:  # type: ignore[override]
        if "bg" in kwargs:
            self.normal_fill = kwargs.pop("bg")
            self.fill = self.normal_fill
        if "activebackground" in kwargs:
            self.hover_fill = kwargs.pop("activebackground")
        if "fg" in kwargs:
            self.fg = kwargs.pop("fg")
        if "activeforeground" in kwargs:
            kwargs.pop("activeforeground")
        if "padx" in kwargs:
            self.padx = int(kwargs.pop("padx"))
        if "pady" in kwargs:
            self.pady = int(kwargs.pop("pady"))
        if "font" in kwargs:
            self.font_value = kwargs.pop("font")
        if "text" in kwargs:
            self.text = kwargs.pop("text")
        if "canvas_bg" in kwargs:
            self.canvas_bg = kwargs.pop("canvas_bg")
            tk.Canvas.configure(self, bg=self.canvas_bg)
        if kwargs:
            super().configure(cnf, **kwargs)
        self.draw()

    config = configure

    def draw(self) -> None:
        self.delete("all")
        width = max(74, len(self.text) * 8 + self.padx * 2)
        height = max(28, self.font_value[1] + self.pady * 2 + 8)
        self.configure_canvas_size(width, height)
        radius = min(16, height // 2)
        points = (
            radius, 1,
            width - radius, 1,
            width - 1, 1,
            width - 1, radius,
            width - 1, height - radius,
            width - 1, height - 1,
            width - radius, height - 1,
            radius, height - 1,
            1, height - 1,
            1, height - radius,
            1, radius,
            1, 1,
        )
        self.create_polygon(points, smooth=True, splinesteps=20, fill=self.fill, outline=self.fill)
        self.create_text(width // 2, height // 2, text=self.text, fill=self.fg, font=self.font_value)

    def configure_canvas_size(self, width: int, height: int) -> None:
        tk.Canvas.configure(self, width=width, height=height)


class SwitchDownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1240x780")
        self.minsize(980, 620)

        self.root_path = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        self.config_dir = self.root_path / "config"
        self.download_dir = self.root_path / "downloads"
        self.log_dir = self.root_path / "logs"
        self.config_dir.mkdir(exist_ok=True)
        self.download_dir.mkdir(exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)

        self.log_file = self.log_dir / f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        ui_settings = self.load_ui_settings()
        self.theme_name = ui_settings["theme"]
        self.layout_name = ui_settings["layout"]
        self.theme = THEMES[self.theme_name]
        self.page_urls: dict[str, str] = {}
        self.download_urls: dict[str, str] = {}
        self.latest_scraped_versions: dict[str, dict[str, Any]] = {}
        self.nav_buttons: list[tk.Button] = []
        self.action_buttons: list[tk.Button] = []
        self.tab_specs: list[tuple[str, tk.Widget, str]] = []
        self.tab_hitboxes: list[tuple[int, int, tk.Widget]] = []

        self.sources: list[dict[str, Any]] = []
        self.firmware_sources: list[dict[str, Any]] = []
        self.keys_sources: list[dict[str, Any]] = []
        self.local_sources: list[dict[str, Any]] = []

        self.load_sources()
        self.setup_ui()
        self.refresh_local_table()
        self.update_optimizations_emu_list()
        self.write_log("Uygulama başlatıldı.")

    def setup_ui(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.default_tab_layout = self.style.layout("TNotebook.Tab")
        self.configure_ttk_style()

        self.header = tk.Frame(self, bg="#101319")
        self.header.pack(fill="x", padx=16, pady=(14, 8))
        title_area = tk.Frame(self.header, bg="#101319")
        title_area.pack(side="left", fill="x", expand=True)
        self.title_label = tk.Label(
            title_area,
            text=APP_TITLE,
            bg="#101319",
            fg="#ffffff",
            font=("Segoe UI", 20, "bold"),
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(
            title_area,
            text="Emulator sürümleri, firmware paketleri ve kendi tanımlı kaynaklarınızı tarayın; yerel kurulumları yedekleyip güncelleyin.",
            bg="#101319",
            fg="#a0a0a0",
            font=("Segoe UI", 10),
        )
        self.subtitle_label.pack(anchor="w", pady=(4, 0))

        switch_area = tk.Frame(self.header, bg="#101319")
        switch_area.pack(side="right", anchor="ne")
        tk.Label(switch_area, text="Arayüz", bg="#101319", fg="#a0a0a0", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="e", padx=(0, 8))
        tk.Label(switch_area, text="Tema", bg="#101319", fg="#a0a0a0", font=("Segoe UI", 9)).grid(row=0, column=1, sticky="e")
        self.cmb_layout = ttk.Combobox(switch_area, values=LAYOUTS, width=15, state="readonly")
        self.cmb_layout.set(self.layout_name)
        self.cmb_layout.grid(row=1, column=0, sticky="e", padx=(0, 8), pady=(3, 0))
        self.cmb_layout.bind("<<ComboboxSelected>>", self.on_layout_change)
        self.cmb_theme = ttk.Combobox(switch_area, values=tuple(THEMES.keys()), width=12, state="readonly")
        self.cmb_theme.set(self.theme_name)
        self.cmb_theme.grid(row=1, column=1, sticky="e", pady=(3, 0))
        self.cmb_theme.bind("<<ComboboxSelected>>", self.on_theme_change)

        self.main_area = tk.Frame(self, bg="#101319")
        self.main_area.pack(fill="both", expand=True, padx=16, pady=8)
        self.tabbar_outer = tk.Frame(self.main_area, bg="#151922")
        self.tabbar = tk.Frame(self.tabbar_outer, bg="#151922")
        self.tab_canvas = tk.Canvas(self.tabbar_outer, height=58, highlightthickness=0, bd=0)
        self.tab_canvas.bind("<Configure>", lambda event: self.draw_modern_tabbar())
        self.tab_canvas.bind("<Button-1>", self.on_modern_tab_click)
        self.notebook = ttk.Notebook(self.main_area, style="App.TNotebook")
        self.tabbar_outer.pack(fill="x", pady=(0, 10))
        self.tabbar.pack(anchor="center")
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda event: self.refresh_after_tab_change())

        self.tab_emulators = self.make_tab("Emülatörler")
        self.tab_firmware = self.make_tab("Firmware")
        self.tab_keys = self.make_tab("Prod Keys")
        self.tab_local = self.make_tab("Yerel Emülatörler")
        self.tab_optimizations = self.make_tab("Optimizasyonlar & Modlar")

        self.build_tabbar()

        self.build_emulator_tab()
        self.build_firmware_tab()
        self.build_keys_tab()
        self.build_local_tab()
        self.build_optimizations_tab()

        self.footer = tk.Frame(self, bg="#101319")
        self.footer.pack(fill="x", padx=16, pady=(4, 12))
        self.lbl_status = tk.Label(
            self.footer,
            text="Hazır",
            anchor="w",
            bg="#101319",
            fg="#2ecc71",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_status.pack(fill="x")
        self.txt_log = tk.Text(
            self.footer,
            height=7,
            bg="#0e1013",
            fg="#c8cdd5",
            insertbackground="#ffffff",
            font=("Consolas", 9),
            relief="flat",
        )
        self.txt_log.pack(fill="x", pady=(6, 0))
        self.txt_log.configure(state="disabled")
        self.apply_theme()
        self.apply_layout()

    def build_tabbar(self) -> None:
        self.tab_specs = (
            ("Emülatörler", self.tab_emulators, "chip"),
            ("Firmware", self.tab_firmware, "stack"),
            ("Prod Keys", self.tab_keys, "key"),
            ("Yerel", self.tab_local, "folder"),
            ("Optimizasyon", self.tab_optimizations, "sliders"),
        )
        for text, tab, _ in self.tab_specs:
            btn = self.button(self.tabbar, text, lambda target=tab: self.select_tab(target))
            btn._target_tab = str(tab)
            btn.pack(side="left", padx=(0 if not self.nav_buttons else 6, 0), pady=6)
            self.nav_buttons.append(btn)

    def select_tab(self, tab: tk.Widget) -> None:
        self.notebook.select(tab)
        self.refresh_after_tab_change()

    def refresh_after_tab_change(self) -> None:
        if self.layout_name == "Modern Sekmeli":
            self.draw_modern_tabbar()
            self.after(25, self.draw_modern_tabbar)
        else:
            self.apply_tab_button_style()

    def on_modern_tab_click(self, event: tk.Event) -> None:
        for left, right, tab in self.tab_hitboxes:
            if left <= event.x <= right:
                self.notebook.select(tab)
                self.draw_modern_tabbar()
                self.after(25, self.draw_modern_tabbar)
                return

    def rounded_rect(self, canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs: Any) -> None:
        radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
        points = (
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        )
        canvas.create_polygon(points, smooth=True, splinesteps=20, **kwargs)

    def draw_tab_icon(self, canvas: tk.Canvas, kind: str, x: int, y: int, color: str) -> None:
        if kind == "chip":
            canvas.create_rectangle(x, y, x + 14, y + 14, outline=color, width=2)
            for off in (3, 7, 11):
                canvas.create_line(x - 3, y + off, x, y + off, fill=color, width=1)
                canvas.create_line(x + 14, y + off, x + 17, y + off, fill=color, width=1)
        elif kind == "stack":
            canvas.create_rectangle(x, y + 2, x + 16, y + 13, outline=color, width=2)
            canvas.create_line(x + 3, y - 1, x + 19, y - 1, fill=color, width=2)
            canvas.create_line(x + 3, y + 16, x + 19, y + 16, fill=color, width=2)
        elif kind == "key":
            canvas.create_oval(x, y + 3, x + 8, y + 11, outline=color, width=2)
            canvas.create_line(x + 8, y + 7, x + 18, y + 7, fill=color, width=2)
            canvas.create_line(x + 15, y + 7, x + 15, y + 11, fill=color, width=2)
        elif kind == "folder":
            canvas.create_line(x, y + 5, x + 6, y + 5, x + 8, y + 2, x + 17, y + 2, x + 17, y + 15, x, y + 15, x, y + 5, fill=color, width=2)
        else:
            for off in (2, 8, 14):
                canvas.create_line(x, y + off, x + 18, y + off, fill=color, width=2)
            canvas.create_oval(x + 4, y, x + 8, y + 4, fill=color, outline=color)
            canvas.create_oval(x + 11, y + 6, x + 15, y + 10, fill=color, outline=color)
            canvas.create_oval(x + 7, y + 12, x + 11, y + 16, fill=color, outline=color)

    def draw_modern_tabbar(self) -> None:
        if not hasattr(self, "tab_canvas") or self.layout_name != "Modern Sekmeli":
            return
        c = self.theme
        canvas = self.tab_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 600)
        canvas.configure(bg=c["panel_bg"])
        tab_widths = [max(112, len(text) * 8 + 52) for text, _, _ in self.tab_specs]
        gap = 8
        total = sum(tab_widths) + gap * (len(tab_widths) - 1) + 14
        start = max(8, (width - total) // 2)
        y1, y2 = 7, 51
        self.rounded_rect(canvas, start, y1, start + total, y2, 22, fill=c["surface_alt"], outline=c["surface_alt"])
        x = start + 7
        current = self.notebook.select()
        self.tab_hitboxes = []
        for (text, tab, icon), tab_w in zip(self.tab_specs, tab_widths):
            selected = str(tab) == current
            fill = c["accent"] if selected else c["surface_alt"]
            text_color = "#ffffff" if selected else c["text"]
            icon_color = "#ffffff" if selected else c["muted"]
            self.rounded_rect(canvas, x, y1 + 5, x + tab_w, y2 - 5, 18, fill=fill, outline=fill)
            self.draw_tab_icon(canvas, icon, x + 16, y1 + 16, icon_color)
            canvas.create_text(x + 42, (y1 + y2) // 2, text=text, anchor="w", fill=text_color, font=("Segoe UI", 9, "bold"))
            self.tab_hitboxes.append((x, x + tab_w, tab))
            x += tab_w + gap

    def load_ui_settings(self) -> dict[str, str]:
        path = self.config_dir / "ui_settings.json"
        settings = {"theme": "Code Dark", "layout": "Modern Sekmeli"}
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                saved_theme = THEME_ALIASES.get(data.get("theme"), data.get("theme"))
                if saved_theme in THEMES:
                    settings["theme"] = saved_theme
                saved_layout = data.get("layout")
                if saved_layout == "Modern Panel":
                    saved_layout = "Modern Sekmeli"
                elif saved_layout == "Minimal Panel":
                    saved_layout = "Minimal Sekmeli"
                if saved_layout in LAYOUTS:
                    settings["layout"] = saved_layout
        except Exception:
            pass
        if settings["theme"] not in THEMES:
            settings["theme"] = "Code Dark"
        return settings

    def save_ui_settings(self) -> None:
        try:
            with (self.config_dir / "ui_settings.json").open("w", encoding="utf-8") as handle:
                json.dump({"theme": self.theme_name, "layout": self.layout_name}, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.write_log(f"Arayüz ayarı kaydedilemedi: {exc}", "ERROR")

    def configure_ttk_style(self) -> None:
        c = self.theme
        self.style.configure(
            "Treeview",
            background=c["surface_bg"],
            foreground=c["text"],
            fieldbackground=c["surface_bg"],
            rowheight=int(c["rowheight"]),
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        self.style.map("Treeview", background=[("selected", c["accent"])], foreground=[("selected", "#ffffff")])
        self.style.configure(
            "Treeview.Heading",
            background=c["surface_alt"],
            foreground=c["text"],
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        self.style.configure("TNotebook", background=c["app_bg"], borderwidth=0)
        self.style.configure("TNotebook.Tab", padding=(14, 7), font=("Segoe UI", 9), background=c["surface_alt"], foreground=c["text"])
        self.style.map("TNotebook.Tab", background=[("selected", c["panel_bg"])], foreground=[("selected", c["text"])])
        self.style.configure("App.TNotebook", background=c["app_bg"], borderwidth=0)
        self.style.configure("App.TNotebook.Tab", padding=(14, 7), font=("Segoe UI", 9), background=c["surface_alt"], foreground=c["text"])
        self.style.map("App.TNotebook.Tab", background=[("selected", c["panel_bg"])], foreground=[("selected", c["text"])])
        try:
            if self.layout_name in ("Modern Sekmeli", "Minimal Sekmeli"):
                self.style.layout("App.TNotebook.Tab", [])
            else:
                self.style.layout("App.TNotebook.Tab", self.default_tab_layout)
        except tk.TclError:
            pass
        self.style.configure("TCombobox", fieldbackground=c["surface_bg"], background=c["surface_alt"], foreground=c["text"])
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", c["surface_bg"]), ("!disabled", c["surface_bg"])],
            foreground=[("readonly", c["text"]), ("!disabled", c["text"])],
            selectbackground=[("readonly", c["surface_bg"])],
            selectforeground=[("readonly", c["text"])],
        )

    def on_theme_change(self, event: Any | None = None) -> None:
        selected = self.cmb_theme.get()
        if selected not in THEMES:
            return
        self.theme_name = selected
        self.theme = THEMES[selected]
        self.configure_ttk_style()
        self.apply_theme()
        self.refresh_modern_tabbar()
        self.save_ui_settings()

    def on_layout_change(self, event: Any | None = None) -> None:
        selected = self.cmb_layout.get()
        if selected not in LAYOUTS:
            return
        self.layout_name = selected
        self.configure_ttk_style()
        self.apply_layout()
        self.save_ui_settings()

    def apply_layout(self) -> None:
        compact = self.layout_name == "Minimal Sekmeli"
        custom_tabs = self.layout_name in ("Modern Sekmeli", "Minimal Sekmeli")
        if custom_tabs:
            if not self.tabbar_outer.winfo_ismapped():
                self.tabbar_outer.pack(fill="x", pady=(0, 10), before=self.notebook)
            if self.layout_name == "Modern Sekmeli":
                self.tabbar.pack_forget()
                if not self.tab_canvas.winfo_ismapped():
                    self.tab_canvas.pack(fill="x")
            else:
                self.tab_canvas.pack_forget()
                if not self.tabbar.winfo_ismapped():
                    self.tabbar.pack(anchor="center")
        else:
            self.tabbar_outer.pack_forget()

        self.title_label.configure(font=("Segoe UI", 14 if compact else 20, "bold"))
        if compact:
            self.subtitle_label.pack_forget()
            if self.txt_log.winfo_ismapped():
                self.txt_log.pack_forget()
            self.header.pack_configure(padx=12, pady=(8, 4))
            self.main_area.pack_configure(padx=10, pady=6)
            self.footer.pack_configure(padx=10, pady=(0, 6))
            self.tabbar_outer.pack_configure(pady=(0, 6))
        else:
            if not self.subtitle_label.winfo_ismapped():
                self.subtitle_label.pack(anchor="w", pady=(4, 0))
            if not self.txt_log.winfo_ismapped():
                self.txt_log.pack(fill="x", pady=(6, 0))
            self.txt_log.configure(height=5 if self.layout_name == "Modern Sekmeli" else 7)
            self.header.pack_configure(padx=16, pady=(14, 8))
            self.main_area.pack_configure(padx=16, pady=8)
            self.footer.pack_configure(padx=16, pady=(4, 12))
            if custom_tabs:
                self.tabbar_outer.pack_configure(pady=(0, 10))

        button_padx = 8 if compact else 12
        button_pady = 4 if compact else 7
        button_font_size = 8 if compact else 9
        for btn in self.action_buttons:
            try:
                kwargs = {
                    "padx": button_padx,
                    "pady": button_pady,
                    "font": ("Segoe UI", button_font_size, "bold"),
                }
                if isinstance(btn, tk.Button):
                    kwargs.update({"borderwidth": 0, "highlightthickness": 0, "relief": "flat"})
                btn.configure(**kwargs)
            except tk.TclError:
                pass
        self.apply_tab_button_style()
        self.refresh_modern_tabbar()

    def refresh_modern_tabbar(self) -> None:
        if not hasattr(self, "tab_canvas"):
            return
        self.tab_canvas.update_idletasks()
        self.draw_modern_tabbar()
        self.after_idle(self.draw_modern_tabbar)

    def apply_theme(self) -> None:
        c = self.theme
        self.configure(bg=c["app_bg"])
        self.recolor_widget_tree(self)
        if hasattr(self, "txt_log"):
            self.txt_log.configure(bg=c["log_bg"], fg=c["log_text"], insertbackground=c["text"])
        if hasattr(self, "lbl_status"):
            self.lbl_status.configure(fg=c["success"])
        if hasattr(self, "cmb_layout"):
            self.cmb_layout.configure(foreground=c["text"], background=c["surface_bg"])
        if hasattr(self, "cmb_theme"):
            self.cmb_theme.configure(foreground=c["text"], background=c["surface_bg"])
        self.apply_tab_button_style()
        self.refresh_modern_tabbar()

    def apply_tab_button_style(self) -> None:
        if not hasattr(self, "nav_buttons"):
            return
        c = self.theme
        compact = self.layout_name == "Minimal Sekmeli"
        if self.layout_name == "Modern Sekmeli":
            outer_bg = c["surface_alt"]
            tab_bg = c["surface_bg"]
            padx, pady = 14, 7
        elif self.layout_name == "Minimal Sekmeli":
            outer_bg = c["panel_bg"]
            tab_bg = c["surface_alt"]
            padx, pady = 9, 4
        else:
            outer_bg = c["panel_bg"]
            tab_bg = c["button"]
            padx, pady = 10, 5
        try:
            self.tabbar_outer.configure(bg=outer_bg, highlightthickness=1 if self.layout_name == "Modern Sekmeli" else 0, highlightbackground=c["surface_alt"])
            self.tabbar.configure(bg=outer_bg)
            self.tab_canvas.configure(bg=c["panel_bg"])
        except tk.TclError:
            pass
        current_tab = self.notebook.select()
        for btn in self.nav_buttons:
            try:
                selected = str(getattr(btn, "_target_tab", "")) == current_tab
                common = {
                    "bg": c["accent"] if selected else tab_bg,
                    "activebackground": c["accent"],
                    "fg": "#ffffff" if selected else c["text"],
                    "activeforeground": "#ffffff",
                    "padx": padx,
                    "pady": pady,
                    "font": ("Segoe UI", 8 if compact else 9, "bold"),
                }
                if isinstance(btn, tk.Button):
                    common.update({"borderwidth": 0, "highlightthickness": 0, "relief": "flat"})
                elif isinstance(btn, RoundedButton):
                    common["canvas_bg"] = outer_bg
                btn.configure(
                    **common
                )
            except tk.TclError:
                pass

    def recolor_widget_tree(self, widget: tk.Widget) -> None:
        c = self.theme
        for child in widget.winfo_children():
            cls = child.winfo_class()
            try:
                if cls in ("Frame", "Labelframe"):
                    child.configure(bg=c["panel_bg"])
                elif cls == "Label":
                    child.configure(bg=c["panel_bg"], fg=c["text"])
                elif cls == "Checkbutton":
                    child.configure(bg=c["panel_bg"], fg=c["text"], selectcolor=c["panel_bg"], activebackground=c["panel_bg"], activeforeground=c["text"])
                elif cls == "Text":
                    child.configure(bg=c["log_bg"], fg=c["log_text"], insertbackground=c["text"])
                elif cls == "Button":
                    if not getattr(child, "_action_color", None):
                        child.configure(bg=c["button"], activebackground=c["button_hover"], fg=c["text"], activeforeground=c["text"])
                    child.configure(borderwidth=0, highlightthickness=0, relief="flat")
                elif isinstance(child, RoundedButton):
                    child.configure(canvas_bg=c["panel_bg"])
            except tk.TclError:
                pass
            self.recolor_widget_tree(child)

    def make_tab(self, text: str) -> tk.Frame:
        frame = tk.Frame(self.notebook, bg=self.theme["panel_bg"])
        self.notebook.add(frame, text=text)
        return frame

    def make_tree(self, parent: tk.Widget, columns: tuple[str, ...], headings: tuple[str, ...]) -> ttk.Treeview:
        wrap = tk.Frame(parent, bg=self.theme["panel_bg"])
        wrap.pack(fill="both", expand=True, padx=int(self.theme["pad"]), pady=int(self.theme["pad"]))
        tree = ttk.Treeview(wrap, columns=columns, show="headings")
        scrollbar = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for col, head in zip(columns, headings):
            tree.heading(col, text=head)
            tree.column(col, width=145, anchor="center")
        return tree

    def button(self, parent: tk.Widget, text: str, command: Any, color: str | None = None) -> tk.Widget:
        if self.layout_name == "Modern Sekmeli":
            btn = RoundedButton(
                parent,
                text=text,
                command=command,
                bg=color or str(self.theme["button"]),
                hover_bg=str(self.theme["button_hover"]),
                padx=12,
                pady=7,
            )
        else:
            btn = tk.Button(
                parent,
                text=text,
                command=command,
                bg=color or self.theme["button"],
                fg="#ffffff",
                activebackground=self.theme["button_hover"],
                activeforeground="#ffffff",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                padx=12,
                pady=7,
                font=("Segoe UI", 9, "bold"),
            )
        btn._action_color = color
        self.action_buttons.append(btn)
        return btn

    def build_source_tab(
        self,
        parent: tk.Widget,
        category: str,
        scan_command: Any,
        config_file: str,
    ) -> ttk.Treeview:
        columns = ("name", "channel", "version", "date", "file", "source_type", "page")
        headings = ("Ad", "Kanal", "Versiyon", "Tarih", "Dosya", "Kaynak Tipi", "Sayfa")
        tree = self.make_tree(parent, columns, headings)
        for width_col, width in {"name": 220, "file": 260, "page": 90}.items():
            tree.column(width_col, width=width)

        controls = tk.Frame(parent, bg="#151922")
        controls.pack(fill="x", padx=10, pady=(0, 10))
        self.button(controls, "Sürümleri Tara" if category == "emulators" else "Kaynak Ara", scan_command, "#2980b9").pack(side="left", padx=4)
        self.button(controls, "Seçileni İndir", lambda: self.download_selected(tree, category), "#27ae60").pack(side="left", padx=4)
        self.button(controls, "Kaynak Sayfası", lambda: self.open_selected_page(tree), "#2c3e50").pack(side="left", padx=4)
        self.button(controls, "İndirilenler Klasörü", lambda: self.open_download_folder(category), "#7f8c8d").pack(side="left", padx=4)
        self.button(controls, "Kaynak JSON Düzenle", lambda: self.open_config_file(config_file), "#d35400").pack(side="left", padx=4)

        if category == "emulators":
            self.chk_emu_old_var = tk.BooleanVar(value=False)
            tk.Checkbutton(controls, text="Eski Sürümleri Göster", variable=self.chk_emu_old_var, bg="#151922", fg="#ffffff", selectcolor="#151922").pack(side="left", padx=(16, 4))
            tk.Label(controls, text="Platform:", bg="#151922", fg="#ffffff").pack(side="left", padx=(10, 4))
            self.cmb_emu_platform = ttk.Combobox(controls, values=("Windows", "Linux", "macOS", "Android", "Hepsi (All)"), width=14, state="readonly")
            self.cmb_emu_platform.set("Windows")
            self.cmb_emu_platform.pack(side="left")
        elif category == "firmware":
            self.chk_fw_old_var = tk.BooleanVar(value=False)
            tk.Checkbutton(controls, text="Eski Sürümleri Göster", variable=self.chk_fw_old_var, bg="#151922", fg="#ffffff", selectcolor="#151922").pack(side="left", padx=(16, 4))
        else:
            self.chk_keys_old_var = tk.BooleanVar(value=False)
            tk.Checkbutton(controls, text="Eski Sürümleri Göster", variable=self.chk_keys_old_var, bg="#151922", fg="#ffffff", selectcolor="#151922").pack(side="left", padx=(16, 4))
        return tree

    def build_emulator_tab(self) -> None:
        self.tree_emu = self.build_source_tab(self.tab_emulators, "emulators", self.scan_emulators, "sources.json")

    def build_firmware_tab(self) -> None:
        self.tree_fw = self.build_source_tab(self.tab_firmware, "firmware", self.scan_firmware, "firmware_sources.json")

    def build_keys_tab(self) -> None:
        self.tree_keys = self.build_source_tab(self.tab_keys, "keys", self.scan_keys, "keys_sources.json")

    def build_local_tab(self) -> None:
        columns = ("name", "path", "installed_version", "latest_version", "status", "last_update")
        headings = ("Emülatör", "Kurulum Klasörü", "Benim Sürümüm", "Son Sürüm", "Durum", "Son Güncelleme")
        self.tree_local = self.make_tree(self.tab_local, columns, headings)
        self.tree_local.column("path", width=300)
        controls = tk.Frame(self.tab_local, bg="#151922")
        controls.pack(fill="x", padx=10, pady=(0, 10))
        self.button(controls, "Dizin Ekle", self.add_local_emulator, "#2980b9").pack(side="left", padx=4)
        self.button(controls, "Dizin Kaldır", self.remove_local_emulator, "#c0392b").pack(side="left", padx=4)
        self.button(controls, "Güncellemeleri Denetle", self.check_local_updates, "#8e44ad").pack(side="left", padx=4)
        self.button(controls, "Otomatik Güncelle", self.update_local_emulator, "#27ae60").pack(side="left", padx=4)

    def build_optimizations_tab(self) -> None:
        outer = tk.Frame(self.tab_optimizations, bg="#151922")
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        left = tk.LabelFrame(outer, text="Küresel Emülatör Optimizasyonu", bg="#151922", fg="#ffffff", padx=12, pady=12)
        right = tk.LabelFrame(outer, text="Oyuna Özel Grafik Modları & Yamalar", bg="#151922", fg="#ffffff", padx=12, pady=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.cmb_opt_emu = ttk.Combobox(left, state="readonly")
        self.cmb_opt_profile = ttk.Combobox(
            left,
            values=(
                "Düşük/Orta Seviye Bilgisayar",
                "Yüksek Seviye Bilgisayar",
                "El Konsolu / Steam Deck",
            ),
            state="readonly",
        )
        self.cmb_opt_api = ttk.Combobox(
            left,
            values=("Vulkan", "OpenGL"),
            state="readonly",
        )
        self.cmb_opt_profile.set("Düşük/Orta Seviye Bilgisayar")
        self.cmb_opt_api.set("Vulkan")
        for label, widget in (
            ("Optimize Edilecek Emülatör:", self.cmb_opt_emu),
            ("Bilgisayar Donanım Profiliniz:", self.cmb_opt_profile),
            ("Grafik API'si:", self.cmb_opt_api),
        ):
            tk.Label(left, text=label, bg="#151922", fg="#ffffff").pack(anchor="w", pady=(6, 2))
            widget.pack(fill="x", pady=(0, 8))
        self.button(left, "Donanımı Tara ve Öner", self.scan_and_auto_configure, "#2980b9").pack(anchor="w", pady=6)
        self.button(left, "Ayarları Uygula", self.optimize_global_emulator, "#27ae60").pack(anchor="w", pady=6)
        tk.Label(
            left,
            text="Not: Config.json veya qt-config.ini önce .bak olarak yedeklenir.",
            bg="#151922",
            fg="#a0a0a0",
            wraplength=430,
        ).pack(anchor="w", pady=12)

        self.mods_data = self.default_mods()
        self.cmb_mod_game = ttk.Combobox(right, values=list(self.mods_data.keys()), state="readonly")
        self.cmb_mod_type = ttk.Combobox(right, state="readonly")
        self.cmb_mod_emu = ttk.Combobox(right, values=("Yuzu / Citron / Eden", "Ryujinx"), state="readonly")
        self.cmb_mod_emu.set("Yuzu / Citron / Eden")
        self.lbl_mod_desc = tk.Label(right, text="Mod açıklaması...", bg="#151922", fg="#a0a0a0", wraplength=430, justify="left")
        for label, widget in (
            ("Hedef Switch Oyunu Seçin:", self.cmb_mod_game),
            ("Uygulanacak Grafik Yaması / Mod:", self.cmb_mod_type),
            ("Yamanın Kurulacağı Emülatör:", self.cmb_mod_emu),
        ):
            tk.Label(right, text=label, bg="#151922", fg="#ffffff").pack(anchor="w", pady=(6, 2))
            widget.pack(fill="x", pady=(0, 8))
        self.lbl_mod_desc.pack(anchor="w", fill="x", pady=8)
        self.cmb_mod_game.bind("<<ComboboxSelected>>", self.update_mod_options)
        self.cmb_mod_type.bind("<<ComboboxSelected>>", self.update_mod_description)
        if self.mods_data:
            self.cmb_mod_game.set(next(iter(self.mods_data)))
            self.update_mod_options()
        self.button(right, "Modu İndir ve Uygula", self.apply_game_optimization, "#27ae60").pack(anchor="w", pady=6)
        self.button(right, "Mod Klasörünü Aç", self.open_emulator_mod_folder, "#7f8c8d").pack(anchor="w", pady=6)

    def write_log(self, message: str, level: str = "INFO") -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}"
        try:
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass
        if hasattr(self, "txt_log"):
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", line + "\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        if hasattr(self, "lbl_status"):
            self.lbl_status.configure(text=message)

    def load_json(self, filename: str, default: Any) -> Any:
        path = self.config_dir / filename
        if not path.exists():
            try:
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(default, handle, ensure_ascii=False, indent=2)
            except Exception as exc:
                self.write_log(f"{filename} oluşturulamadı: {exc}", "ERROR")
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            self.write_log(f"{filename} okunamadı: {exc}", "ERROR")
            return default

    def load_sources(self) -> None:
        self.sources = self.load_json("sources.json", self.default_emulator_sources())
        self.firmware_sources = self.load_json("firmware_sources.json", self.default_firmware_sources())
        self.keys_sources = self.load_json("keys_sources.json", self.default_keys_sources())
        self.local_sources = self.load_json("local_emulators.json", [])

    def default_emulator_sources(self) -> list[dict[str, Any]]:
        return [
            {"name": "Citron Neo", "type": "github-releases", "repo": "citron-neo/CI", "enabled": True},
            {"name": "Eden (Nightly)", "type": "gitea-releases", "domain": "git.eden-emu.dev", "repo": "eden-ci/nightly", "enabled": True},
            {"name": "Ryubing", "type": "gitea-releases", "domain": "git.ryujinx.app", "repo": "projects/Ryubing", "enabled": True},
            {"name": "Skyline (Android Switch Emulator)", "type": "github-releases", "repo": "skyline-emu/skyline", "enabled": False},
        ]

    def default_firmware_sources(self) -> list[dict[str, Any]]:
        return [
            {"name": "THZoria NX-Firmware", "type": "github-releases", "repo": "THZoria/NX_Firmware", "enabled": True}
        ]

    def default_keys_sources(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "Yerel Keys Yedekleri",
                "type": "local-files",
                "path": "config/keys",
                "enabled": True,
                "note": "Kendi cihazınızdan dump ettiğiniz prod.keys/title.keys dosyalarını bu klasöre koyun.",
            },
            {
                "name": "LetSwitch Site Keys",
                "type": "manual-page",
                "url": "https://letswitch.site/",
                "enabled": True
            },
            {
                "name": "SwitchKeys.io Keys",
                "type": "manual-page",
                "url": "https://switchkeys.io/switch-prod-keys-download/",
                "enabled": True
            },
            {
                "name": "ProdKeys.io Keys",
                "type": "manual-page",
                "url": "https://prodkeys.io/yuzu-keys-download/",
                "enabled": True
            }
        ]

    def default_mods(self) -> dict[str, dict[str, Any]]:
        return {
            "The Legend of Zelda: Tears of the Kingdom (TitleID: 0100F2C0115B6000)": {
                "title_id": "0100F2C0115B6000",
                "mods": {
                    "60 FPS Performans Yaması": {
                        "url": "https://github.com/hoverbike1/TOTK-Mods-collection/raw/main/Performance/DynamicFPS/DynamicFPS%20v1.5.5%20-%20Complete%20Pack.zip",
                        "fallback_url": "https://github.com/hoverbike1/TOTK-Mods-collection",
                        "desc": "Oyunu 60 FPS yapar, hızını korur ve performansı artırır.",
                    },
                    "Dinamik Çözünürlük Kapat": {
                        "url": "https://github.com/hoverbike1/TOTK-Mods-collection/raw/main/Performance/Disable%20Dynamic%20Resolution/Disable%20Dynamic%20Resolution.zip",
                        "fallback_url": "https://github.com/hoverbike1/TOTK-Mods-collection",
                        "desc": "Çözünürlüğün dinamik olarak düşmesini engeller.",
                    },
                },
            },
            "The Legend of Zelda: Breath of the Wild (TitleID: 01007EF00011E000)": {
                "title_id": "01007EF00011E000",
                "mods": {
                    "60 FPS Performans Yaması": {
                        "url": "https://github.com/yuzu-mirror/yuzu-mod-archive/raw/master/the%20legend%20of%20zelda%20breath%20of%20the%20wild/Breath%20of%20the%20Wild%2060fps.zip",
                        "fallback_url": "https://github.com/yuzu-mirror/yuzu-mod-archive",
                        "desc": "Breath of the Wild için 60 FPS yaması.",
                    }
                },
            },
        }

    def http_get(self, url: str, **kwargs: Any) -> Any:
        if requests is None:
            raise RuntimeError("requests paketi kurulu değil. `pip install -r requirements.txt` komutunu çalıştırın.")
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", USER_AGENT)
        return requests.get(url, headers=headers, timeout=kwargs.pop("timeout", 30), **kwargs)

    def get_channel_name(self, release: dict[str, Any]) -> str:
        tag = str(release.get("tag_name") or release.get("name") or "").lower()
        if release.get("prerelease"):
            return "Nightly / PreRelease"
        if "nightly" in tag:
            return "Nightly"
        if "canary" in tag:
            return "Canary"
        if any(word in tag for word in ("experimental", "alpha", "beta")):
            return "Experimental"
        return "Stable"

    def select_best_asset(self, assets: list[dict[str, Any]], platform: str) -> dict[str, Any] | None:
        if not assets:
            return None
        platform_lower = platform.lower()
        if "all" in platform_lower or "hepsi" in platform_lower:
            return assets[0]
        rules = {
            "windows": (("windows", "win", "x64", ".zip"), ("linux", "mac", "android", ".apk", ".deb", ".appimage")),
            "linux": (("linux", "ubuntu", "appimage", ".tar.xz", ".deb"), ("windows", "win", "mac", "android", ".exe", ".apk")),
            "macos": (("mac", "macos", "darwin", "osx", "apple", ".pkg"), ("windows", "linux", "android", ".apk")),
            "android": (("android", ".apk"), ("windows", "linux", "mac", ".exe")),
        }
        key = "windows"
        for candidate in rules:
            if candidate in platform_lower:
                key = candidate
                break
        positives, negatives = rules[key]
        best_asset = None
        best_score = -999
        for asset in assets:
            name = str(asset.get("name") or asset.get("browser_download_url") or "").lower()
            score = sum(3 for token in positives if token in name) - sum(5 for token in negatives if token in name)
            if name.endswith((".zip", ".appimage", ".tar.xz", ".pkg", ".apk", ".7z")):
                score += 1
            if score > best_score and asset.get("browser_download_url"):
                best_asset = asset
                best_score = score
        return best_asset or assets[0]

    def add_row(self, tree: ttk.Treeview, result: SourceResult) -> None:
        row_id = f"{id(tree)}::{result.name}::{result.version}::{result.file_name}"
        values = (
            result.name,
            result.channel,
            result.version,
            result.date[:10],
            result.file_name,
            result.source_type,
            "Aç",
        )
        tree.insert("", "end", iid=row_id, values=values)
        self.page_urls[row_id] = result.page_url
        self.download_urls[row_id] = result.download_url
        self.latest_scraped_versions[result.name] = result.raw

    def scan_github_releases(self, source: dict[str, Any], show_old: bool, target_platform: str) -> list[SourceResult]:
        repo = source["repo"]
        source_label = source.get("name", repo)
        if source.get("type") in ("gitea-releases", "forgejo-releases"):
            domain = source.get("domain", "").strip().rstrip("/")
            url = f"https://{domain}/api/v1/repos/{repo}/releases"
            api_label = "Gitea Release"
            self.write_log(f"Gitea/Forgejo taranıyor: {source_label} -> {domain}/{repo}")
        else:
            url = f"https://api.github.com/repos/{repo}/releases"
            api_label = "GitHub Release"
            self.write_log(f"GitHub taranıyor: {source_label} -> {repo}")
        response = self.http_get(url)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}")
        data = response.json()
        if isinstance(data, dict):
            data = [data]
        self.write_log(f"{source_label} release sayısı: {len(data)}")
        results: list[SourceResult] = []
        for release in data[: (20 if show_old else 1)]:
            assets = release.get("assets") or []
            asset = self.select_best_asset(assets, target_platform)
            if not asset:
                continue
            asset_name = str(asset.get("name") or Path(str(asset.get("browser_download_url"))).name)
            version = self.release_version_from_asset(source_label, release, asset_name)
            results.append(
                SourceResult(
                    name=source_label,
                    channel=self.get_channel_name(release),
                    version=version,
                    date=str(release.get("published_at") or release.get("created_at") or ""),
                    file_name=asset_name,
                    source_type=api_label,
                    page_url=str(release.get("html_url") or source.get("page_url") or ""),
                    download_url=str(asset.get("browser_download_url") or ""),
                    raw={"release": release, "asset": asset, "source": source},
                )
            )
        return results

    def scan_github_contents(self, source: dict[str, Any], show_old: bool, category: str = "") -> list[SourceResult]:
        repo = source["repo"]
        sub_path = source.get("path", "")
        url = f"https://api.github.com/repos/{repo}/contents/{sub_path}".rstrip("/")
        self.write_log(f"GitHub Contents taranıyor: {source.get('name', repo)} -> {repo}/{sub_path}")
        response = self.http_get(url)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}")
        files = [item for item in response.json() if item.get("type") == "file" and item.get("download_url")]
        filtered = [item for item in files if re.search(r"\.(zip|7z|rar|keys|txt|bin)$", item.get("name", ""), re.I)]
        
        if category == "keys":
            filtered = [item for item in filtered if any(x in item.get("name", "").lower() for x in ("key", "prod"))]
        elif category == "firmware":
            filtered = [item for item in filtered if any(x in item.get("name", "").lower() for x in ("firmware", "fw"))]

        if not show_old:
            filtered = filtered[:1]
        return [
            SourceResult(
                name=source.get("name", repo),
                channel="Direct",
                version=self.extract_version(item.get("name", "")),
                date="",
                file_name=item.get("name", ""),
                source_type="GitHub Direct",
                page_url=item.get("html_url", ""),
                download_url=item.get("download_url", ""),
                raw={"source": source, "file": item},
            )
            for item in filtered
        ]

    def scan_manual_page(self, source: dict[str, Any], show_old: bool, category: str = "") -> list[SourceResult]:
        url = source.get("url", "")
        if not url:
            return []
        self.write_log(f"Web sayfası kazınıyor: {source.get('name', url)} -> {url}")
        response = self.http_get(url)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}")
        html = response.text
        links = re.findall(r'href=["\']([^"\']+?\.(?:zip|7z|rar))["\']', html, re.I)
        links += re.findall(r"(https?://[^\s)\"']+?\.(?:zip|7z|rar))", html, re.I)
        absolute = list(dict.fromkeys(urljoin(url, link) for link in links))
        
        if category == "keys":
            absolute = [link for link in absolute if any(x in Path(link).name.lower() for x in ("key", "prod"))]
        elif category == "firmware":
            absolute = [link for link in absolute if any(x in Path(link).name.lower() for x in ("firmware", "fw"))]

        if not show_old:
            absolute = absolute[:1]
        return [
            SourceResult(
                name=source.get("name", url),
                channel="Direct ZIP",
                version=self.extract_version(Path(link).name),
                date="",
                file_name=Path(link).name,
                source_type="Manual Page",
                page_url=url,
                download_url=link,
                raw={"source": source, "url": link},
            )
            for link in absolute
        ]

    def scan_local_files(self, source: dict[str, Any], show_old: bool) -> list[SourceResult]:
        raw_path = source.get("path", "")
        folder = Path(raw_path)
        if not folder.is_absolute():
            folder = self.root_path / folder
        folder.mkdir(parents=True, exist_ok=True)
        self.write_log(f"Yerel dosya kaynağı taranıyor: {source.get('name', folder)} -> {folder}")
        patterns = ("*.keys", "prod.keys", "title.keys", "*.zip", "*.7z", "*.rar")
        files: list[Path] = []
        for pattern in patterns:
            files.extend(folder.glob(pattern))
        unique_files = sorted(set(files), key=lambda item: item.stat().st_mtime, reverse=True)
        if not show_old:
            unique_files = unique_files[:5]
        return [
            SourceResult(
                name=source.get("name", "Yerel Dosyalar"),
                channel="Local",
                version=datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d-%H%M"),
                date=datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"),
                file_name=path.name,
                source_type="Local File",
                page_url=str(folder),
                download_url=str(path),
                raw={"source": source, "path": str(path)},
            )
            for path in unique_files
        ]

    def extract_version(self, text: str) -> str:
        match = re.search(r"(?:nightly|release)[-_+.]([0-9a-f]{7,12})(?:[-_+.])", text, re.I)
        if match:
            return match.group(1)
        match = re.search(r"(\d+(?:\.\d+){1,4}|[0-9a-f]{7,12})", text, re.I)
        return match.group(1) if match else "Bilinmiyor"

    def release_version_from_asset(self, source_label: str, release: dict[str, Any], asset_name: str) -> str:
        asset_version = self.extract_version(asset_name)
        tag_version = str(release.get("tag_name") or release.get("name") or "unknown")
        if asset_version != "Bilinmiyor":
            if tag_version.lower() in ("nightly-windows", "nightly-linux", "nightly-macos", "nightly-android"):
                return asset_version
            if "citron" in source_label.lower() and "nightly" in tag_version.lower():
                return asset_version
        return tag_version

    def run_scan(self, tree: ttk.Treeview, sources: list[dict[str, Any]], show_old: bool, category: str) -> None:
        def worker() -> None:
            try:
                self.write_log("Kaynak taraması başlatıldı.")
                tree.delete(*tree.get_children())
                target_platform = getattr(self, "cmb_emu_platform", None)
                platform = target_platform.get() if target_platform else "Windows"
                total = 0
                for source in sources:
                    if source.get("enabled", True) is False:
                        continue
                    try:
                        kind = source.get("type", "github-releases")
                        if kind in ("github-releases", "gitea-releases", "forgejo-releases"):
                            results = self.scan_github_releases(source, show_old, platform)
                        elif kind == "github-contents":
                            results = self.scan_github_contents(source, show_old, category)
                        elif kind in ("manual-page", "prodkeys-scraped"):
                            results = self.scan_manual_page(source, show_old, category)
                        elif kind == "local-files":
                            results = self.scan_local_files(source, show_old)
                        else:
                            self.write_log(f"Bilinmeyen kaynak tipi: {kind}", "WARNING")
                            results = []
                        for result in results:
                            self.add_row(tree, result)
                            total += 1
                    except Exception as exc:
                        self.write_log(f"{source.get('name', source)} taranırken hata: {exc}", "ERROR")
                self.write_log(f"Tarama tamamlandı. Toplam bulunan satır: {total}")
            except Exception as exc:
                self.write_log(f"Tarama hatası: {exc}", "ERROR")

        threading.Thread(target=worker, daemon=True).start()

    def scan_emulators(self) -> None:
        self.run_scan(self.tree_emu, self.sources, self.chk_emu_old_var.get(), "emulators")

    def scan_firmware(self) -> None:
        self.run_scan(self.tree_fw, self.firmware_sources, self.chk_fw_old_var.get(), "firmware")

    def scan_keys(self) -> None:
        self.run_scan(self.tree_keys, self.keys_sources, self.chk_keys_old_var.get(), "keys")

    def selected_iid(self, tree: ttk.Treeview) -> str | None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Bilgi", "Lütfen listeden bir satır seçin.")
            return None
        return selection[0]

    def open_selected_page(self, tree: ttk.Treeview) -> None:
        iid = self.selected_iid(tree)
        if not iid:
            return
        url = self.page_urls.get(iid)
        if not url:
            messagebox.showwarning("Uyarı", "Açılacak bir sayfa URL'si bulunamadı.")
            return
        webbrowser.open(url)

    def open_download_folder(self, category: str) -> None:
        folder = self.download_dir / category
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def open_config_file(self, filename: str) -> None:
        path = self.config_dir / filename
        if not path.exists():
            self.load_sources()
        subprocess.Popen(["notepad.exe", str(path)])

    def safe_name(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" ._") or "download"

    def download_selected(self, tree: ttk.Treeview, category: str) -> None:
        iid = self.selected_iid(tree)
        if not iid:
            return
        values = tree.item(iid, "values")
        url = self.download_urls.get(iid)
        if not url:
            messagebox.showwarning("Uyarı", "Geçerli bir indirme bağlantısı bulunamadı.")
            return
        item_name = str(values[0])
        file_name = str(values[4]) or Path(url).name
        target_dir = self.download_dir / category / self.safe_name(item_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file_name
        threading.Thread(target=self.download_worker, args=(url, target_path, category), daemon=True).start()

    def download_worker(self, url: str, target_path: Path, category: str = "") -> bool:
        try:
            if target_path.exists() and target_path.stat().st_size > 0:
                self.write_log(f"Dosya zaten indirilmiş. Mevcut dosya kullanılıyor: {target_path}")
                if category == "keys":
                    self.install_keys(target_path)
                return True
            self.write_log(f"İndiriliyor: {target_path.name}")
            response = self.http_get(url, stream=True, timeout=60)
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            downloaded = 0
            with target_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = downloaded * 100 / total
                        self.lbl_status.configure(text=f"İndiriliyor: {percent:.1f}%")
            self.write_log(f"İndirme tamamlandı: {target_path}", "OK")
            messagebox.showinfo("Tamamlandı", f"Dosya başarıyla indirildi:\n{target_path}")
            if category == "keys":
                self.install_keys(target_path)
            return True
        except Exception as exc:
            self.write_log(f"{target_path.name} indirilirken hata oluştu: {exc}", "ERROR")
            messagebox.showerror("İndirme Hatası", f"Dosya indirilirken bir hata oluştu:\n{exc}")
            return False

    def install_keys(self, file_path: Path) -> None:
        try:
            self.write_log(f"Anahtar kurulumu başlatıldı: {file_path.name}")
            temp_dir = self.config_dir / "temp_keys_extract"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            keys_found = []
            
            if file_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    for member in zip_ref.namelist():
                        filename = Path(member).name
                        if filename.lower() in ("prod.keys", "title.keys"):
                            with zip_ref.open(member) as f:
                                keys_found.append((filename.lower(), f.read()))
            elif file_path.suffix.lower() in (".keys", ".txt"):
                filename = file_path.name.lower()
                if "prod.keys" in filename or "prod" in filename:
                    filename = "prod.keys"
                elif "title.keys" in filename or "title" in filename:
                    filename = "title.keys"
                else:
                    filename = "prod.keys"
                with file_path.open("rb") as f:
                    keys_found.append((filename, f.read()))
            
            if not keys_found:
                self.write_log("Dosya içerisinde 'prod.keys' veya 'title.keys' bulunamadı.", "WARNING")
                messagebox.showwarning("Kurulum Hatası", "İndirilen dosya içerisinde prod.keys veya title.keys bulunamadı.")
                return
            
            destinations = []
            
            for item in self.local_sources:
                emu_name = item.get("name", "").lower()
                emu_path = Path(item.get("path", ""))
                if not emu_path.exists():
                    continue
                if "ryu" in emu_name:
                    portable_dir = emu_path / "portable" / "system"
                    if portable_dir.exists() or (emu_path / "portable").exists():
                        destinations.append(emu_path / "portable" / "system")
                    else:
                        destinations.append(Path(os.path.expandvars(r"%APPDATA%\Ryujinx\system")))
                elif "citron" in emu_name:
                    portable_dir = emu_path / "user" / "keys"
                    if portable_dir.exists() or (emu_path / "user").exists():
                        destinations.append(emu_path / "user" / "keys")
                    else:
                        destinations.append(Path(os.path.expandvars(r"%APPDATA%\citron\keys")))
                elif "eden" in emu_name:
                    portable_dir = emu_path / "user" / "keys"
                    if portable_dir.exists() or (emu_path / "user").exists():
                        destinations.append(emu_path / "user" / "keys")
                    else:
                        destinations.append(Path(os.path.expandvars(r"%APPDATA%\eden\keys")))
                elif "yuzu" in emu_name:
                    portable_dir = emu_path / "user" / "keys"
                    if portable_dir.exists() or (emu_path / "user").exists():
                        destinations.append(emu_path / "user" / "keys")
                    else:
                        destinations.append(Path(os.path.expandvars(r"%APPDATA%\yuzu\keys")))
            
            std_paths = {
                "Ryujinx": Path(os.path.expandvars(r"%APPDATA%\Ryujinx\system")),
                "Citron": Path(os.path.expandvars(r"%APPDATA%\citron\keys")),
                "Eden": Path(os.path.expandvars(r"%APPDATA%\eden\keys")),
                "Yuzu": Path(os.path.expandvars(r"%APPDATA%\yuzu\keys")),
                "Suyu": Path(os.path.expandvars(r"%APPDATA%\suyu\keys")),
                "Sudachi": Path(os.path.expandvars(r"%APPDATA%\sudachi\keys")),
                "Uzuy": Path(os.path.expandvars(r"%APPDATA%\uzuy\keys")),
            }
            
            for name, path in std_paths.items():
                if path.parent.exists():
                    destinations.append(path)
            
            destinations = list(set(destinations))
            
            if not destinations:
                if messagebox.askyesno("Klasör Bulunamadı", "Sisteminizde kurulu herhangi bir emülatör klasörü otomatik tespit edilemedi.\nVarsayılan Ryujinx ve Citron klasörleri oluşturularak anahtarlar yüklensin mi?"):
                    destinations.append(std_paths["Ryujinx"])
                    destinations.append(std_paths["Citron"])
                else:
                    custom_path = filedialog.askdirectory(title="Anahtarların kurulacağı Emülatör Sistem/Keys klasörünü seçin")
                    if custom_path:
                        destinations.append(Path(custom_path))
            
            installed_paths = []
            for dest in destinations:
                dest.mkdir(parents=True, exist_ok=True)
                for filename, data in keys_found:
                    target_file = dest / filename
                    with target_file.open("wb") as f:
                        f.write(data)
                    installed_paths.append(str(target_file))
            
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                
            self.write_log(f"Anahtarlar başarıyla yüklendi. Hedef sayısı: {len(destinations)}", "OK")
            installed_summary = "\n".join([f"- {Path(p).parent.name}\\{Path(p).name}" for p in installed_paths])
            messagebox.showinfo("Kurulum Başarılı", f"Anahtarlar başarıyla aşağıdaki emülatör dizinlerine kuruldu:\n\n{installed_summary}")
            
        except Exception as exc:
            self.write_log(f"Anahtar yüklenirken hata: {exc}", "ERROR")
            messagebox.showerror("Kurulum Hatası", f"Anahtarlar otomatik kurulurken bir hata oluştu:\n{exc}")

    def refresh_local_table(self) -> None:
        if not hasattr(self, "tree_local"):
            return
        self.tree_local.delete(*self.tree_local.get_children())
        for idx, item in enumerate(self.local_sources):
            installed = item.get("installed_version") or self.detect_installed_version(item.get("name", ""), item.get("path", ""))
            latest = item.get("latest_version", "Bilinmiyor")
            status = "Bilinmiyor"
            if installed and latest and latest != "Bilinmiyor":
                status = "Güncel" if self.normalize_version(installed) == self.normalize_version(latest) else "Güncelleme Var"
            self.tree_local.insert(
                "",
                "end",
                iid=str(idx),
                values=(item.get("name", ""), item.get("path", ""), installed or "Bilinmiyor", latest, status, item.get("last_update", "")),
            )

    def normalize_version(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9.]+", "", str(value)).lower()

    def save_local_emulators(self) -> None:
        try:
            with (self.config_dir / "local_emulators.json").open("w", encoding="utf-8") as handle:
                json.dump(self.local_sources, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.write_log(f"Yerel emülatörler kaydedilirken hata: {exc}", "ERROR")

    def detect_installed_version(self, emu_name: str, path_str: str) -> str:
        try:
            path = Path(path_str)
            metadata = path / ".updater_metadata.json"
            if metadata.exists():
                with metadata.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return str(data.get("version") or data.get("tag") or "Bilinmiyor")
            patterns = {
                "Ryubing": ("**/Ryujinx.exe", "**/ryujinx.exe"),
                "Ryujinx": ("**/Ryujinx.exe", "**/ryujinx.exe"),
                "Eden": ("**/eden.exe", "**/eden-cli.exe"),
                "Citron": ("**/citron.exe", "**/yuzu.exe"),
                "Yuzu": ("**/yuzu.exe",),
            }
            for key, globs in patterns.items():
                if key.lower() in emu_name.lower():
                    for pattern in globs:
                        for exe in path.glob(pattern):
                            version = self.file_version(exe)
                            if version:
                                return version
            zip_files = sorted((self.download_dir / "emulators" / self.safe_name(emu_name)).glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
            if zip_files:
                return self.extract_version(zip_files[0].name)
        except Exception as exc:
            self.write_log(f"Sürüm tespiti sırasında hata ({emu_name}): {exc}", "ERROR")
        return "Bilinmiyor"

    def file_version(self, path: Path) -> str:
        try:
            escaped_path = str(path).replace("'", "''")
            command = f"(Get-Item '{escaped_path}').VersionInfo.ProductVersion"
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=8)
            return result.stdout.strip()
        except Exception:
            return ""

    def add_local_emulator(self) -> None:
        folder = filedialog.askdirectory(title="Emülatör Kurulu Olduğu Dizini Seç")
        if not folder:
            return
        names = ["Citron Neo", "Eden (Nightly)", "Ryubing", "Ryujinx", "Yuzu"]
        popup = tk.Toplevel(self)
        popup.title("Klasör Ekle")
        popup.geometry("400x170")
        popup.configure(bg="#151922")
        tk.Label(popup, text="Eklemek istediğiniz emülatör:", bg="#151922", fg="#ffffff").pack(pady=(14, 6))
        cmb = ttk.Combobox(popup, values=names, state="readonly")
        cmb.set(names[0])
        cmb.pack(fill="x", padx=24)

        def proceed() -> None:
            if any(item.get("path") == folder for item in self.local_sources):
                messagebox.showwarning("Uyarı", "Bu dizin zaten ekli!")
                return
            name = cmb.get()
            detected = self.detect_installed_version(name, folder)
            self.local_sources.append({"name": name, "path": folder, "installed_version": detected, "latest_version": "Bilinmiyor", "last_update": ""})
            self.save_local_emulators()
            self.refresh_local_table()
            self.update_optimizations_emu_list()
            self.write_log(f"Yerel emülatör eklendi: {name} -> {folder}")
            popup.destroy()

        self.button(popup, "Ekle", proceed, "#27ae60").pack(pady=16)
        popup.grab_set()

    def remove_local_emulator(self) -> None:
        iid = self.selected_iid(self.tree_local)
        if iid is None:
            return
        idx = int(iid)
        removed = self.local_sources.pop(idx)
        self.save_local_emulators()
        self.refresh_local_table()
        self.update_optimizations_emu_list()
        self.write_log(f"Yerel emülatör silindi: {removed.get('name')}")

    def check_local_updates(self) -> None:
        def worker() -> None:
            try:
                self.write_log("Yerel sürümler taranıyor.")
                self.scan_for_latest_versions()
                for item in self.local_sources:
                    name = item.get("name", "")
                    item["installed_version"] = self.detect_installed_version(name, item.get("path", ""))
                    latest = self.find_latest_for_local_name(name)
                    if latest:
                        item["latest_version"] = latest.get("version", "Bilinmiyor")
                        item["latest_raw"] = latest
                self.save_local_emulators()
                self.refresh_local_table()
                self.write_log("Sürüm denetimi tamamlandı.")
                messagebox.showinfo("Tamamlandı", "Sürüm denetimi tamamlandı. Durum sütununu inceleyebilirsiniz.")
            except Exception as exc:
                self.write_log(f"Arka plan güncelleme kontrol hatası: {exc}", "ERROR")

        threading.Thread(target=worker, daemon=True).start()

    def scan_for_latest_versions(self) -> None:
        for source in self.sources:
            if source.get("enabled", True) is False:
                continue
            try:
                if source.get("type") not in ("github-releases", "gitea-releases", "forgejo-releases"):
                    continue
                results = self.scan_github_releases(source, False, "Windows")
                if results:
                    self.latest_scraped_versions[results[0].name] = {
                        "version": results[0].version,
                        "download_url": results[0].download_url,
                        "file_name": results[0].file_name,
                        "page_url": results[0].page_url,
                        "source": source,
                    }
            except Exception as exc:
                self.write_log(f"Yerel kayıt için veri eşitlenirken hata: {source.get('name')}: {exc}", "ERROR")

    def find_latest_for_local_name(self, name: str) -> dict[str, Any] | None:
        lowered = name.lower()
        for key, value in self.latest_scraped_versions.items():
            if key.lower() in lowered or lowered in key.lower() or ("ryu" in lowered and "ryu" in key.lower()):
                return value
        return None

    def update_local_emulator(self) -> None:
        iid = self.selected_iid(self.tree_local)
        if iid is None:
            return
        item = self.local_sources[int(iid)]
        if not item.get("latest_raw"):
            messagebox.showwarning("Uyarı", "Önce 'Güncellemeleri Denetle' butonuna basarak son sürümü tespit edin.")
            return
        status = self.tree_local.item(iid, "values")[4]
        if status == "Güncel" and not messagebox.askyesno("Zaten Güncel", "Bu emülatör zaten güncel görünüyor. Yine de üzerine kurmak istiyor musunuz?"):
            return
        threading.Thread(target=self.update_local_emulator_thread, args=(item,), daemon=True).start()

    def update_local_emulator_thread(self, item: dict[str, Any]) -> None:
        try:
            name = item["name"]
            local_path = Path(item["path"])
            latest = item["latest_raw"]
            url = latest.get("download_url")
            file_name = latest.get("file_name") or Path(url).name
            version = latest.get("version", "Bilinmiyor")
            if not url:
                raise RuntimeError("Son sürüm kaynak bilgisi bulunamadı.")
            self.write_log(f"Auto-Update başlatıldı: {name} -> {version}")
            persistent_dir = self.download_dir / "emulators" / self.safe_name(name)
            persistent_dir.mkdir(parents=True, exist_ok=True)
            temp_zip_path = persistent_dir / file_name
            if not self.download_worker(url, temp_zip_path):
                return

            backup_dir = self.download_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_zip_path = backup_dir / f"{self.safe_name(name)}_backup_{stamp}.zip"
            if local_path.exists():
                self.write_log(f"Yedek alınıyor: {local_path} -> {backup_zip_path}")
                with zipfile.ZipFile(backup_zip_path, "w", zipfile.ZIP_DEFLATED) as backup_zip:
                    for root, _, files in os.walk(local_path):
                        for file in files:
                            file_path = Path(root) / file
                            backup_zip.write(file_path, file_path.relative_to(local_path.parent))
                self.write_log("Yedekleme başarıyla tamamlandı.", "OK")
            local_path.mkdir(parents=True, exist_ok=True)
            self.write_log(f"Ayıklanıyor: {temp_zip_path} -> {local_path}")
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                zip_ref.extractall(local_path)
            metadata = {"name": name, "version": version, "source_file": file_name, "updated_at": datetime.now().isoformat(timespec="seconds")}
            with (local_path / ".updater_metadata.json").open("w", encoding="utf-8") as handle:
                json.dump(metadata, handle, ensure_ascii=False, indent=2)
            item["installed_version"] = version
            item["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.save_local_emulators()
            self.refresh_local_table()
            self.write_log(f"Auto-Update başarıyla tamamlandı: {name} -> {version}", "OK")
            messagebox.showinfo("Güncelleme Başarılı", f"{name} güncellendi.\nYedek: {backup_zip_path}")
        except Exception as exc:
            self.write_log(f"Auto-Update sırasında hata oluştu: {exc}", "ERROR")
            messagebox.showerror("Güncelleme Hatası", f"Otomatik güncelleme yapılırken hata oluştu:\n{exc}")

    def update_optimizations_emu_list(self) -> None:
        if not hasattr(self, "cmb_opt_emu"):
            return
        options = [f"{item.get('name')} | {item.get('path')}" for item in self.local_sources]
        if not options:
            options = ["Kurulu emülatör bulunamadı"]
        self.cmb_opt_emu.configure(values=options)
        self.cmb_opt_emu.set(options[0])

    def scan_and_auto_configure(self) -> None:
        threading.Thread(target=self.scan_and_auto_configure_thread, daemon=True).start()

    def scan_and_auto_configure_thread(self) -> None:
        try:
            self.write_log("Sistem donanımı taranıyor.")
            gpu = self.run_powershell("(Get-CimInstance Win32_VideoController).Name")
            cpu = self.run_powershell("(Get-CimInstance Win32_Processor).Name")
            ram = self.run_powershell("[math]::round((Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB)")
            legacy_gpu = any(token in gpu.lower() for token in ("intel(r) hd", "intel graphics", "radeon hd", "geforce gt"))
            api = "OpenGL" if legacy_gpu else "Vulkan"
            try:
                ram_value = int(re.search(r"\d+", ram).group(0))
            except Exception:
                ram_value = 8
            profile = "Yüksek Seviye Bilgisayar" if ram_value >= 16 and not legacy_gpu else "Düşük/Orta Seviye Bilgisayar"
            self.cmb_opt_profile.set(profile)
            self.cmb_opt_api.set(api)
            self.write_log(f"Sistem Donanımı Tespit Edildi: CPU: {cpu} | GPU: {gpu} | RAM: {ram} GB")
            messagebox.showinfo("Donanım Tespit Edildi", f"CPU: {cpu}\nGPU: {gpu}\nRAM: {ram} GB\n\nÖneri: {profile} + {api}")
        except Exception as exc:
            self.write_log(f"Sistem taraması tamamlanamadı: {exc}", "ERROR")

    def run_powershell(self, command: str) -> str:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr).strip() or "Sorgulanamadı"

    def optimize_global_emulator(self) -> None:
        emu_value = self.cmb_opt_emu.get()
        if "|" not in emu_value:
            messagebox.showwarning("Uyarı", "Önce 'Yerel Emülatörler' sekmesinden bir emülatör dizini ekleyin.")
            return
        name, path_str = [part.strip() for part in emu_value.split("|", 1)]
        profile = self.cmb_opt_profile.get()
        api = self.cmb_opt_api.get()
        if not messagebox.askyesno("Optimizasyon Onayı", f"{name}, '{profile}' profili ve '{api}' API moduna göre optimize edilecek. Devam etmek istiyor musunuz?"):
            return
        try:
            base = Path(path_str)
            success = False
            if "ryu" in name.lower():
                candidates = [base / "Config.json", Path(os.path.expandvars(r"%APPDATA%\Ryujinx\Config.json"))]
                for config in candidates:
                    if config.exists():
                        shutil.copy2(config, str(config) + ".bak")
                        self.optimize_ryujinx_config(config, profile, api)
                        success = True
            else:
                appname = "eden" if "eden" in name.lower() else "citron"
                candidates = [base / "user" / "config" / "qt-config.ini", Path(os.path.expandvars(fr"%APPDATA%\{appname}\config\qt-config.ini"))]
                for config in candidates:
                    if config.exists():
                        shutil.copy2(config, str(config) + ".bak")
                        self.optimize_yuzu_style_ini(config, profile, api)
                        success = True
            if not success:
                messagebox.showwarning("Uyarı", "Ayar dosyası bulunamadı. Emülatörü en az bir kez çalıştırıp kapatın.")
                return
            self.write_log(f"Optimizasyon başarıyla tamamlandı: {name}", "OK")
            messagebox.showinfo("Optimizasyon tamamlandı", f"{name} seçilen ayarlarla optimize edildi. Orijinal yapılandırma .bak olarak saklandı.")
        except Exception as exc:
            self.write_log(f"Optimizasyon hatası: {exc}", "ERROR")
            messagebox.showerror("Optimizasyon hatası", f"Optimizasyon yapılamadı:\n{exc}")

    def optimize_ryujinx_config(self, config_path: Path, profile: str, api: str) -> None:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        data["graphics_backend"] = "OpenGl" if api.lower().startswith("opengl") else "Vulkan"
        data["enable_shader_cache"] = True
        data["enable_ptc"] = True
        data["enable_macro_hle"] = True
        data["backend_threading"] = "Auto"
        data["res_scale_custom"] = 2 if "Yüksek" in profile else 1
        data["max_anisotropy"] = 16 if "Yüksek" in profile else 1
        data["enable_vsync"] = "Deck" in profile
        with config_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def optimize_yuzu_style_ini(self, ini_path: Path, profile: str, api: str) -> None:
        lines = ini_path.read_text(encoding="utf-8", errors="ignore").splitlines(True)
        settings = {
            "backend": "0" if api.lower().startswith("opengl") else "1",
            "use_disk_shader_cache": "true",
            "resolution_setup": "2" if "Yüksek" in profile else "1",
        }
        out: list[str] = []
        in_renderer = False
        seen = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if in_renderer:
                    for key, value in settings.items():
                        if key not in seen:
                            out.append(f"{key}={value}\n")
                in_renderer = stripped.lower() == "[renderer]"
            if in_renderer and "=" in stripped:
                key = stripped.split("=", 1)[0]
                if key in settings:
                    out.append(f"{key}={settings[key]}\n")
                    seen.add(key)
                    continue
            out.append(line)
        if not any(line.strip().lower() == "[renderer]" for line in lines):
            out.append("\n[Renderer]\n")
            for key, value in settings.items():
                out.append(f"{key}={value}\n")
        elif in_renderer:
            for key, value in settings.items():
                if key not in seen:
                    out.append(f"{key}={value}\n")
        ini_path.write_text("".join(out), encoding="utf-8")

    def update_mod_options(self, event: Any | None = None) -> None:
        game_key = self.cmb_mod_game.get()
        mods = self.mods_data.get(game_key, {}).get("mods", {})
        names = list(mods.keys())
        self.cmb_mod_type.configure(values=names)
        if names:
            self.cmb_mod_type.set(names[0])
        self.update_mod_description()

    def update_mod_description(self, event: Any | None = None) -> None:
        game_key = self.cmb_mod_game.get()
        mod_key = self.cmb_mod_type.get()
        desc = self.mods_data.get(game_key, {}).get("mods", {}).get(mod_key, {}).get("desc", "Mod açıklaması...")
        self.lbl_mod_desc.configure(text=desc)

    def current_mod_target_folder(self) -> Path | None:
        game_key = self.cmb_mod_game.get()
        title_id = self.mods_data.get(game_key, {}).get("title_id")
        if not title_id:
            return None
        emu_type = self.cmb_mod_emu.get()
        if "Ryujinx" in emu_type:
            return Path(os.path.expandvars(fr"%APPDATA%\Ryujinx\mods\contents\{title_id}"))
        folder_name = "citron"
        return Path(os.path.expandvars(fr"%APPDATA%\{folder_name}\load\{title_id}"))

    def apply_game_optimization(self) -> None:
        game_key = self.cmb_mod_game.get()
        mod_key = self.cmb_mod_type.get()
        mod_info = self.mods_data.get(game_key, {}).get("mods", {}).get(mod_key)
        if not mod_info:
            messagebox.showwarning("Uyarı", "Lütfen geçerli bir oyun ve mod seçin.")
            return
        if not messagebox.askyesno("Kurulum Onayı", f"Seçilen yama indirilecek ve emülatör mod klasörüne kurulacak.\n\nMod: {mod_key}\nOyun: {game_key}\n\nDevam etmek istiyor musunuz?"):
            return
        threading.Thread(target=self.apply_game_optimization_thread, args=(game_key, mod_key, mod_info), daemon=True).start()

    def apply_game_optimization_thread(self, game_key: str, mod_key: str, mod_info: dict[str, Any]) -> None:
        try:
            target = self.current_mod_target_folder()
            if not target:
                raise RuntimeError("Hedef mod klasörü belirlenemedi.")
            target.mkdir(parents=True, exist_ok=True)
            zip_path = self.download_dir / "mods" / f"{self.safe_name(game_key)}_{self.safe_name(mod_key)}.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            if not zip_path.exists():
                self.write_log(f"Yama indiriliyor: {mod_key}")
                if not self.download_worker(mod_info["url"], zip_path):
                    fallback = mod_info.get("fallback_url")
                    if fallback:
                        webbrowser.open(fallback)
                    return
            self.write_log("Yama emülatöre kuruluyor.")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(target)
            self.write_log(f"Yama başarıyla kuruldu: {mod_key}", "OK")
            messagebox.showinfo("Yama Başarıyla Kuruldu", f"{mod_key} başarıyla uygulandı.\nKurulan Dizin:\n{target}")
        except Exception as exc:
            self.write_log(f"Mod kurulumu hatası: {exc}", "ERROR")
            fallback = mod_info.get("fallback_url")
            if fallback:
                webbrowser.open(fallback)
            messagebox.showerror("Manuel Kurulum Gerekli", f"Yama otomatik kurulamadı:\n{exc}")

    def open_emulator_mod_folder(self) -> None:
        target = self.current_mod_target_folder()
        if not target:
            messagebox.showwarning("Uyarı", "Önce geçerli bir oyun seçin.")
            return
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(target)


def main() -> None:
    app = SwitchDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
