"""Interfaz grafica del reemplazador de logos PDF."""

from __future__ import annotations

import csv
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageTk

from logo_engine import (
    Detection,
    LogoAsset,
    LogoEngineError,
    LogoNotFoundError,
    PdfEncryptedError,
    ReplaceResult,
    detect_logo,
    find_pdfs,
    load_logo_asset,
    replace_pdf,
    unique_output_path,
)

APP_TITLE = "Reemplazador de logo PDF"
APP_VERSION = "1.0"

BG = "#F3F5F8"
CARD = "#FFFFFF"
TEXT = "#1F2937"
MUTED = "#6B7280"
BORDER = "#E2E8F0"
RED = "#E4002B"
RED_DARK = "#B80023"
BLUE = "#5B8FA8"
BLUE_DARK = "#44748C"
SOFT_RED = "#FDE7EB"
SOFT_BLUE = "#EAF3F7"
GREEN = "#15803D"
DARK = "#111827"
LOG_BG = "#0F172A"
LOG_TEXT = "#D7E0EA"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return app_dir()


def enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _font(size: int, bold: bool = False, mono: bool = False) -> tuple:
    family = "Consolas" if mono else "Segoe UI"
    return (family, size, "bold" if bold else "normal")


class LogoReplacerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_TITLE}  ·  v{APP_VERSION}")
        self.root.configure(bg=BG)
        self.root.geometry("1180x820")
        self.root.minsize(1040, 720)

        self.files: list[Path] = []
        self.logo: LogoAsset | None = None
        self.analysis: Detection | None = None
        self.current_source: Path | None = None
        self.output_by_source: dict[str, Path] = {}
        self.preview_page = 0
        self.preview_page_count = 0
        self.preview_mode = "antes"
        self.detail_mode = False
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.logo_photo: ImageTk.PhotoImage | None = None
        self._preview_job: str | None = None
        self._output_auto = True
        self._icon_photo: ImageTk.PhotoImage | None = None

        self.processing = False
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.message_queue: queue.Queue = queue.Queue()
        self.last_report: Path | None = None
        self.last_results: list[ReplaceResult] = []
        self.last_errors: list[tuple[Path, str]] = []

        self.var_footer = tk.BooleanVar(value=True)
        self.var_scale = tk.StringVar(value="100")
        self.var_output = tk.StringVar(value="")
        self.var_open_folder = tk.BooleanVar(value=True)
        self.var_page = tk.StringVar(value="1")
        self.var_status = tk.StringVar(value="Listo")
        self.var_file_count = tk.StringVar(value="0 archivos")
        self.var_logo_info = tk.StringVar(value="Sin logo seleccionado")
        self.var_preview_info = tk.StringVar(value="Agrega un PDF para comenzar")

        self._build_styles()
        self._build_ui()
        self._set_app_icon()
        self._load_defaults()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._poll_queue)
        self.root.bind("<Control-o>", lambda _e: self.add_files())
        self.root.bind("<Control-O>", lambda _e: self.add_files())
        self.root.bind("<Control-Return>", lambda _e: self.start_processing())

    # ------------------------------------------------------------------
    # Construccion de la interfaz
    # ------------------------------------------------------------------

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor="#E5E7EB",
            background=RED,
            bordercolor="#E5E7EB",
            lightcolor=RED,
            darkcolor=RED,
            thickness=7,
        )
        style.configure(
            "App.Vertical.TScrollbar",
            background="#CBD5E1",
            troughcolor="#F8FAFC",
            bordercolor="#F8FAFC",
            arrowcolor="#475569",
        )

    def _build_ui(self) -> None:
        accent = tk.Canvas(self.root, height=4, bg=CARD, highlightthickness=0)
        accent.pack(fill="x")
        accent.create_rectangle(0, 0, 700, 4, fill=RED, outline="")
        accent.create_rectangle(700, 0, 2400, 4, fill=BLUE, outline="")

        header = tk.Frame(self.root, bg=CARD)
        header.pack(fill="x")
        header_inner = tk.Frame(header, bg=CARD)
        header_inner.pack(fill="x", padx=24, pady=(15, 14))
        left_header = tk.Frame(header_inner, bg=CARD)
        left_header.pack(side="left", fill="x", expand=True)

        tk.Label(
            left_header,
            text=APP_TITLE,
            bg=CARD,
            fg=TEXT,
            font=_font(19, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            left_header,
            text="Sustituye el logo antiguo en todas las páginas y en lote, sin cambiar el contenido.",
            bg=CARD,
            fg=MUTED,
            font=_font(9),
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        badge = tk.Frame(header_inner, bg=SOFT_BLUE)
        badge.pack(side="right", anchor="e")
        tk.Label(
            badge,
            text="  Procesamiento local  ·  tus archivos no se suben  ",
            bg=SOFT_BLUE,
            fg=BLUE_DARK,
            font=_font(8, bold=True),
            pady=6,
        ).pack()

        status = tk.Frame(self.root, bg=CARD, height=28)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        tk.Label(
            status,
            textvariable=self.var_status,
            bg=CARD,
            fg=MUTED,
            font=_font(8),
            anchor="w",
        ).pack(side="left", padx=20, pady=5)
        tk.Label(
            status,
            text=f"v{APP_VERSION}  ·  PDF + PyMuPDF",
            bg=CARD,
            fg="#9CA3AF",
            font=_font(8),
            anchor="e",
        ).pack(side="right", padx=20, pady=5)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(12, 8))

        left = tk.Frame(body, bg=BG, width=382)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self._build_files_card(left)
        self._build_logo_card(left)
        self._build_options_card(left)
        self._build_actions(left)
        self._build_preview(right)
        self._build_log(right)



    def _make_card(self, parent: tk.Widget) -> tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=12, pady=9)
        return outer, inner

    def _section_title(
        self, parent: tk.Widget, number: str, title: str, extra: str = ""
    ) -> tk.Frame:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x")
        num = tk.Label(
            row,
            text=number,
            bg=RED if number == "1" else BLUE,
            fg="white",
            font=_font(8, bold=True),
            width=2,
            pady=2,
        )
        num.pack(side="left")
        tk.Label(
            row,
            text=title,
            bg=CARD,
            fg=TEXT,
            font=_font(10, bold=True),
            anchor="w",
        ).pack(side="left", padx=(8, 0))
        if extra:
            tk.Label(
                row,
                text=extra,
                bg=CARD,
                fg=MUTED,
                font=_font(8),
                anchor="e",
            ).pack(side="right")
        return row

    def _build_files_card(self, parent: tk.Widget) -> None:
        card, inner = self._make_card(parent)
        card.pack(fill="x", pady=(0, 10))
        self._section_title(inner, "1", "Archivos PDF", "")
        self.file_count_label = tk.Label(
            inner,
            textvariable=self.var_file_count,
            bg=CARD,
            fg=MUTED,
            font=_font(8),
            anchor="e",
        )
        self.file_count_label.pack(anchor="e", pady=(0, 4))

        list_frame = tk.Frame(inner, bg=CARD)
        list_frame.pack(fill="x")
        self.file_list = tk.Listbox(
            list_frame,
            height=5,
            selectmode=tk.EXTENDED,
            activestyle="none",
            bg="#FBFCFE",
            fg=TEXT,
            selectbackground=SOFT_RED,
            selectforeground=TEXT,
            font=_font(8),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BLUE,
            relief="flat",
        )
        self.file_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.file_list.yview,
            style="App.Vertical.TScrollbar",
        )
        scroll.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.bind("<<ListboxSelect>>", self._on_file_select)

        buttons = tk.Frame(inner, bg=CARD)
        buttons.pack(fill="x", pady=(7, 0))
        self.btn_add = self._button(
            buttons, "Agregar PDFs", self.add_files, kind="secondary"
        )
        self.btn_add.pack(side="left")
        self.btn_folder = self._button(
            buttons, "Agregar carpeta", self.add_folder, kind="secondary"
        )
        self.btn_folder.pack(side="left", padx=(6, 0))
        self.btn_remove = self._button(
            buttons, "Quitar", self.remove_selected, kind="ghost"
        )
        self.btn_remove.pack(side="right")

    def _build_logo_card(self, parent: tk.Widget) -> None:
        card, inner = self._make_card(parent)
        card.pack(fill="x", pady=(0, 10))
        self._section_title(inner, "2", "Logo nuevo")
        self.logo_canvas = tk.Canvas(
            inner,
            height=62,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.logo_canvas.pack(fill="x", pady=(7, 5))
        self.logo_canvas.bind("<Configure>", lambda _e: self._draw_logo_preview())

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        self.btn_logo = self._button(
            row, "Elegir imagen...", self.choose_logo, kind="secondary"
        )
        self.btn_logo.pack(side="left")
        tk.Label(
            row,
            textvariable=self.var_logo_info,
            bg=CARD,
            fg=MUTED,
            font=_font(8),
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(8, 0), fill="x", expand=True)

    def _build_options_card(self, parent: tk.Widget) -> None:
        card, inner = self._make_card(parent)
        card.pack(fill="x", pady=(0, 10))
        self._section_title(inner, "3", "Opciones")

        self.chk_footer = tk.Checkbutton(
            inner,
            text="Reemplazar también el logo del pie de página",
            variable=self.var_footer,
            bg=CARD,
            fg=TEXT,
            activebackground=CARD,
            activeforeground=TEXT,
            selectcolor=CARD,
            font=_font(8),
            anchor="w",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self.chk_footer.pack(anchor="w", pady=(6, 0))

        scale_row = tk.Frame(inner, bg=CARD)
        scale_row.pack(fill="x", pady=(8, 0))
        tk.Label(
            scale_row,
            text="Tamaño del logo",
            bg=CARD,
            fg=TEXT,
            font=_font(8),
        ).pack(side="left")
        self.spin_scale = tk.Spinbox(
            scale_row,
            from_=60,
            to=110,
            increment=5,
            textvariable=self.var_scale,
            width=5,            justify="center",
            font=_font(8),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BLUE,
            relief="flat",
            bg="#FBFCFE",
        )
        self.spin_scale.pack(side="left", padx=(8, 3))
        tk.Label(
            scale_row,
            text="% del ancho original",
            bg=CARD,
            fg=MUTED,
            font=_font(8),
        ).pack(side="left")

        out_row = tk.Frame(inner, bg=CARD)
        out_row.pack(fill="x", pady=(8, 0))
        tk.Label(
            out_row, text="Carpeta de salida", bg=CARD, fg=TEXT, font=_font(8)
        ).pack(side="left")
        self.entry_output = tk.Entry(
            out_row,
            textvariable=self.var_output,
            font=_font(8),
            bg="#FBFCFE",
            fg=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BLUE,
        )
        self.entry_output.pack(side="left", fill="x", expand=True, padx=(8, 4))
        self.entry_output.bind("<KeyRelease>", self._on_output_edited)
        self.btn_output = self._button(
            out_row, "...", self.choose_output_folder, kind="ghost"
        )
        self.btn_output.pack(side="right")

        self.chk_open = tk.Checkbutton(
            inner,
            text="Abrir la carpeta al terminar",
            variable=self.var_open_folder,
            bg=CARD,
            fg=MUTED,
            activebackground=CARD,
            activeforeground=TEXT,
            selectcolor=CARD,
            font=_font(8),
            anchor="w",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self.chk_open.pack(anchor="w", pady=(7, 0))

    def _build_actions(self, parent: tk.Widget) -> None:
        box = tk.Frame(parent, bg=BG)
        box.pack(fill="x", pady=(2, 0))
        self.btn_analyze = self._button(
            box, "Analizar y previsualizar", self.analyze_selected, kind="secondary"
        )
        self.btn_analyze.pack(fill="x", pady=(0, 6))
        self.btn_process = self._button(
            box, "Reemplazar logos", self.start_processing, kind="primary"
        )
        self.btn_process.pack(fill="x")
        tk.Label(
            box,
            text="Los PDF originales no se modifican.",
            bg=BG,
            fg=MUTED,
            font=_font(8),
        ).pack(anchor="center", pady=(6, 0))

    def _build_preview(self, parent: tk.Widget) -> None:
        toolbar = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        toolbar.pack(fill="x", pady=(0, 10))
        toolbar_inner = tk.Frame(toolbar, bg=CARD)
        toolbar_inner.pack(fill="x", padx=12, pady=8)

        title_box = tk.Frame(toolbar_inner, bg=CARD)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="Vista previa",
            bg=CARD,
            fg=TEXT,
            font=_font(10, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.preview_info_label = tk.Label(
            title_box,
            textvariable=self.var_preview_info,
            bg=CARD,
            fg=MUTED,
            font=_font(8),
            anchor="w",
        )
        self.preview_info_label.pack(anchor="w")

        mode_box = tk.Frame(toolbar_inner, bg="#EEF2F7")
        mode_box.pack(side="right", padx=(10, 0))
        self.btn_before = tk.Button(
            mode_box,
            text="Antes",
            command=lambda: self.set_preview_mode("antes"),
            font=_font(8, bold=True),
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            bg=RED,
            fg="white",
            activebackground=RED_DARK,
            activeforeground="white",
        )
        self.btn_before.pack(side="left")
        self.btn_after = tk.Button(
            mode_box,
            text="Después",
            command=lambda: self.set_preview_mode("despues"),
            font=_font(8, bold=True),
            relief="flat",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            bg="#EEF2F7",
            fg=MUTED,
            activebackground="#E2E8F0",
            activeforeground=TEXT,
            state="disabled",
        )
        self.btn_after.pack(side="left")
        self.btn_detail = tk.Button(
            mode_box,
            text="Detalle",
            command=self.toggle_detail,
            font=_font(8, bold=True),
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            bg="#EEF2F7",
            fg=MUTED,
            activebackground="#E2E8F0",
            activeforeground=TEXT,
        )
        self.btn_detail.pack(side="left")

        nav = tk.Frame(toolbar_inner, bg=CARD)
        nav.pack(side="right", padx=(4, 8))
        self.btn_prev = self._button(
            nav, "‹", lambda: self.change_page(-1), kind="ghost", width=3
        )
        self.btn_prev.pack(side="left")
        self.page_spin = tk.Spinbox(
            nav,
            from_=1,
            to=1,
            textvariable=self.var_page,
            width=5,
            justify="center",
            font=_font(8),
            command=self._on_page_spin,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BLUE,
            relief="flat",
            bg="#FBFCFE",
        )
        self.page_spin.pack(side="left", padx=3)
        self.page_spin.bind("<Return>", lambda _e: self._on_page_spin())
        self.page_spin.bind("<FocusOut>", lambda _e: self._on_page_spin())
        self.page_total_label = tk.Label(
            nav, text="de 0", bg=CARD, fg=MUTED, font=_font(8)
        )
        self.page_total_label.pack(side="left", padx=(0, 3))
        self.btn_next = self._button(
            nav, "›", lambda: self.change_page(1), kind="ghost", width=3
        )
        self.btn_next.pack(side="left")

        self.preview_canvas = tk.Canvas(
            parent,
            bg="#E9EDF2",
            highlightthickness=0,
        )
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_canvas.bind("<Configure>", self._schedule_preview)

    def _build_log(self, parent: tk.Widget) -> None:
        card = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(10, 0))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=12, pady=9)

        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x")
        tk.Label(
            top, text="Registro", bg=CARD, fg=TEXT, font=_font(9, bold=True)
        ).pack(side="left")
        self.progress_label = tk.Label(
            top, text="", bg=CARD, fg=MUTED, font=_font(8)
        )
        self.progress_label.pack(side="left", padx=(10, 0))
        self.btn_cancel = self._button(
            top, "Cancelar", self.cancel_processing, kind="ghost"
        )
        self.btn_cancel.pack(side="right")
        self.btn_cancel.configure(state="disabled")

        text_frame = tk.Frame(inner, bg=LOG_BG)
        text_frame.pack(fill="both", expand=True, pady=(7, 7))
        self.log_text = tk.Text(
            text_frame,
            height=6,
            bg=LOG_BG,
            fg=LOG_TEXT,
            insertbackground=LOG_TEXT,
            font=_font(8, mono=True),
            relief="flat",
            bd=0,
            wrap="word",
            padx=8,
            pady=6,
            state="disabled",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.log_text.yview,
            style="App.Vertical.TScrollbar",
        )
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_configure("info", foreground="#CBD5E1")
        self.log_text.tag_configure("ok", foreground="#86EFAC")
        self.log_text.tag_configure("warn", foreground="#FCD34D")
        self.log_text.tag_configure("err", foreground="#FCA5A5")
        self.log_text.tag_configure("head", foreground="#FFFFFF")

        self.progress = ttk.Progressbar(
            inner,
            style="App.Horizontal.TProgressbar",
            mode="determinate",
            maximum=100,
        )
        self.progress.pack(fill="x")

    def _button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        kind: str = "secondary",
        width: int | None = None,
    ) -> tk.Button:
        if kind == "primary":
            bg, fg, active_bg, active_fg = RED, "white", RED_DARK, "white"
            font = _font(10, bold=True)
            pady = 9
        elif kind == "ghost":
            bg, fg, active_bg, active_fg = CARD, MUTED, "#EEF2F7", TEXT
            font = _font(8)
            pady = 5
        else:
            bg, fg, active_bg, active_fg = "#EEF2F7", TEXT, "#E2E8F0", TEXT
            font = _font(8, bold=True)
            pady = 6
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            disabledforeground="#9CA3AF",
            font=font,
            relief="flat",
            bd=0,
            padx=10,
            pady=pady,
            cursor="hand2",
            width=width,
            highlightthickness=0,
        )
        return btn

    def _set_app_icon(self) -> None:
        try:
            size = 64
            img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((2, 2, 61, 61), radius=12, fill="#FFFFFF")
            d.rectangle((2, 2, 61, 61), fill=None, outline="#E2E8F0", width=2)
            d.polygon(
                [(15, 40), (34, 16), (34, 30), (50, 30), (31, 55), (31, 40)],
                fill=RED,
            )
            d.line((15, 47, 49, 47), fill=BLUE, width=4)
            self._icon_photo = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Datos iniciales
    # ------------------------------------------------------------------

    def _load_defaults(self) -> None:
        base = app_dir()
        search_dirs = [base]
        bundled = resource_dir()
        if bundled != base:
            search_dirs.append(bundled)
        for folder in search_dirs:
            found = False
            for name in (
                "newlogo.jpg",
                "newlogo.png",
                "logo_nuevo.png",
                "logo_nuevo.jpg",
                "logo.png",
                "logo.jpg",
            ):
                candidate = folder / name
                if candidate.is_file():
                    try:
                        self._apply_logo(candidate, silent=True)
                        found = True
                        break
                    except Exception:
                        pass
            if found:
                break

        pdfs = find_pdfs(base)
        if len(pdfs) == 1:
            self.add_files([pdfs[0]], silent=True)

        if not self.var_output.get():
            if self.files:
                self._auto_output(self.files[0])
            else:
                self.var_output.set(str(base / "salida_logos"))
        self._append_log("Listo. Agrega tus PDF y verifica la vista previa.", "info")
        if self.logo:
            self._append_log(
                f"Logo cargado: {self.logo.path.name} ({self.logo.width} x {self.logo.height} px)",
                "ok",
            )

    def _auto_output(self, source: Path) -> None:
        if self._output_auto or not self.var_output.get().strip():
            self.var_output.set(str(source.parent / "salida_logos"))

    # ------------------------------------------------------------------
    # Archivos
    # ------------------------------------------------------------------

    def add_files(self, paths=None, silent: bool = False) -> None:
        if self.processing:
            return
        if paths is None:
            selected = filedialog.askopenfilenames(
                title="Selecciona uno o varios PDF",
                filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")],
            )
            if not selected:
                return
            paths = selected
        new_files: list[Path] = []
        for raw in paths:
            p = Path(raw).expanduser().resolve()
            if p.is_file() and p.suffix.lower() == ".pdf" and p not in self.files:
                new_files.append(p)
        if not new_files:
            return
        self.files.extend(new_files)
        if not self.current_source:
            self.current_source = new_files[0]
            self._auto_output(self.current_source)
        self._refresh_file_list(select=len(self.files) - len(new_files))
        self._append_log(
            f"Se agregaron {len(new_files)} PDF."
            if len(new_files) != 1
            else f"PDF agregado: {new_files[0].name}",
            "ok",
        )
        self._select_file(self.current_source)
        if not silent:
            self.var_status.set(f"{len(self.files)} archivos en la lista")

    def add_folder(self) -> None:
        if self.processing:
            return
        folder = filedialog.askdirectory(title="Selecciona la carpeta con los PDF")
        if not folder:
            return
        root = Path(folder).expanduser().resolve()
        pdfs = find_pdfs(root)
        if not pdfs:
            messagebox.showinfo(
                "Sin PDF",
                "No se encontraron archivos PDF en esa carpeta.",
                parent=self.root,
            )
            return
        self.add_files(pdfs)
        if self._output_auto:
            self.var_output.set(str(root / "salida_logos"))

    def remove_selected(self) -> None:
        if self.processing:
            return
        selected = list(self.file_list.curselection())
        if not selected:
            return
        for index in reversed(selected):
            if 0 <= index < len(self.files):
                self.files.pop(index)
        if self.current_source not in self.files:
            self.current_source = self.files[0] if self.files else None
        self.analysis = None
        self.preview_page = 0
        self._refresh_file_list()
        self._select_file(self.current_source)
        self._append_log("Se quitaron archivos de la lista.", "info")

    def _refresh_file_list(self, select: int | None = None) -> None:
        self.file_list.delete(0, tk.END)
        for i, path in enumerate(self.files):
            prefix = f"{i + 1:02d}  "
            self.file_list.insert(tk.END, prefix + path.name)
        self.var_file_count.set(
            f"{len(self.files)} archivo" if len(self.files) == 1 else f"{len(self.files)} archivos"
        )
        if select is not None and 0 <= select < len(self.files):
            self.file_list.selection_set(select)
            self.file_list.see(select)

    def _select_file(self, path: Path | None) -> None:
        if path is None:
            self.current_source = None
            self._clear_preview("Agrega un PDF para comenzar")
            return
        if path not in self.files:
            return
        index = self.files.index(path)
        self.file_list.selection_clear(0, tk.END)
        self.file_list.selection_set(index)
        self.file_list.see(index)
        self.current_source = path
        self.analysis = None
        self.preview_page = 0
        self._update_page_count()
        self._update_preview_info()
        self.set_preview_mode("antes", render=False)
        self.render_preview()

    def _on_file_select(self, _event=None) -> None:
        if self.processing:
            return
        selection = self.file_list.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.files):
            path = self.files[index]
            if path != self.current_source:
                self.current_source = path
                self.analysis = None
                self.preview_page = 0
                self._update_page_count()
                self._update_preview_info()
                self.set_preview_mode("antes", render=False)
                self.render_preview()

    # ------------------------------------------------------------------
    # Logo nuevo
    # ------------------------------------------------------------------

    def choose_logo(self) -> None:
        if self.processing:
            return
        path = filedialog.askopenfilename(
            title="Selecciona el logo nuevo",
            filetypes=[
                ("Imagenes PNG o JPG", "*.png *.jpg *.jpeg"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self._apply_logo(Path(path))
        except LogoEngineError as exc:
            messagebox.showerror("Logo no valido", str(exc), parent=self.root)

    def _apply_logo(self, path: Path, silent: bool = False) -> None:
        asset = load_logo_asset(path)
        self.logo = asset
        self.var_logo_info.set(f"{asset.path.name}\n{asset.width} x {asset.height} px")
        self._draw_logo_preview()
        if not silent:
            self._append_log(
                f"Logo nuevo: {asset.path.name} ({asset.width} x {asset.height} px)",
                "ok",
            )

    def _draw_logo_preview(self) -> None:
        canvas = getattr(self, "logo_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        if not self.logo:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Sin logo seleccionado",
                fill="#94A3B8",
                font=_font(8),
            )
            return
        try:
            with Image.open(self.logo.path) as im:
                im = im.convert("RGBA")
                scale = min((width - 20) / im.width, (height - 14) / im.height)
                scale = max(0.01, min(scale, 2.0))
                new_size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
                im = im.resize(new_size, Image.Resampling.LANCZOS)
                bg = Image.new("RGBA", (width, height), "white")
                bg.alpha_composite(im, ((width - im.width) // 2, (height - im.height) // 2))
                self.logo_photo = ImageTk.PhotoImage(bg.convert("RGB"))
                canvas.create_image(width / 2, height / 2, image=self.logo_photo)
        except Exception:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Vista previa no disponible",
                fill="#94A3B8",
                font=_font(8),
            )

    # ------------------------------------------------------------------
    # Opciones y vista previa
    # ------------------------------------------------------------------

    def _on_output_edited(self, _event=None) -> None:
        self._output_auto = False

    def choose_output_folder(self) -> None:
        if self.processing:
            return
        initial = self.var_output.get().strip() or str(app_dir() / "salida_logos")
        folder = filedialog.askdirectory(
            title="Carpeta de salida", initialdir=initial if Path(initial).exists() else None
        )
        if folder:
            self.var_output.set(folder)
            self._output_auto = False

    def _get_output_dir(self) -> Path:
        raw = self.var_output.get().strip()
        if not raw:
            raise LogoEngineError("Indica una carpeta de salida.")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if path.exists() and not path.is_dir():
            raise LogoEngineError("La ruta de salida es un archivo, no una carpeta.")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _scale_value(self) -> float:
        try:
            value = float(self.var_scale.get().replace(",", "."))
        except ValueError:
            value = 100.0
        return max(0.6, min(1.10, value / 100.0))

    def _update_page_count(self) -> None:
        path = self._preview_path()
        count = 0
        if path:
            try:
                doc = pymupdf.open(path)
                count = doc.page_count
                doc.close()
            except Exception:
                count = 0
        self.preview_page_count = count
        self.preview_page = min(self.preview_page, max(0, count - 1))
        self.var_page.set(str(self.preview_page + 1 if count else 1))
        self.page_total_label.configure(text=f"de {count}")
        self.page_spin.configure(from_=1, to=max(1, count))
        state = "normal" if count > 1 else "disabled"
        self.btn_prev.configure(state=state)
        self.btn_next.configure(state=state)
        self.page_spin.configure(state="normal" if count else "disabled")
        has_output = self.current_source is not None and str(self.current_source) in self.output_by_source
        self.btn_after.configure(state="normal" if has_output else "disabled")

    def _preview_path(self) -> Path | None:
        if not self.current_source:
            return None
        if self.preview_mode == "despues":
            return self.output_by_source.get(str(self.current_source))
        return self.current_source

    def _update_preview_info(self) -> None:
        if not self.current_source:
            self.var_preview_info.set("Agrega un PDF para comenzar")
            return
        if self.analysis and self.analysis.source == self.current_source:
            det = self.analysis
            self.var_preview_info.set(
                f"{det.pages_with_logo} páginas con logo  ·  {len(det.selected)} apariciones"
                f"  ·  {det.header_count} encabezado / {det.footer_count} pie"
            )
        elif self.preview_mode == "despues":
            self.var_preview_info.set("Resultado del archivo actual")
        else:
            self.var_preview_info.set(self.current_source.name)

    def set_preview_mode(self, mode: str, render: bool = True) -> None:
        if mode == "despues":
            if not self.current_source or str(self.current_source) not in self.output_by_source:
                return
        self.preview_mode = mode
        if mode == "antes":
            self.btn_before.configure(bg=RED, fg="white")
            self.btn_after.configure(bg="#EEF2F7", fg=MUTED)
        else:
            self.btn_after.configure(bg=RED, fg="white")
            self.btn_before.configure(bg="#EEF2F7", fg=MUTED)
        self._update_page_count()
        self._update_preview_info()
        if render:
            self.render_preview()

    def change_page(self, delta: int) -> None:
        if not self.preview_page_count:
            return
        self.preview_page = max(
            0, min(self.preview_page_count - 1, self.preview_page + delta)
        )
        self.var_page.set(str(self.preview_page + 1))
        self.render_preview()

    def _on_page_spin(self) -> None:
        try:
            value = int(float(self.var_page.get()))
        except ValueError:
            return
        value = max(1, min(max(1, self.preview_page_count), value))
        self.preview_page = value - 1
        self.var_page.set(str(value))
        self.render_preview()

    def _schedule_preview(self, _event=None) -> None:
        if self._preview_job:
            try:
                self.root.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.root.after(140, self.render_preview)

    def _clear_preview(self, message: str) -> None:
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 200)
        height = max(canvas.winfo_height(), 200)
        canvas.create_text(
            width / 2,
            height / 2 - 10,
            text=message,
            fill="#64748B",
            font=_font(10, bold=True),
        )
        canvas.create_text(
            width / 2,
            height / 2 + 14,
            text="PDF  ·  vista de página",
            fill="#94A3B8",
            font=_font(8),
        )
        self._preview_job = None

    def toggle_detail(self) -> None:
        self.detail_mode = not self.detail_mode
        self.btn_detail.configure(
            bg=RED if self.detail_mode else "#EEF2F7",
            fg="white" if self.detail_mode else MUTED,
        )
        self.render_preview()

    def _render_detail(self, page: pymupdf.Page, doc: pymupdf.Document) -> Image.Image:
        page_rect = page.rect
        width = min(page_rect.width, max(360.0, page_rect.width * 0.62))
        strip_h = min(80.0, page_rect.height * 0.17)
        header_clip = pymupdf.Rect(0, 0, width, strip_h)
        footer_clip = pymupdf.Rect(
            0, max(0, page_rect.height - strip_h), width, page_rect.height
        )
        zoom = 2.35
        header = self._clip_to_image(page, header_clip, zoom)
        footer = self._clip_to_image(page, footer_clip, zoom)
        if self.preview_mode == "antes":
            self._draw_strip_boxes(header, page, doc, header_clip, zoom)
            self._draw_strip_boxes(footer, page, doc, footer_clip, zoom)

        label_h = 24
        gap = 12
        canvas_w = max(header.width, footer.width)
        result = Image.new(
            "RGB",
            (canvas_w, label_h + header.height + gap + label_h + footer.height),
            (233, 237, 242),
        )
        draw = ImageDraw.Draw(result)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
        except Exception:
            font = ImageFont.load_default()
        draw.rectangle([0, 0, canvas_w, label_h - 1], fill=(226, 232, 240))
        draw.text((8, 4), "ENCABEZADO", fill=(71, 85, 105), font=font)
        y_footer_label = label_h + header.height + gap
        draw.rectangle(
            [0, y_footer_label, canvas_w, y_footer_label + label_h - 1],
            fill=(226, 232, 240),
        )
        draw.text((8, y_footer_label + 4), "PIE DE PÁGINA", fill=(71, 85, 105), font=font)
        result.paste(header, (0, label_h))
        result.paste(footer, (0, y_footer_label + label_h))
        return result

    def _clip_to_image(
        self, page: pymupdf.Page, clip: pymupdf.Rect, zoom: float
    ) -> Image.Image:
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False
        )
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def _draw_strip_boxes(
        self,
        img: Image.Image,
        page: pymupdf.Page,
        doc: pymupdf.Document,
        clip: pymupdf.Rect,
        zoom: float,
    ) -> None:
        if not self.analysis or self.analysis.source != self.current_source:
            return
        if self.analysis.page_count != doc.page_count:
            return
        draw = ImageDraw.Draw(img)
        for placement in self.analysis.selected:
            if placement.page != self.preview_page:
                continue
            x0, y0, x1, y1 = placement.bbox
            if y1 < clip.y0 or y0 > clip.y1:
                continue
            rect = [
                (x0 - clip.x0) * zoom,
                (y0 - clip.y0) * zoom,
                (x1 - clip.x0) * zoom,
                (y1 - clip.y0) * zoom,
            ]
            draw.rectangle(rect, outline=(228, 0, 43), width=3)

    def render_preview(self) -> None:
        self._preview_job = None
        canvas = self.preview_canvas
        path = self._preview_path()
        if not path:
            if self.current_source and self.preview_mode == "despues":
                self._clear_preview("Procesa el archivo para ver el resultado")
            else:
                self._clear_preview("Agrega un PDF para comenzar")
            return
        try:
            doc = pymupdf.open(path)
            if doc.page_count == 0:
                doc.close()
                self._clear_preview("El PDF no tiene páginas")
                return
            self.preview_page = max(0, min(doc.page_count - 1, self.preview_page))
            page = doc[self.preview_page]
            if self.detail_mode:
                img = self._render_detail(page, doc)
            else:
                zoom = 1.45
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                if self.preview_mode == "antes":
                    self._draw_detection_boxes(img, page, doc)
            doc.close()
        except Exception as exc:
            self._clear_preview("No se pudo mostrar la vista previa")
            self._append_log(f"No se pudo renderizar {path.name}: {exc}", "err")
            return

        cw = max(canvas.winfo_width(), 100)
        ch = max(canvas.winfo_height(), 100)
        margin = 24
        scale = min((cw - margin * 2) / img.width, (ch - margin * 2) / img.height, 1.0)
        scale = max(0.05, scale)
        new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        if new_size != img.size:
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        x = (cw - img.width) / 2
        y = (ch - img.height) / 2

        canvas.delete("all")
        canvas.create_rectangle(
            x + 5,
            y + 5,
            x + img.width + 5,
            y + img.height + 5,
            fill="#D5DCE5",
            outline="",
        )
        canvas.create_rectangle(
            x - 1,
            y - 1,
            x + img.width + 1,
            y + img.height + 1,
            fill="#FFFFFF",
            outline="#CBD5E1",
        )
        self.preview_photo = ImageTk.PhotoImage(img)
        canvas.create_image(x, y, image=self.preview_photo, anchor="nw")

    def _draw_detection_boxes(
        self, img: Image.Image, page: pymupdf.Page, doc: pymupdf.Document
    ) -> None:
        if not self.analysis or self.analysis.source != self.current_source:
            return
        if self.analysis.page_count != doc.page_count:
            return
        page_rect = page.rect
        if page_rect.width <= 0 or page_rect.height <= 0:
            return
        sx = img.width / page_rect.width
        sy = img.height / page_rect.height
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", max(11, int(12 * sx)))
        except Exception:
            font = ImageFont.load_default()
        for placement in self.analysis.selected:
            if placement.page != self.preview_page:
                continue
            x0, y0, x1, y1 = placement.bbox
            rect = [x0 * sx, y0 * sy, x1 * sx, y1 * sy]
            draw.rectangle(rect, outline=(228, 0, 43), width=max(2, int(2 * sx)))
            label = "logo antiguo"
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            lx = rect[0]
            ly = rect[1] - th - 8
            if ly < 2:
                ly = rect[3] + 3
            draw.rectangle([lx, ly, lx + tw + 10, ly + th + 6], fill=(228, 0, 43))
            draw.text((lx + 5, ly + 2), label, fill="white", font=font)

    # ------------------------------------------------------------------
    # Analisis
    # ------------------------------------------------------------------

    def _selected_or_first(self) -> Path | None:
        selection = self.file_list.curselection()
        if selection and 0 <= selection[0] < len(self.files):
            return self.files[selection[0]]
        return self.current_source or (self.files[0] if self.files else None)

    def analyze_selected(self) -> None:
        if self.processing:
            return
        if not self.files:
            messagebox.showinfo(
                "Falta un PDF",
                "Agrega al menos un archivo PDF para analizar.",
                parent=self.root,
            )
            return
        if not self.logo:
            messagebox.showinfo(
                "Falta el logo",
                "Selecciona primero la imagen del logo nuevo.",
                parent=self.root,
            )
            return
        source = self._selected_or_first()
        if not source:
            return
        self.current_source = source
        self._select_file(source)
        self.var_status.set("Analizando el PDF...")
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            doc = pymupdf.open(source)
            if doc.needs_pass:
                doc.close()
                raise PdfEncryptedError(
                    "El PDF está protegido con contraseña. Quita la protección antes de procesarlo."
                )
            try:
                detection = detect_logo(doc, include_footer=self.var_footer.get())
            finally:
                doc.close()
            detection.source = source
            self.analysis = detection
            self.preview_page = 0
            self.set_preview_mode("antes", render=False)
            self._update_page_count()
            self._update_preview_info()
            self.render_preview()
            self._append_log(
                f"Análisis: {len(detection.selected)} apariciones en "
                f"{detection.pages_with_logo} páginas "
                f"({detection.header_count} encabezado / {detection.footer_count} pie).",
                "ok",
            )
            for warning in detection.warnings:
                self._append_log("Aviso: " + warning, "warn")
            self.var_status.set(
                f"Listo para reemplazar: {len(detection.selected)} apariciones detectadas"
            )
        except (LogoNotFoundError, PdfEncryptedError, LogoEngineError) as exc:
            self.analysis = None
            self._append_log("No se pudo analizar: " + str(exc), "err")
            self.var_status.set("No se detectó el logo")
            messagebox.showwarning("No se detectó el logo", str(exc), parent=self.root)
        except Exception as exc:
            self.analysis = None
            self._append_log("Error al analizar: " + str(exc), "err")
            self.var_status.set("Error de análisis")
            messagebox.showerror("Error al analizar", str(exc), parent=self.root)
        finally:
            self.root.config(cursor="")
            self.root.update_idletasks()

    # ------------------------------------------------------------------
    # Procesamiento por lotes
    # ------------------------------------------------------------------

    def start_processing(self) -> None:
        if self.processing:
            return
        if not self.files:
            messagebox.showinfo(
                "Falta un PDF",
                "Agrega al menos un archivo PDF para procesar.",
                parent=self.root,
            )
            return
        if not self.logo:
            messagebox.showinfo(
                "Falta el logo",
                "Selecciona primero la imagen del logo nuevo.",
                parent=self.root,
            )
            return
        try:
            output_dir = self._get_output_dir()
        except Exception as exc:
            messagebox.showerror("Carpeta no válida", str(exc), parent=self.root)
            return
        self.var_output.set(str(output_dir))

        scale = self._scale_value()
        include_footer = bool(self.var_footer.get())
        files = list(self.files)
        logo = self.logo
        self.processing = True
        self.cancel_event.clear()
        self.last_results = []
        self.last_errors = []
        self.last_report = None
        self._set_busy(True)
        self.progress.configure(value=0)
        self.progress_label.configure(text="Preparando...")
        self.var_status.set("Procesando...")
        self._append_log(
            f"Inicio del lote: {len(files)} PDF, escala {int(scale * 100)}%, "
            f"{'encabezado y pie' if include_footer else 'solo encabezado'}.",
            "head",
        )
        self.worker = threading.Thread(
            target=self._worker,
            args=(files, output_dir, logo, include_footer, scale),
            daemon=True,
        )
        self.worker.start()

    def _worker(
        self,
        files: list[Path],
        output_dir: Path,
        logo: LogoAsset,
        include_footer: bool,
        scale: float,
    ) -> None:
        rows: list[ReplaceResult] = []
        errors: list[tuple[Path, str]] = []
        start = time.perf_counter()
        total = len(files)
        for index, source in enumerate(files):
            if self.cancel_event.is_set():
                self.message_queue.put(("canceled", index))
                break
            self.message_queue.put(("file_start", index, total, source))
            try:
                output = unique_output_path(source, output_dir)
                result = replace_pdf(
                    source,
                    output,
                    logo,
                    include_footer=include_footer,
                    scale=scale,
                    verify=True,
                    progress=lambda pno, pages, _msg, i=index, s=source: self.message_queue.put(
                        ("progress", i, total, pno, pages, s.name)
                    ),
                    cancel=self.cancel_event.is_set,
                )
                rows.append(result)
                self.message_queue.put(("file_done", index, result))
            except Exception as exc:
                if self.cancel_event.is_set():
                    self.message_queue.put(("canceled", index))
                    break
                errors.append((source, str(exc)))
                self.message_queue.put(("file_error", index, total, source, str(exc)))
        report_path = None
        if rows or errors:
            try:
                report_path = self._write_report(rows, errors, output_dir)
            except Exception:
                report_path = None
        elapsed = time.perf_counter() - start
        self.message_queue.put(
            (
                "done",
                {
                    "rows": rows,
                    "errors": errors,
                    "report": report_path,
                    "elapsed": elapsed,
                    "canceled": self.cancel_event.is_set(),
                },
            )
        )

    def _write_report(
        self,
        rows: list[ReplaceResult],
        errors: list[tuple[Path, str]],
        output_dir: Path,
    ) -> Path:
        path = output_dir / "reporte_reemplazo.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(
                [
                    "Archivo",
                    "Salida",
                    "Páginas",
                    "Apariciones",
                    "Encabezado",
                    "Pie",
                    "Estado",
                    "Imagen antigua eliminada",
                    "Advertencias",
                    "Segundos",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.source.name,
                        row.output.name,
                        row.page_count,
                        row.replacements,
                        row.header_replacements,
                        row.footer_replacements,
                        "OK" if row.verified else "REVISAR",
                        "Sí" if row.old_removed else "No",
                        " | ".join(row.warnings),
                        f"{row.elapsed:.2f}",
                    ]
                )
            for source, error in errors:
                writer.writerow(
                    [source.name, "", "", "", "", "", "ERROR", "No", error, ""]
                )
        return path

    # ------------------------------------------------------------------
    # Cola de mensajes / estado
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self.message_queue.get_nowait()
                kind = message[0]
                if kind == "file_start":
                    _, index, total, source = message
                    self.progress_label.configure(
                        text=f"Archivo {index + 1} de {total}: {source.name}"
                    )
                    self.var_status.set(
                        f"Procesando {index + 1} de {total}: {source.name}"
                    )
                elif kind == "progress":
                    _, index, total, pno, pages, name = message
                    fraction = (index + (pno / max(pages, 1))) / max(total, 1)
                    self.progress.configure(value=max(0, min(100, fraction * 100)))
                    self.progress_label.configure(
                        text=f"{index + 1}/{total}  ·  {name}  ·  página {pno}/{pages}"
                    )
                elif kind == "file_done":
                    _, _index, result = message
                    self.output_by_source[str(result.source)] = result.output
                    self.last_results.append(result)
                    self._append_log(
                        f"OK  {result.source.name}: {result.replacements} logos en "
                        f"{result.page_count} páginas ({result.elapsed:.1f} s).",
                        "ok",
                    )
                    for warning in result.warnings:
                        self._append_log("Aviso: " + warning, "warn")
                    if not self.current_source:
                        self.current_source = result.source
                elif kind == "file_error":
                    _, index, total, source, text = message
                    self.last_errors.append((source, text))
                    self._append_log(f"ERROR  {source.name}: {text}", "err")
                    fraction = (index + 1) / max(total, 1)
                    self.progress.configure(value=max(0, min(100, fraction * 100)))
                elif kind == "canceled":
                    self._append_log("Proceso cancelado por el usuario.", "warn")
                elif kind == "done":
                    _, summary = message
                    self._finish_processing(summary)
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_queue)

    def _finish_processing(self, summary: dict) -> None:
        self.processing = False
        self._set_busy(False)
        self.progress.configure(value=100 if self.last_results else 0)
        rows: list[ReplaceResult] = summary.get("rows", [])
        errors: list[tuple[Path, str]] = summary.get("errors", [])
        canceled = bool(summary.get("canceled"))
        elapsed = float(summary.get("elapsed", 0))
        self.last_report = summary.get("report")
        self.progress_label.configure(
            text=f"{len(rows)} archivos procesados  ·  {elapsed:.1f} s"
        )
        total_logos = sum(r.replacements for r in rows)
        if self.last_results:
            first = self.last_results[0]
            self.current_source = first.source
            if first.source in self.files:
                index = self.files.index(first.source)
                self.file_list.selection_clear(0, tk.END)
                self.file_list.selection_set(index)
                self.file_list.see(index)
            self.preview_page = 0
            self.preview_mode = "despues"
            self.btn_after.configure(state="normal")
            self.set_preview_mode("despues", render=False)
            self._update_page_count()
            self._update_preview_info()
            self.render_preview()
        if canceled:
            self.var_status.set("Proceso cancelado")
        else:
            self.var_status.set(
                f"Listo: {len(rows)} archivos  ·  {total_logos} logos reemplazados"
            )

        if rows:
            self._append_log(
                f"Lote terminado: {len(rows)} archivos, {total_logos} logos, "
                f"{len(errors)} errores, {elapsed:.1f} s.",
                "head",
            )
        else:
            self._append_log("No se generó ningún archivo.", "err")
        if self.last_report:
            self._append_log(f"Reporte: {self.last_report}", "info")

        if self.var_open_folder.get() and rows and self.var_output.get().strip():
            self._open_folder(Path(self.var_output.get().strip()))

        if canceled:
            message = (
                f"Proceso cancelado.\n\n"
                f"Archivos generados antes de cancelar: {len(rows)}\n"
                f"Errores: {len(errors)}"
            )
            messagebox.showinfo("Proceso cancelado", message, parent=self.root)
        elif errors and not rows:
            detalle = "\n".join(f"· {p.name}: {e}" for p, e in errors[:4])
            messagebox.showerror(
                "No se pudo procesar",
                "Ningún PDF se pudo procesar.\n\n" + detalle,
                parent=self.root,
            )
        elif rows:
            detalle = (
                f"Archivos procesados: {len(rows)}\n"
                f"Logos reemplazados: {total_logos}\n"
                f"Errores: {len(errors)}\n"
                f"Tiempo: {elapsed:.1f} s"
            )
            if self.last_report:
                detalle += f"\n\nReporte:\n{self.last_report}"
            if errors:
                detalle += "\n\nRevisa el registro para ver los archivos con error."
            messagebox.showinfo("Reemplazo terminado", detalle, parent=self.root)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in (
            self.btn_add,
            self.btn_folder,
            self.btn_remove,
            self.btn_logo,
            self.btn_analyze,
            self.btn_process,
            self.btn_output,
        ):
            button.configure(state=state)
        self.file_list.configure(state=state)
        self.chk_footer.configure(state=state)
        self.chk_open.configure(state=state)
        self.spin_scale.configure(state=state)
        self.entry_output.configure(state=state)
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _append_log(self, text: str, tag: str = "info") -> None:
        self.log_text.configure(state="normal")
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{stamp}] ", "info")
        self.log_text.insert(tk.END, text + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def cancel_processing(self) -> None:
        if not self.processing:
            return
        self.cancel_event.set()
        self.btn_cancel.configure(state="disabled")
        self.progress_label.configure(text="Cancelando...")
        self.var_status.set("Cancelando el lote...")
        self._append_log("Solicitud de cancelación recibida.", "warn")

    def _open_folder(self, folder: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["open", str(folder)])
            else:
                import subprocess

                subprocess.Popen(["xdg-open", str(folder)])
        except Exception:
            pass

    def _on_close(self) -> None:
        if self.processing:
            if not messagebox.askyesno(
                "Proceso en curso",
                "Todavía se están generando archivos. ¿Cancelar y cerrar?",
                parent=self.root,
            ):
                return
            self.cancel_event.set()
        self.root.destroy()


def main() -> int:
    enable_windows_dpi_awareness()
    root = tk.Tk()
    LogoReplacerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
