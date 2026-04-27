import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import random
import os
import threading
import time
import win32gui
import win32con
from bot import MiningBot
from drag_drop_list import DragDropList, OreList
import ctypes
from ctypes import wintypes
import psutil
from PIL import Image, ImageTk

WM_HOTKEY = 0x0312
VK_F6 = 0x75

# ── Theme Presets ─────────────────────────────────────────────────────────────
THEMES = {
    'RS-Classic': {
        'BG': '#000000', 'SURFACE': '#0c0c00', 'BORDER': '#333300',
        'FG': '#ffff00', 'MUTED': '#c8c800', 'ACCENT': '#ffcc00',
        'GREEN': '#00ff00', 'RED': '#ff0000', 'AMBER': '#ffff00',
        'TITLE_BG': '#000000',
    },
    'Default': {
        'BG': '#0d0d0f', 'SURFACE': '#16161a', 'BORDER': '#2a2a32',
        'FG': '#e2e2e8', 'MUTED': '#9e9eab', 'ACCENT': '#ff6b7a',
        'GREEN': '#4ade80', 'RED': '#ff6b6b', 'AMBER': '#4ade80',
        'TITLE_BG': '#080808',
    },
    'White + Light Blue': {
        'BG': '#eef2f7', 'SURFACE': '#ffffff', 'BORDER': '#b8c9dc',
        'FG': '#1a1a2e', 'MUTED': '#5a6378', 'ACCENT': '#2980b9',
        'GREEN': '#27ae60', 'RED': '#c0392b', 'AMBER': '#f39c12',
        'TITLE_BG': '#d5dfe9',
    },
    'Magenta + Black': {
        'BG': '#0a0008', 'SURFACE': '#180818', 'BORDER': '#3d1540',
        'FG': '#f0c8f4', 'MUTED': '#a068a8', 'ACCENT': '#ff44ff',
        'GREEN': '#00e87b', 'RED': '#ff3368', 'AMBER': '#ff8800',
        'TITLE_BG': '#060006',
    },
    'Red + Black': {
        'BG': '#0a0000', 'SURFACE': '#1a0808', 'BORDER': '#3d1a1a',
        'FG': '#f0c8c8', 'MUTED': '#a07070', 'ACCENT': '#ff3333',
        'GREEN': '#4ade80', 'RED': '#ff4444', 'AMBER': '#ff8800',
        'TITLE_BG': '#060000',
    },
    'Green + Black': {
        'BG': '#000a00', 'SURFACE': '#081808', 'BORDER': '#1a3d1a',
        'FG': '#c8f0c8', 'MUTED': '#70a070', 'ACCENT': '#33ff66',
        'GREEN': '#33ff66', 'RED': '#ff4444', 'AMBER': '#88ff00',
        'TITLE_BG': '#000600',
    },
}
FONT_CHOICES = ['Consolas', 'Segoe UI', 'Courier New', 'Fixedsys']

def _load_active_theme():
    global BG, SURFACE, BORDER, FG, MUTED, ACCENT, GREEN, RED, AMBER, TITLE_BG, FONT_UI, FONT_HDR
    theme_name = 'RS-Classic'
    font_name = 'Consolas'
    if os.path.exists('config.json'):
        try:
            with open('config.json', 'r') as f:
                cfg = json.load(f)
            theme_name = cfg.get('theme', 'RS-Classic')
            font_name = cfg.get('font', 'Consolas')
        except Exception:
            pass
    t = THEMES.get(theme_name, THEMES.get('RS-Classic', THEMES['Default']))
    BG       = t['BG']
    SURFACE  = t['SURFACE']
    BORDER   = t['BORDER']
    FG       = t['FG']
    MUTED    = t['MUTED']
    ACCENT   = t['ACCENT']
    GREEN    = t['GREEN']
    RED      = t['RED']
    AMBER    = t['AMBER']
    TITLE_BG = t['TITLE_BG']
    if font_name not in FONT_CHOICES:
        font_name = 'Consolas'
    FONT_UI  = (font_name, 9)
    FONT_HDR = (font_name, 10, 'bold')

_load_active_theme()


def card(parent, **kw):
    outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    inner = tk.Frame(outer, bg=SURFACE, **kw)
    inner.pack(fill='both', expand=True)
    return outer, inner


def section_label(parent, text):
    tk.Label(parent, text=text.upper(), bg=SURFACE, fg=ACCENT,
             font=('Segoe UI', 9, 'bold'), pady=4).pack(anchor='w', padx=8)
    tk.Frame(parent, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(0, 6))


class Toggle(tk.Canvas):
    """Pill-style iOS toggle switch backed by a BooleanVar."""

    W, H, R = 36, 18, 9  # pill width, height, circle radius

    def __init__(self, parent, variable, bg=None, **kw):
        bg = bg or SURFACE
        super().__init__(parent, width=self.W, height=self.H,
                         bg=bg, highlightthickness=0, cursor='hand2', **kw)
        self._var = variable
        self._disabled = False
        self._draw()
        self.bind('<Button-1>', self._toggle)
        variable.trace_add('write', lambda *_: self._draw())

    def _draw(self):
        self.delete('all')
        on = self._var.get()
        if self._disabled:
            track = '#3a3a3a'
            knob  = '#5a5a5a'
        else:
            track = GREEN if on else BORDER
            knob  = '#ffffff'
        # Track pill
        r = self.H // 2
        self.create_oval(0, 0, self.H, self.H, fill=track, outline='')
        self.create_oval(self.W - self.H, 0, self.W, self.H, fill=track, outline='')
        self.create_rectangle(r, 0, self.W - r, self.H, fill=track, outline='')
        # Knob
        pad = 2
        kx = self.W - self.H + pad if on else pad
        self.create_oval(kx, pad, kx + self.H - 2*pad, self.H - pad,
                         fill=knob, outline='')

    def _toggle(self, _=None):
        if self._disabled:
            return
        self._var.set(not self._var.get())

    def set_disabled(self, disabled: bool):
        self._disabled = disabled
        self.configure(cursor='arrow' if disabled else 'hand2')
        self._draw()


def toggle_row(parent, text, variable, bg=None):
    """Helper: renders  [Toggle]  Label  in a horizontal row."""
    bg = bg or SURFACE
    row = tk.Frame(parent, bg=bg)
    Toggle(row, variable, bg=bg).pack(side='left', padx=(0, 8))
    tk.Label(row, text=text, bg=bg, fg=FG,
             font=FONT_UI, anchor='w').pack(side='left', fill='x', expand=True)
    return row


class MiningBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('RSC MultiMiner V1.1')
        self.root.geometry('660x680')
        self.root.minsize(580, 560)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.on_closing)

        # Window icon (pickaxe)
        _icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
        try:
            _ico_img = Image.open(os.path.join(_icons_dir, 'Rune_Pickaxe.png'))
            self._app_icon = ImageTk.PhotoImage(_ico_img)
            self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self.bot = None
        self.bot_thread = None
        self.running = False
        self.obtain_count = 0
        self.ore_count = 0
        self._overlay_win = None
        self._overlay_label = None
        self._overlay_canvas = None
        self._overlay_canvas_item = None
        self._overlay_photo = None
        self._det_seen_at = {}  # smoothing: key -> (det, timestamp)

        self.load_config()
        self._build_styles()
        self._build_ui()

        self.start_hotkey_listener()

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self):
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                'window_title': 'RScrevolution',
                'ore_checkboxes': {},
                'show_empty_ore': False,
                'priority_order': [],
                'break_settings': {},
                'mouse_settings': {},
                'model_settings': {'use_main_model': True, 'use_adamantite_model': False},
                'detection_settings': {
                    'confidence_threshold': 0.75,
                    'update_interval_ms': 200,
                    'no_ore_retry_delay_ms': 500,
                },
                'powermine_enabled': False,
                'fatigue_detection_enabled': True,
            }

    def save_config(self):
        self.config['window_title'] = self._title_from_display(self.window_var.get())
        self.config['show_empty_ore'] = self.show_empty_var.get()
        for ore, var in self.checkbox_vars.items():
            self.config['ore_checkboxes'][ore] = var.get()
        self.config['priority_order'] = self.ore_list.get_priority_order()
        self.config['break_settings'] = {
            'breaks_enabled':              self.breaks_enabled_var.get(),
            'min_seconds_between_breaks':  int(self.min_break_interval_var.get()) * 60,
            'max_seconds_between_breaks':  int(self.max_break_interval_var.get()) * 60,
            'min_break_duration_seconds':  int(self.min_break_duration_var.get()) * 60,
            'max_break_duration_seconds':  int(self.max_break_duration_var.get()) * 60,
            'micro_breaks_enabled':        self.micro_breaks_enabled_var.get(),
            'micro_break_min_ms':          int(self.micro_break_min_var.get()),
            'micro_break_max_ms':          int(self.micro_break_max_var.get()),
        }
        try:
            self.config['mouse_settings'] = {
                'min_delay_ms':         int(self.min_delay_var.get()),
                'max_delay_ms':         int(self.max_delay_var.get()),
                'human_curve_strength': float(self.human_curve_var.get()),
                'mouse_seed':           int(self.mouse_seed_var.get()) if hasattr(self, 'mouse_seed_var') else None,
            }
        except Exception:
            pass
        self.config['model_settings'] = {
            'use_main_model':       self.main_model_var.get(),
            'use_adamantite_model': False,
        }
        try:
            det = self.config.get('detection_settings', {}) or {}
            det['confidence_threshold'] = float(self.confidence_var.get())
            self.config['detection_settings'] = det
        except Exception:
            pass
        self.config['overlay_box_thickness'] = self.overlay_thickness_var.get()
        self.config['antiban_master_enabled'] = (
            self.antiban_master_var.get() if hasattr(self, 'antiban_master_var') else True)
        self.config['antiban_failsafe_enabled'] = (
            self.antiban_failsafe_var.get() if hasattr(self, 'antiban_failsafe_var') else True)
        self.config['powermine_enabled'] = self.powermine_var.get()
        self.config['fatigue_detection_enabled'] = self.fatigue_detection_var.get()
        if hasattr(self, 'teleport_detect_var'):
            self.config['teleport_detection_enabled'] = self.teleport_detect_var.get()
            try:
                self.config['teleport_threshold'] = int(self.teleport_thresh_var.get())
            except (ValueError, tk.TclError, AttributeError):
                pass
        if hasattr(self, 'teleport_reactions_var'):
            self.config['teleport_reactions_text'] = self.teleport_reactions_var.get()
        if hasattr(self, 'teleport_pick_random_var'):
            self.config['teleport_pick_random'] = bool(self.teleport_pick_random_var.get())
        self.config['verbose_debug'] = self.verbose_debug_var.get()
        _spd = self.mining_speed_var.get()
        self.config['speed_mode'] = _spd
        self.config['fast_mining_enabled'] = (_spd == 'fast')
        self.config['lazy_idle_pause_enabled'] = self.lazy_idle_pause_var.get()
        self.config['hover_mode_enabled'] = self.hover_mode_var.get()
        self.config['camera_rotation_enabled'] = self.camera_rotation_var.get()
        self.config['fixed_ore_spots'] = self._fixed_spots
        self.config['stop_on_full_inventory'] = self.stop_on_full_var.get()
        self.config['overlay_mode'] = self.overlay_mode_var.get()
        self.config['mouse_outside_window'] = self.mouse_outside_var.get()
        self.config['window_brightness'] = self._brightness_var.get() if hasattr(self, '_brightness_var') else 100
        if hasattr(self, 'autologin_var'):
            self.config['autologin_enabled'] = self.autologin_var.get()
        if hasattr(self, 'mod_crown_var'):
            self.config['mod_crown_detection_enabled'] = self.mod_crown_var.get()
        if hasattr(self, 'chat_text_stop_var'):
            self.config['chat_text_stop_enabled'] = self.chat_text_stop_var.get()
            raw = self.chat_text_phrases_var.get() if hasattr(self, 'chat_text_phrases_var') else ''
            phrases = [p.strip().lower() for p in raw.split(',') if p.strip()]
            self.config['chat_text_stop_phrases'] = phrases
        if hasattr(self, 'walkto_enabled_var'):
            self.config['walkto_enabled'] = self.walkto_enabled_var.get()
        if hasattr(self, 'walkto_min_var'):
            try:
                self.config['walkto_min_clicks'] = int(self.walkto_min_var.get())
            except Exception:
                pass
        if hasattr(self, 'walkto_max_var'):
            try:
                self.config['walkto_max_clicks'] = int(self.walkto_max_var.get())
            except Exception:
                pass
        if hasattr(self, 'walkto_dest_var'):
            self.config['walkto_destination'] = self.walkto_dest_var.get().strip()
        if hasattr(self, 'multi_client_var'):
            self.config['multi_client_mode'] = self.multi_client_var.get()
        if hasattr(self, 'theme_var'):
            self.config['theme'] = self.theme_var.get()
        if hasattr(self, 'font_var'):
            self.config['font'] = self.font_var.get()
        # Atomic write: dump to temp then replace, so Google Drive sync / concurrent
        # writers can't leave a half-written config.json on disk.
        import os, tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(prefix='config_', suffix='.json', dir='.')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(self.config, f, indent=4)
            os.replace(tmp_path, 'config.json')
        except Exception:
            try: os.unlink(tmp_path)
            except Exception: pass
            raise

    def get_java_windows(self):
        """Return list of display strings for Java windows; populates self._window_info_map."""
        self._window_info_map = {}  # display_str -> dict(title, pid, hwnd, pos_label)
        entries = []
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        def _pos_label(x, y, w, h):
            cx, cy = x + w // 2, y + h // 2
            vert  = 'Top'    if cy < sh * 0.4 else ('Bottom' if cy > sh * 0.6 else 'Center')
            horiz = 'Left'   if cx < sw * 0.4 else ('Right'  if cx > sw * 0.6 else '')
            return (vert + horiz).strip() or 'Center'

        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] not in ('javaw.exe', 'java.exe'):
                        continue
                    pid = proc.info['pid']
                    hwnd_list = []

                    def _enum(hwnd, _ctx, _pid=pid):
                        if win32gui.IsWindowVisible(hwnd):
                            try:
                                dpid = ctypes.wintypes.DWORD()
                                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dpid))
                                if dpid.value == _pid:
                                    hwnd_list.append(hwnd)
                            except Exception:
                                pass
                        return True

                    win32gui.EnumWindows(_enum, None)
                    for hwnd in hwnd_list:
                        title = win32gui.GetWindowText(hwnd)
                        if not title:
                            continue
                        # Detect minimized: IsIconic + the (-32000,-32000) sentinel.
                        try:
                            minimized = bool(win32gui.IsIconic(hwnd))
                        except Exception:
                            minimized = False
                        try:
                            rect = win32gui.GetWindowRect(hwnd)
                            x, y, x2, y2 = rect
                            w, h = x2 - x, y2 - y
                            if x <= -30000 or y <= -30000:
                                minimized = True
                            if minimized:
                                pos = 'Minimized'
                                sz = '—'
                            else:
                                pos = _pos_label(x, y, w, h)
                                sz = f'{w}×{h}'
                        except Exception:
                            pos, sz = ('Minimized' if minimized else '?'), '—'
                        display = f'{title}  |  PID {pid}  |  {pos}  |  {sz}'
                        if display not in self._window_info_map:
                            self._window_info_map[display] = {
                                'title': title, 'pid': pid, 'hwnd': hwnd,
                                'pos': pos, 'size': sz, 'minimized': minimized,
                            }
                            entries.append(display)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f'[WIN] Error scanning windows: {e}')

        if not entries:
            fallback = 'RScrevolution  |  PID ?  |  ?  |  ?'
            self._window_info_map[fallback] = {'title': 'RScrevolution', 'pid': None,
                                               'hwnd': None, 'pos': '?', 'size': '?'}
            entries = [fallback]
        return entries

    def _title_from_display(self, display_str):
        """Extract window title from a display string (or return it verbatim as fallback)."""
        info = self._window_info_map.get(display_str)
        return info['title'] if info else display_str.split('  |  ')[0]

    # ── Style ─────────────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('TFrame',      background=BG)
        s.configure('TLabel',      background=SURFACE, foreground=FG, font=FONT_UI)
        # Toggle-style checkbuttons: rounded look, teal when selected
        s.configure('TCheckbutton',
                    background=SURFACE, foreground=FG, font=FONT_UI,
                    indicatorcolor=BORDER, indicatorrelief='flat',
                    indicatormargin=4, selectcolor=GREEN)
        s.map('TCheckbutton',
              background=[('active', SURFACE)],
              foreground=[('active', FG)],
              indicatorcolor=[('selected', GREEN), ('!selected', BORDER)])
        s.configure('TEntry',
                    fieldbackground=TITLE_BG, foreground=FG,
                    insertcolor=FG, font=FONT_UI, padding=3, relief='flat')
        s.configure('TScale', background=SURFACE, troughcolor=BORDER, slidercolor=ACCENT)
        s.configure('TRadiobutton', background=SURFACE, foreground=FG, font=FONT_UI,
                    indicatorcolor=BORDER, selectcolor=GREEN)
        s.map('TRadiobutton',
              background=[('active', SURFACE)],
              indicatorcolor=[('selected', GREEN)])
        s.configure('Start.TButton',
                    font=('Segoe UI', 9, 'bold'),
                    background=GREEN, foreground='#0f131a',
                    padding=(18, 7), relief='flat')
        s.map('Start.TButton',
              background=[('active', '#4dd4b6'), ('disabled', BORDER)],
              foreground=[('disabled', MUTED)])
        s.configure('Stop.TButton',
                    font=('Segoe UI', 9, 'bold'),
                    background=RED, foreground='#0f131a',
                    padding=(18, 7), relief='flat')
        s.map('Stop.TButton',
              background=[('active', '#e05555'), ('disabled', BORDER)],
              foreground=[('disabled', MUTED)])
        s.configure('Util.TButton',
                    font=FONT_UI,
                    background=BORDER, foreground=FG,
                    padding=(10, 5), relief='flat')
        s.map('Util.TButton', background=[('active', '#3a4458')])
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=BORDER, foreground=MUTED,
                    font=('Segoe UI', 9, 'bold'), padding=(14, 6))
        s.map('TNotebook.Tab',
              background=[('selected', SURFACE)],
              foreground=[('selected', FG)])

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        _icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
        self._title_icons = []  # prevent GC

        # Titlebar (two rows: top = brand+counters, bottom = live stats)
        bar_wrap = tk.Frame(self.root, bg=TITLE_BG)
        bar_wrap.pack(fill='x')
        bar = tk.Frame(bar_wrap, bg=TITLE_BG, height=44)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        # Pickaxe icon + title text
        try:
            pick_img = Image.open(os.path.join(_icons_dir, 'Rune_Pickaxe.png')).resize((24, 24), Image.LANCZOS)
            pick_photo = ImageTk.PhotoImage(pick_img)
            self._title_icons.append(pick_photo)
            tk.Label(bar, image=pick_photo, bg=TITLE_BG).pack(side='left', padx=(14, 4), pady=10)
        except Exception:
            pass
        tk.Label(bar, text='RSC MULTIMINER  V1.1', bg=TITLE_BG, fg=FG,
                 font=('Segoe UI', 11, 'bold')).pack(side='left', pady=12)

        # Ore icons in order: Copper, Coal, Iron, Mithril, Adamantite, Tin
        ore_files = ['Copper_ore.png', 'Coal.png', 'Iron_ore.png',
                     'Mithril_ore.png', 'Adamantite_ore.png', 'Tin_ore.png']
        for fname in ore_files:
            try:
                ore_img = Image.open(os.path.join(_icons_dir, fname)).resize((20, 20), Image.LANCZOS)
                ore_photo = ImageTk.PhotoImage(ore_img)
                self._title_icons.append(ore_photo)
                tk.Label(bar, image=ore_photo, bg=TITLE_BG).pack(side='left', padx=1, pady=10)
            except Exception:
                pass
        
        self.status_dot = tk.Label(bar, text='● IDLE', bg=TITLE_BG, fg=MUTED,
                                   font=('Segoe UI', 8, 'bold'))
        self.status_dot.pack(side='right', padx=14)

        # Break countdown — hidden until bot is on break
        self.break_countdown_label = tk.Label(bar, text='', bg=TITLE_BG, fg='#ffb347',
                                              font=('Consolas', 10, 'bold'))
        self.break_countdown_label.pack(side='right', padx=8)

        # Clicked-rocks counter (top bar)
        self.click_count = 0
        self.click_count_label = tk.Label(bar, text='⛏ 0',
                                          bg=TITLE_BG, fg=GREEN,
                                          font=('Consolas', 10, 'bold'))
        self.click_count_label.pack(side='right', padx=8)

        # Walkto countdown (top bar) — only visible when walkto is enabled
        self._walkto_bar_label = tk.Label(bar, text='',
                                          bg=TITLE_BG, fg=AMBER,
                                          font=('Consolas', 9, 'bold'))
        self._walkto_bar_label.pack(side='right', padx=8)

        # Runtime, mouse coords + last click — inline at the top
        self.live_runtime_label = tk.Label(bar, text='⏱ 00:00',
                                           bg=TITLE_BG, fg=GREEN,
                                           font=('Consolas', 10, 'bold'))
        self.live_runtime_label.pack(side='right', padx=8)

        self.mouse_coord_label = tk.Label(bar, text='🖱 ----, ----   ----ms',
                                          bg=TITLE_BG, fg=MUTED,
                                          font=('Consolas', 8))
        self.mouse_coord_label.pack(side='right', padx=8)

        # Last-click label is merged into mouse_coord_label text; keep the
        # attribute so _schedule_live_update can write to it without a NoneType.
        self.live_last_click_label = tk.Label(bar_wrap)  # hidden, unpacked
        self.live_mouse_label = None

        # Fatigue + Inventory — boxed together, larger, top-right second row
        stats_row = tk.Frame(bar_wrap, bg=TITLE_BG)
        stats_row.pack(fill='x', padx=8, pady=(0, 6))
        stats_outer = tk.Frame(stats_row, bg=BORDER, padx=1, pady=1)
        stats_outer.pack(side='right', padx=(0, 8))
        stats = tk.Frame(stats_outer, bg=SURFACE, padx=12, pady=6)
        stats.pack()
        def _stat(col, label_text, default, color, attr):
            tk.Label(stats, text=label_text, bg=SURFACE, fg=MUTED,
                     font=('Consolas', 9, 'bold')).grid(row=0, column=col, sticky='e', padx=(0, 6))
            val = tk.Label(stats, text=default, bg=SURFACE, fg=color,
                           font=('Consolas', 16, 'bold'))
            val.grid(row=0, column=col + 1, sticky='w', padx=(0, 16))
            setattr(self, attr, val)
        _stat(0, 'FATIGUE',   '0%',   RED,   'live_fatigue_label')
        _stat(2, 'INVENTORY', '0/30', AMBER, 'live_inventory_label')

        # ── Notebook with two tabs ───────────────────────────────────────────
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=6, pady=(4, 0))

        # ── Shared multi-client state (must be init'd before any bot tab) ────
        self._clients_config = self.config.get('clients', [])
        while len(self._clients_config) < 4:
            self._clients_config.append({})
        self._client_window_combos = []
        self._client_enable_vars = [None] * 4
        self._client_ore_vars    = [{} for _ in range(4)]
        self._client_task_vars   = [None] * 4
        self._client_status_rows = {}

        # ── Mining (top-level, with nested sub-tabs) ─────────────────────────
        mining_tab = tk.Frame(notebook, bg=BG)
        notebook.add(mining_tab, text='  Mining (Master)  ')
        mining_sub = ttk.Notebook(mining_tab)
        mining_sub.pack(fill='both', expand=True)

        sub_bot = tk.Frame(mining_sub, bg=BG)
        mining_sub.add(sub_bot, text='  Bot  ')
        self._build_bot_tab(sub_bot)

        sub_settings = tk.Frame(mining_sub, bg=BG)
        mining_sub.add(sub_settings, text='  Settings  ')
        self._build_settings_tab(sub_settings)

        sub_antiban = tk.Frame(mining_sub, bg=BG)
        mining_sub.add(sub_antiban, text='  Anti-Ban  ')
        self._build_antiban_tab(sub_antiban)

        sub_exp = tk.Frame(mining_sub, bg=BG)
        mining_sub.add(sub_exp, text='  Experimental  ')
        self._build_experimental_tab(sub_exp)

        # ── Bot2 / Bot3 / Bot4 tabs ──────────────────────────────────────────
        for _slot_idx in range(1, 4):
            _bt = tk.Frame(notebook, bg=BG)
            notebook.add(_bt, text=f'  Bot{_slot_idx + 1}  ')
            self._build_bot_slave_tab(_bt, _slot_idx)

        # Start the live-status refresh for all bot tabs
        self._schedule_clients_status_update()

        # Footer
        footer = tk.Frame(self.root, bg=TITLE_BG, height=54)
        footer.pack(fill='x', side='bottom')
        footer.pack_propagate(False)
        tk.Frame(footer, bg=BORDER, height=1).pack(fill='x', side='top')
        btn_row = tk.Frame(footer, bg=TITLE_BG)
        btn_row.pack(expand=True)
        self.btn_start = ttk.Button(btn_row, text='▶  START', command=self.start_bot,
                                    style='Start.TButton')
        self.btn_start.pack(side='left', padx=6, pady=10)
        self.btn_stop = ttk.Button(btn_row, text='■  STOP', command=self.stop_bot,
                                   state='disabled', style='Stop.TButton')
        self.btn_stop.pack(side='left', padx=6)
        ttk.Button(btn_row, text='SAVE', command=self.save_config,
                   style='Util.TButton').pack(side='left', padx=6)

        # Overlay mode toggle — always visible in footer
        sep = tk.Frame(btn_row, bg=BORDER, width=1, height=24)
        sep.pack(side='left', padx=8, fill='y')
        tk.Label(btn_row, text='OVERLAY:', bg=TITLE_BG, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold')).pack(side='left')
        self.overlay_mode_var = tk.StringVar(value=self.config.get('overlay_mode', 'ingame'))
        ttk.Radiobutton(btn_row, text='In-Game',
                        variable=self.overlay_mode_var, value='ingame').pack(side='left', padx=2)
        ttk.Radiobutton(btn_row, text='Pop-Out',
                        variable=self.overlay_mode_var, value='popout').pack(side='left', padx=2)
        # Rebuild overlay when mode switches so the old window is torn down
        self.overlay_mode_var.trace_add('write', lambda *_: self._on_overlay_mode_change())

        tk.Label(btn_row, text='F6 = toggle', bg=TITLE_BG, fg=MUTED,
                 font=(FONT_UI[0], 7)).pack(side='left', padx=10)

    # ── Bot Tab (main working view) ──────────────────────────────────────────

    def _build_bot_tab(self, tab):
        # Debug log — fixed strip at the very bottom (not in scroll area)
        log_strip = tk.Frame(tab, bg=BG)
        log_strip.pack(side='bottom', fill='x', padx=6, pady=(0, 4))
        log_co, log_c = card(log_strip, padx=0, pady=4)
        log_co.pack(fill='x')
        section_label(log_c, 'Debug Log')
        self.debug_text = scrolledtext.ScrolledText(
            log_c, height=5,
            bg=TITLE_BG, fg=GREEN,
            insertbackground=GREEN,
            font=(FONT_UI[0], 9),
            relief='flat', bd=0,
            selectbackground=BORDER)
        self.debug_text.pack(fill='x', padx=6, pady=(0, 4))
        self.debug_text.config(state='disabled')
        self.log_debug('Console ready')

        # Scrollable upper area
        vscroll = tk.Scrollbar(tab, orient='vertical',
                               bg=BG, troughcolor=BG, width=18, highlightthickness=0, bd=0)
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0,
                           yscrollcommand=vscroll.set)
        vscroll.config(command=canvas.yview)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        wrapper = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=wrapper, anchor='nw')

        def _on_wrapper_configure(e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
        def _on_canvas_configure(event):
            canvas.itemconfig(win_id, width=event.width)

        wrapper.bind('<Configure>', _on_wrapper_configure)
        canvas.bind('<Configure>', _on_canvas_configure)
        # Scope mouse wheel to this canvas only — bind_all caused Settings-tab
        # canvas to steal wheel events from the Bot tab.
        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        canvas.bind('<Enter>', lambda _: canvas.bind_all('<MouseWheel>', _wheel))
        canvas.bind('<Leave>', lambda _: canvas.unbind_all('<MouseWheel>'))

        left  = tk.Frame(wrapper, bg=BG)
        right = tk.Frame(wrapper, bg=BG)
        left.grid(row=0, column=0, sticky='new', padx=(0, 3))
        right.grid(row=0, column=1, sticky='new', padx=(3, 0))
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)

        self._build_left(left)
        self._build_right(right)
        wrapper.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox('all'))

    def _build_left(self, p):
        # ── Mining Mode (TOP) ────────────────────────────────────────────────
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Mining Mode')

        self.powermine_var = tk.BooleanVar(value=self.config.get('powermine_enabled', False))
        _pm_row = tk.Frame(c, bg=SURFACE)
        _pm_row.pack(anchor='w', padx=8, pady=(0, 4))
        self._powermine_toggle = Toggle(_pm_row, self.powermine_var, bg=SURFACE)
        self._powermine_toggle.pack(side='left', padx=(0, 8))
        tk.Label(_pm_row, text='Powermine (never stop)', bg=SURFACE, fg=FG,
                 font=FONT_UI, anchor='w').pack(side='left', fill='x', expand=True)

        # Speed mode: prefer new `speed_mode`; fall back to legacy `fast_mining_enabled`.
        _saved_mode = self.config.get('speed_mode')
        if _saved_mode not in ('fast', 'lazy', 'super_lazy'):
            _saved_mode = 'fast' if self.config.get('fast_mining_enabled', True) else 'lazy'
        self.config['speed_mode'] = _saved_mode
        self.config['fast_mining_enabled'] = (_saved_mode == 'fast')
        self.mining_speed_var = tk.StringVar(value=_saved_mode)
        sr = tk.Frame(c, bg=SURFACE)
        sr.pack(fill='x', padx=8, pady=(0, 2))
        ttk.Radiobutton(sr, text='Fast  (800-1200 ms)',
                        variable=self.mining_speed_var, value='fast',
                        command=self._on_speed_change).pack(side='left', padx=4)
        ttk.Radiobutton(sr, text='Lazy  (1.2-2.4 s)',
                        variable=self.mining_speed_var, value='lazy',
                        command=self._on_speed_change).pack(side='left', padx=4)
        ttk.Radiobutton(sr, text='Super Lazy  (10-30 s)',
                        variable=self.mining_speed_var, value='super_lazy',
                        command=self._on_speed_change).pack(side='left', padx=4)

        # Multi-Client mode toggle — lives here so it's grouped with Mining Mode
        self.multi_client_var = tk.BooleanVar(
            value=self.config.get('multi_client_mode', False))
        mc_row = tk.Frame(c, bg=SURFACE)
        mc_row.pack(anchor='w', padx=8, pady=(4, 2))
        Toggle(mc_row, self.multi_client_var, bg=SURFACE).pack(side='left', padx=(0, 8))
        tk.Label(mc_row, text='Multi-Client Window Hopping  (hops mouse between Bot2/3/4 windows)',
                 bg=SURFACE, fg=FG, font=FONT_UI, anchor='w').pack(side='left')
        tk.Label(c, text='Disables park-mouse and hover mode. Enable Bot2/3/4 tabs and assign windows.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=380, justify='left').pack(anchor='w', padx=22, pady=(0, 4))

        self.lazy_idle_pause_var = tk.BooleanVar(value=self.config.get('lazy_idle_pause_enabled', False))
        toggle_row(c, 'Lazy idle pause (every 5–25 clicks, park mouse 5–20s)',
                   self.lazy_idle_pause_var).pack(anchor='w', padx=8, pady=(0, 2))

        # Park mouse outside — only usable in Lazy mode
        self.mouse_outside_var = tk.BooleanVar(value=self.config.get('mouse_outside_window', False))
        self.mouse_outside_var.trace_add('write', lambda *_: self._on_mouse_outside_change())
        _park_row = tk.Frame(c, bg=SURFACE)
        _park_row.pack(anchor='w', padx=8, pady=(0, 2))
        self._mouse_outside_toggle = Toggle(_park_row, self.mouse_outside_var, bg=SURFACE)
        self._mouse_outside_toggle.pack(side='left', padx=(0, 8))
        tk.Label(_park_row, text='Park mouse outside window after click  (Lazy only)',
                 bg=SURFACE, fg=FG, font=FONT_UI, anchor='w').pack(side='left', fill='x', expand=True)
        # Disabled when in fast mode
        if self.config.get('fast_mining_enabled', True):
            self._mouse_outside_toggle.set_disabled(True)

        self.stop_on_full_var = tk.BooleanVar(value=self.config.get('stop_on_full_inventory', True))
        toggle_row(c, 'Stop when inventory full (X/30)',
                   self.stop_on_full_var).pack(anchor='w', padx=8, pady=(2, 2))

        self.config['hover_mode_enabled'] = False
        self.hover_mode_var = tk.BooleanVar(value=False)
        self.hover_mode_var.trace_add('write', self._on_hover_mode_change)
        toggle_row(c, '⚗ Hover Mode  [experimental]',
                   self.hover_mode_var).pack(anchor='w', padx=8, pady=(4, 0))
        tk.Label(c, text='After clicking ore A, glide mouse to ore B and click the instant A depletes.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=260, justify='left').pack(anchor='w', padx=22, pady=(0, 4))

        # Powermine: hard-disable fatigue check.
        self.pm_no_fatigue_var = tk.BooleanVar(value=self.config.get('powermine_disable_fatigue', False))
        def _on_pm_nf(*_):
            self.config['powermine_disable_fatigue'] = bool(self.pm_no_fatigue_var.get())
            try: self.save_config()
            except Exception: pass
        self.pm_no_fatigue_var.trace_add('write', _on_pm_nf)
        toggle_row(c, 'Powermine: hard-disable fatigue check',
                   self.pm_no_fatigue_var).pack(anchor='w', padx=8, pady=(4, 6))

        # ── Game Window ──────────────────────────────────────────────────────
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Game Window')

        java_windows = self.get_java_windows()
        # Pick the display entry that matches the saved title
        saved_title = self.config.get('window_title', '')
        matching = next((d for d, info in self._window_info_map.items()
                         if info['title'] == saved_title), java_windows[0] if java_windows else '')
        self.window_var = tk.StringVar(value=matching)

        self._window_combo = ttk.Combobox(c, textvariable=self.window_var,
                                          values=java_windows, state='readonly')
        self._window_combo.pack(fill='x', padx=6, pady=(0, 2))
        self._window_combo.bind('<<ComboboxSelected>>', self.on_window_selected)
        self._window_combo.bind('<MouseWheel>', lambda e: 'break')

        # Info strip below dropdown
        self._win_info_label = tk.Label(c, text='', bg=TITLE_BG, fg=MUTED,
                                        font=(FONT_UI[0], 8), anchor='w', padx=6)
        self._win_info_label.pack(fill='x', padx=6, pady=(0, 2))
        self._update_win_info_label()

        btn_row = tk.Frame(c, bg=SURFACE)
        btn_row.pack(fill='x', padx=6, pady=(0, 2))
        ttk.Button(btn_row, text='Refresh',  command=self.refresh_windows,
                   style='Util.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(btn_row, text='Bring to front',
                   command=self._bring_selected_to_front,
                   style='Util.TButton').pack(side='left', padx=(0, 4))

        # Brightness slider
        br_row = tk.Frame(c, bg=SURFACE)
        br_row.pack(fill='x', padx=6, pady=(2, 2))
        tk.Label(br_row, text='Brightness (Experimental)', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 8), anchor='w').pack(side='left')
        self._brightness_var = tk.IntVar(value=self.config.get('window_brightness', 100))
        br_scale = ttk.Scale(br_row, from_=50, to=200, orient='horizontal',
                             variable=self._brightness_var, length=90)
        br_scale.pack(side='left', padx=4)
        self._brightness_pct_label = tk.Label(br_row, text=f'{self._brightness_var.get()}%',
                                              bg=SURFACE, fg=FG, font=(FONT_UI[0], 8), width=5)
        self._brightness_pct_label.pack(side='left')
        ttk.Button(br_row, text='Apply', command=self._apply_brightness,
                   style='Util.TButton').pack(side='left', padx=2)
        self._brightness_var.trace_add('write',
            lambda *_: self._brightness_pct_label.config(
                text=f'{self._brightness_var.get()}%'))

        # Auto-login toggle (uses autologin.attempt_login before main bot loop)
        self.autologin_var = tk.BooleanVar(value=self.config.get('autologin_enabled', False))
        toggle_row(c, 'Auto-login on Start (OCR login screens)',
                   self.autologin_var).pack(anchor='w', padx=6, pady=(2, 0))
        tk.Label(c, text='Fail-safe: stops bot after 5 failed login attempts, or after 30s of no ore/fatigue reads.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 7, 'italic'),
                 wraplength=280, justify='left').pack(anchor='w', padx=30, pady=(0, 4))

        # Ores + Priority — combined drag-to-reorder panel
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        # Section header with "show empty" toggle on the same line
        hdr_row = tk.Frame(c, bg=SURFACE)
        hdr_row.pack(fill='x', padx=8, pady=(4, 2))
        tk.Label(hdr_row, text='ORE SELECTION & PRIORITY', bg=SURFACE, fg=ACCENT,
                 font=('Segoe UI', 9, 'bold')).pack(side='left')
        self.show_empty_var = tk.BooleanVar(value=self.config.get('show_empty_ore', False))
        self.show_empty_var.trace_add('write', lambda *_: self.config.update({'show_empty_ore': self.show_empty_var.get()}))
        se_row = tk.Frame(hdr_row, bg=SURFACE)
        se_row.pack(side='right')
        Toggle(se_row, self.show_empty_var, bg=SURFACE).pack(side='left', padx=(0, 4))
        tk.Label(se_row, text='Show Empty Rocks', bg=SURFACE, fg=FG,
                 font=(FONT_UI[0], 8)).pack(side='left')
        tk.Frame(c, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(0, 6))
        tk.Label(c, text='✓ enable  |  ≡ drag to set priority',
                 bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 8, 'italic')).pack(anchor='w', padx=10, pady=(0, 4))

        self.checkbox_vars = {}
        all_ores = ['coal_rock', 'mithril_rock', 'iron_rock',
                    'tin_rock', 'copper_rock']
        for ore in all_ores:
            self.checkbox_vars[ore] = tk.BooleanVar(
                value=self.config['ore_checkboxes'].get(ore, True))

        # Filter saved priority_order to only known ores (handles dropped
        # 'adamantite_rock' entries from older configs).
        saved_order = [o for o in self.config.get('priority_order', all_ores) if o in all_ores]
        for o in all_ores:
            if o not in saved_order:
                saved_order.append(o)
        self.ore_list = OreList(
            c,
            priority_order=saved_order,
            checkbox_vars=self.checkbox_vars,
            bg=BG, fg=FG, surface=SURFACE, accent=ACCENT, muted=MUTED,
        )
        self.ore_list.pack(fill='x', padx=6, pady=(0, 6))

        # Detection confidence — lives here so it's next to ore selection
        tk.Frame(c, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(0, 4))
        self.confidence_var = tk.DoubleVar(
            value=self.config.get('detection_settings', {}).get('confidence_threshold', 0.75))
        crow = tk.Frame(c, bg=SURFACE)
        crow.pack(fill='x', padx=8, pady=(0, 6))
        tk.Label(crow, text='Confidence', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=11, anchor='w').pack(side='left')
        self.confidence_value_label = tk.Label(
            crow, text=f'{self.confidence_var.get():.2f}',
            bg=BORDER, fg=ACCENT, font=('Consolas', 8, 'bold'), width=5)
        self.confidence_value_label.pack(side='right', padx=4)
        ttk.Scale(crow, from_=0.05, to=1.0, orient='horizontal',
                  variable=self.confidence_var,
                  command=self.on_confidence_change).pack(side='left', fill='x', expand=True)

        # overlay_mode_var is created in the footer (always visible)
        # just make sure the variable exists before the footer is built
        if not hasattr(self, 'overlay_mode_var'):
            self.overlay_mode_var = tk.StringVar(value=self.config.get('overlay_mode', 'ingame'))

    def _build_right(self, p):
        # Camera Rotation — top-right
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Camera Rotation')
        self.camera_rotation_var = tk.BooleanVar(value=self.config.get('camera_rotation_enabled', True))
        _cam_row = tk.Frame(c, bg=SURFACE)
        _cam_row.pack(anchor='w', padx=8, pady=(0, 6))
        self._cam_rot_toggle = Toggle(_cam_row, self.camera_rotation_var, bg=SURFACE)
        self._cam_rot_toggle.pack(side='left', padx=(0, 8))
        tk.Label(_cam_row, text='Auto-rotate camera when no ore found',
                 bg=SURFACE, fg=FG, font=FONT_UI, anchor='w').pack(side='left', fill='x', expand=True)

        # Fixed Ore Spots — top-right
        co, c = card(p, padx=0, pady=6)
        co.pack(fill='x', pady=(0, 6))
        section_label(c, 'Fixed Ore Spots')
        tk.Label(c, text='Disable camera rotation + select up to 3 spots to lock the bot in place.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=260, justify='left').pack(anchor='w', padx=10, pady=(0, 6))
        self._fixed_spots = list(self.config.get('fixed_ore_spots', []))
        spot_row = tk.Frame(c, bg=SURFACE)
        spot_row.pack(fill='x', padx=8, pady=(0, 6))
        self.spot_btn_label = tk.StringVar(value=self._spot_btn_text())
        ttk.Button(spot_row, textvariable=self.spot_btn_label,
                   command=self._open_spot_selector,
                   style='Util.TButton').pack(side='left', padx=(0, 6))
        ttk.Button(spot_row, text='Clear spots',
                   command=self._clear_fixed_spots,
                   style='Util.TButton').pack(side='left')

        # Fixed Spots Mode toggle — disables camera rotation when on
        _has_spots = bool(self._fixed_spots)
        _cam_off = not self.config.get('camera_rotation_enabled', True)
        self.fixed_spot_mode_var = tk.BooleanVar(value=(_has_spots and _cam_off))
        toggle_row(c, 'Fixed Spots Mode  (locks rotation off)',
                   self.fixed_spot_mode_var).pack(anchor='w', padx=8, pady=(4, 6))

        def _on_fixed_spot_mode(*_):
            if self.fixed_spot_mode_var.get():
                self.camera_rotation_var.set(False)
                self._cam_rot_toggle.set_disabled(True)
            else:
                self._cam_rot_toggle.set_disabled(False)
        self.fixed_spot_mode_var.trace_add('write', _on_fixed_spot_mode)
        # Apply initial state
        _on_fixed_spot_mode()

    # ── Settings Tab ─────────────────────────────────────────────────────────

    def _build_settings_tab(self, tab):
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview,
                               bg=BG, troughcolor=BG, width=18, highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        body = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=body, anchor='nw')

        def _resize(e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        body.bind('<Configure>', _resize)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        canvas.bind('<Enter>', lambda _: canvas.bind_all('<MouseWheel>', _wheel))
        canvas.bind('<Leave>', lambda _: canvas.unbind_all('<MouseWheel>'))

        # Profiles (named config snapshots — top of Settings)
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(6, 6))
        section_label(c, 'Profiles')
        tk.Label(c, text='Save and recall named configs '
                         '(e.g. "powerminetincopper", "faladorironbank").',
                 bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 8, 'italic')).pack(anchor='w', padx=8, pady=(0, 4))
        prow = tk.Frame(c, bg=SURFACE)
        prow.pack(fill='x', padx=8, pady=(0, 6))
        self._profiles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          'profiles')
        os.makedirs(self._profiles_dir, exist_ok=True)
        self.profile_var = tk.StringVar(value='')
        self._profile_combo = ttk.Combobox(prow, textvariable=self.profile_var,
                                           values=self._list_profiles(),
                                           state='normal', width=24)
        self._profile_combo.pack(side='left', padx=(0, 4))
        self._profile_combo.bind('<MouseWheel>', lambda e: 'break')
        ttk.Button(prow, text='Save as',
                   command=self._profile_save,
                   style='Util.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(prow, text='Load',
                   command=self._profile_load,
                   style='Util.TButton').pack(side='left', padx=(0, 4))
        ttk.Button(prow, text='Delete',
                   command=self._profile_delete,
                   style='Util.TButton').pack(side='left')

        # YOLO Models (moved here from bot tab)
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'YOLO Models')
        self.main_model_var = tk.BooleanVar(
            value=self.config.get('model_settings', {}).get('use_main_model', True))
        toggle_row(c, 'Main (best.pt)', self.main_model_var).pack(anchor='w', padx=8, pady=(0, 6))

        # Detection (box thickness only — confidence is in the Ore Selection panel)
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(6, 6))
        section_label(c, 'Detection')
        self.overlay_thickness_var = tk.IntVar(
            value=self.config.get('overlay_box_thickness', 2))
        trow = tk.Frame(c, bg=SURFACE)
        trow.pack(fill='x', padx=8, pady=(4, 4))
        tk.Label(trow, text='Box thickness', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=11, anchor='w').pack(side='left')
        self.overlay_thickness_label = tk.Label(
            trow, textvariable=self.overlay_thickness_var,
            bg=BORDER, fg=ACCENT, font=('Consolas', 8, 'bold'), width=3)
        self.overlay_thickness_label.pack(side='right', padx=4)
        ttk.Scale(trow, from_=1, to=6, orient='horizontal',
                  variable=self.overlay_thickness_var,
                  command=lambda v: self.overlay_thickness_var.set(int(float(v)))
                  ).pack(side='left', fill='x', expand=True)

        # Mouse
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Mouse')
        ms = self.config.get('mouse_settings', {})
        self.min_delay_var   = tk.StringVar(value=str(ms.get('min_delay_ms', 50)))
        self.max_delay_var   = tk.StringVar(value=str(ms.get('max_delay_ms', 250)))
        self.human_curve_var = tk.StringVar(value=str(ms.get('human_curve_strength', 0.7)))
        for lbl, var, unit in [('Min delay', self.min_delay_var, 'ms'),
                                ('Max delay', self.max_delay_var, 'ms'),
                                ('Curve str.', self.human_curve_var, '')]:
            r = tk.Frame(c, bg=SURFACE)
            r.pack(fill='x', padx=8, pady=2)
            tk.Label(r, text=lbl, bg=SURFACE, fg=MUTED,
                     font=FONT_UI, width=10, anchor='w').pack(side='left')
            ttk.Entry(r, textvariable=var, width=7).pack(side='left', padx=4)
            if unit:
                tk.Label(r, text=unit, bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left')

        # Mouse profile seed
        seed_val = ms.get('mouse_seed', None)
        self.mouse_seed_var = tk.IntVar(value=seed_val if seed_val is not None else random.randint(0, 9999))
        sr = tk.Frame(c, bg=SURFACE)
        sr.pack(fill='x', padx=8, pady=(4, 2))
        tk.Label(sr, text='Profile seed', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        self.seed_label = tk.Label(sr, textvariable=self.mouse_seed_var,
                                   bg=BORDER, fg=ACCENT, font=('Consolas', 9, 'bold'), width=6)
        self.seed_label.pack(side='left', padx=4)
        ttk.Scale(sr, from_=0, to=9999, orient='horizontal',
                  variable=self.mouse_seed_var,
                  command=lambda v: self.mouse_seed_var.set(int(float(v)))).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(sr, text='🎲 Random',
                   command=lambda: self.mouse_seed_var.set(random.randint(0, 9999))).pack(side='right', padx=4)

        # Long Breaks + Micro Breaks — side by side
        bs = self.config.get('break_settings', {})
        bf = tk.Frame(body, bg=BG)
        bf.pack(fill='x', padx=8, pady=(0, 6))
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)

        # Long Breaks (left)
        co_lb, c_lb = card(bf, padx=0, pady=6)
        co_lb.grid(row=0, column=0, sticky='new', padx=(0, 3))
        section_label(c_lb, 'Long Breaks')
        self.breaks_enabled_var = tk.BooleanVar(value=bs.get('breaks_enabled', True))
        toggle_row(c_lb, 'Enable', self.breaks_enabled_var).pack(anchor='w', padx=8, pady=(0, 4))
        self.min_break_interval_var = tk.StringVar(value=str(max(1, int(bs.get('min_seconds_between_breaks', 600)) // 60)))
        self.max_break_interval_var = tk.StringVar(value=str(max(1, int(bs.get('max_seconds_between_breaks', 3600)) // 60)))
        self.min_break_duration_var = tk.StringVar(value=str(max(1, int(bs.get('min_break_duration_seconds', 60)) // 60)))
        self.max_break_duration_var = tk.StringVar(value=str(max(1, int(bs.get('max_break_duration_seconds', 1200)) // 60)))
        for lbl, v1, v2 in [('Every (min)', self.min_break_interval_var, self.max_break_interval_var),
                             ('Duration (min)', self.min_break_duration_var, self.max_break_duration_var)]:
            r = tk.Frame(c_lb, bg=SURFACE)
            r.pack(fill='x', padx=8, pady=2)
            tk.Label(r, text=lbl, bg=SURFACE, fg=MUTED,
                     font=FONT_UI, width=12, anchor='w').pack(side='left')
            ttk.Entry(r, textvariable=v1, width=5).pack(side='left', padx=2)
            tk.Label(r, text='–', bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left', padx=2)
            ttk.Entry(r, textvariable=v2, width=5).pack(side='left', padx=2)
        tk.Frame(c_lb, bg=SURFACE).pack(pady=(0, 4))

        # Micro Breaks (right)
        co_mb, c_mb = card(bf, padx=0, pady=6)
        co_mb.grid(row=0, column=1, sticky='new', padx=(3, 0))
        section_label(c_mb, 'Micro Breaks')
        self.micro_breaks_enabled_var = tk.BooleanVar(value=bs.get('micro_breaks_enabled', True))
        toggle_row(c_mb, 'Enable', self.micro_breaks_enabled_var).pack(anchor='w', padx=8, pady=(0, 4))
        self.micro_break_min_var = tk.StringVar(value=str(bs.get('micro_break_min_ms', 100)))
        self.micro_break_max_var = tk.StringVar(value=str(bs.get('micro_break_max_ms', 500)))
        r = tk.Frame(c_mb, bg=SURFACE)
        r.pack(fill='x', padx=8, pady=2)
        tk.Label(r, text='Range (ms)', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=12, anchor='w').pack(side='left')
        ttk.Entry(r, textvariable=self.micro_break_min_var, width=5).pack(side='left', padx=2)
        tk.Label(r, text='–', bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left', padx=2)
        ttk.Entry(r, textvariable=self.micro_break_max_var, width=5).pack(side='left', padx=2)
        tk.Frame(c_mb, bg=SURFACE).pack(pady=(0, 4))

        # Verbose debug toggle — moved up since anti-ban section now lives in its own tab
        self.verbose_debug_var = tk.BooleanVar(value=self.config.get('verbose_debug', False))
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Debug')
        toggle_row(c, 'Verbose debug logging',
                   self.verbose_debug_var).pack(anchor='w', padx=8, pady=(2, 4))
        tk.Label(c, text='→ Anti-Ban Features are in their own tab.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic')
                 ).pack(anchor='w', padx=8, pady=(0, 6))

        # Theme — at the bottom of Settings; changing it restarts the GUI.
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(0, 6))
        section_label(c, 'Theme')
        tk.Label(c, text='⚠ Changing theme will restart the bot GUI',
                 bg=SURFACE, fg=AMBER,
                 font=(FONT_UI[0], 8, 'bold')).pack(anchor='w', padx=8, pady=(0, 4))
        tr = tk.Frame(c, bg=SURFACE)
        tr.pack(fill='x', padx=8, pady=2)
        tk.Label(tr, text='Preset', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        self.theme_var = tk.StringVar(value=self.config.get('theme', 'RS-Classic'))
        theme_combo = ttk.Combobox(tr, textvariable=self.theme_var,
                                   values=list(THEMES.keys()), state='readonly', width=20)
        theme_combo.pack(side='left', padx=4)
        theme_combo.bind('<<ComboboxSelected>>', self._on_theme_change)
        theme_combo.bind('<MouseWheel>', lambda e: 'break')
        fr = tk.Frame(c, bg=SURFACE)
        fr.pack(fill='x', padx=8, pady=(2, 6))
        tk.Label(fr, text='Font', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        self.font_var = tk.StringVar(value=self.config.get('font', FONT_UI[0]))
        font_combo = ttk.Combobox(fr, textvariable=self.font_var,
                                  values=FONT_CHOICES, state='readonly', width=20)
        font_combo.pack(side='left', padx=4)
        font_combo.bind('<<ComboboxSelected>>', self._on_theme_change)
        font_combo.bind('<MouseWheel>', lambda e: 'break')

    def _build_antiban_tab(self, tab):
        """Anti-Ban Features as a standalone tab with its own scroll container."""
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview,
                               bg=BG, troughcolor=BG, width=18, highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=body, anchor='nw')
        def _resize(e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        body.bind('<Configure>', _resize)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        canvas.bind('<Enter>', lambda _: canvas.bind_all('<MouseWheel>', _wheel))
        canvas.bind('<Leave>', lambda _: canvas.unbind_all('<MouseWheel>'))

        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(6, 6))
        section_label(c, 'Anti-Ban Features')

        # Master switch
        self.antiban_master_var = tk.BooleanVar(
            value=self.config.get('antiban_master_enabled', True))
        toggle_row(c, '★ Master: Anti-Ban Suite  (disables all below if off)',
                   self.antiban_master_var).pack(anchor='w', padx=8, pady=(0, 4))
        tk.Frame(c, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(0, 4))

        # Track sub-widgets so master toggle can disable/enable them visually.
        self._antiban_sub_frame = c
        self._antiban_master_anchor_count = len(c.winfo_children())
        self.antiban_master_var.trace_add('write', lambda *_: self._apply_antiban_master_state())

        def _ab_label(parent, tag):
            """Small tag next to toggle: [DEFAULT ON] or [OPT-IN]."""
            color = GREEN if tag == 'DEFAULT ON' else AMBER
            tk.Label(parent, text=f'[{tag}]', bg=SURFACE, fg=color,
                     font=(FONT_UI[0], 7, 'bold')).pack(side='left', padx=(4, 0))

        # 1. Failsafe: 30 empty rotations (always on — no toggle).
        info_row = tk.Frame(c, bg=SURFACE)
        info_row.pack(fill='x', padx=8, pady=(4, 0))
        tk.Label(info_row, text='✓',
                 bg=SURFACE, fg=GREEN, font=(FONT_UI[0], 9, 'bold')).pack(side='left', padx=(0, 6))
        tk.Label(info_row, text='Stop after 30 empty camera rotations',
                 bg=SURFACE, fg=FG, font=FONT_UI).pack(side='left')
        tk.Label(info_row, text='[ALWAYS ON]', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold')).pack(side='left', padx=4)

        # 2. Fatigue detection
        self.fatigue_detection_var = tk.BooleanVar(
            value=self.config.get('fatigue_detection_enabled', True))
        row = toggle_row(c, 'Detect fatigue (OCR) — stop at 96%',
                         self.fatigue_detection_var)
        row.pack(anchor='w', padx=8, pady=(2, 0))
        _ab_label(row, 'DEFAULT ON')

        # 3. Micro breaks
        bs = self.config.get('break_settings', {})
        if not hasattr(self, 'micro_breaks_enabled_var'):
            self.micro_breaks_enabled_var = tk.BooleanVar(
                value=bs.get('micro_breaks_enabled', True))
        row = toggle_row(c, 'Micro breaks (short random pauses between clicks)',
                         self.micro_breaks_enabled_var)
        row.pack(anchor='w', padx=8, pady=(2, 0))
        _ab_label(row, 'DEFAULT ON')

        # 4. Long breaks
        if not hasattr(self, 'breaks_enabled_var'):
            self.breaks_enabled_var = tk.BooleanVar(
                value=bs.get('breaks_enabled', True))
        row = toggle_row(c, 'Long breaks (periodic extended pauses)',
                         self.breaks_enabled_var)
        row.pack(anchor='w', padx=8, pady=(2, 0))
        _ab_label(row, 'DEFAULT ON')

        # 5. Teleport detector — moved to Experimental tab (still default-on).
        tk.Frame(c, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(2, 4))

        # 6. Randomized mouse personality (informational — always on)
        info_row = tk.Frame(c, bg=SURFACE)
        info_row.pack(fill='x', padx=8, pady=(4, 0))
        tk.Label(info_row, text='✓',
                 bg=SURFACE, fg=GREEN, font=(FONT_UI[0], 9, 'bold')).pack(side='left', padx=(0, 6))
        tk.Label(info_row, text='Randomized mouse personality per session (seeded)',
                 bg=SURFACE, fg=FG, font=FONT_UI).pack(side='left')
        tk.Label(info_row, text='[ALWAYS ON]', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold')).pack(side='left', padx=4)

        info_row = tk.Frame(c, bg=SURFACE)
        info_row.pack(fill='x', padx=8, pady=(2, 6))
        tk.Label(info_row, text='✓',
                 bg=SURFACE, fg=GREEN, font=(FONT_UI[0], 9, 'bold')).pack(side='left', padx=(0, 6))
        tk.Label(info_row, text='Watchdog: alerts if loop stalls > 10s',
                 bg=SURFACE, fg=FG, font=FONT_UI).pack(side='left')
        tk.Label(info_row, text='[ALWAYS ON]', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold')).pack(side='left', padx=4)

        tk.Frame(c, bg=BORDER, height=1).pack(fill='x', padx=6, pady=(4, 4))

        # 8. Mod crown detector — watches bottom-left chat for gold/silver crown pixels
        self.mod_crown_var = tk.BooleanVar(
            value=self.config.get('mod_crown_detection_enabled', False))
        row = toggle_row(c, 'Mod crown detector (stop if mod/admin speaks in chat)',
                         self.mod_crown_var)
        row.pack(anchor='w', padx=8, pady=(4, 0))
        _ab_label(row, 'OPT-IN')
        tk.Label(c, text='Watches chat bottom-left for gold/silver crown icons. '
                         '(Currently uses pixel-color detection, not template matching — '
                         'template-based detection is on the roadmap.)',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic')
                 ).pack(anchor='w', padx=30, pady=(0, 6))

        # Stop-on-chat-text — OCR chat for user-specified phrases
        self.chat_text_stop_var = tk.BooleanVar(
            value=self.config.get('chat_text_stop_enabled', True))
        row = toggle_row(c, 'Read chat for names — stop on match (e.g. Terror, Kleio)',
                         self.chat_text_stop_var)
        row.pack(anchor='w', padx=8, pady=(4, 0))
        _ab_label(row, 'DEFAULT ON')
        tk.Label(c, text='Names to watch for, separated by commas (case-insensitive):',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic')
                 ).pack(anchor='w', padx=30, pady=(0, 2))
        self.chat_text_phrases_var = tk.StringVar(
            value=','.join(self.config.get('chat_text_stop_phrases',
                                           ['Terror', 'Kleio'])))
        ttk.Entry(c, textvariable=self.chat_text_phrases_var
                  ).pack(fill='x', padx=30, pady=(0, 6))

        # Apply initial master state now that all sub-widgets exist
        self._apply_antiban_master_state()

    def _build_skill_placeholder(self, tab, name, blurb):
        """Stub tab for skills not yet implemented."""
        wrap = tk.Frame(tab, bg=BG)
        wrap.pack(fill='both', expand=True, padx=20, pady=20)
        tk.Label(wrap, text=name, bg=BG, fg=FG,
                 font=('Segoe UI', 16, 'bold')).pack(anchor='w', pady=(0, 6))
        tk.Label(wrap, text='Coming soon — built off the mining loop.',
                 bg=BG, fg=AMBER,
                 font=(FONT_UI[0], 10, 'italic')).pack(anchor='w', pady=(0, 10))
        tk.Label(wrap, text=blurb, bg=BG, fg=MUTED,
                 font=FONT_UI, wraplength=500, justify='left').pack(anchor='w')
        if name.startswith('Fighter'):
            sub = tk.Frame(wrap, bg=BG)
            sub.pack(anchor='w', pady=(20, 0))
            tk.Label(sub, text='Fight Loot:', bg=BG, fg=MUTED,
                     font=FONT_UI).pack(side='left', padx=(0, 8))
            cb = tk.Checkbutton(sub, text='Auto-loot drops', state='disabled',
                                bg=BG, fg=MUTED, selectcolor=BORDER,
                                font=FONT_UI)
            cb.pack(side='left')

    def _build_bot_slave_tab(self, tab, slot_idx):
        """Inline per-bot config tab for Bot2/3/4.
        Enable toggle at top grays out all content when off."""
        bot_name = f'Bot{slot_idx + 1}'
        slot = self._clients_config[slot_idx]
        ORE_LIST = ('coal_rock', 'mithril_rock', 'iron_rock', 'tin_rock', 'copper_rock')

        # Scrollable body
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview,
                               bg=BG, troughcolor=BG, width=18, highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>',
                  lambda _: (canvas.configure(scrollregion=canvas.bbox('all')),
                             canvas.itemconfig(win_id, width=canvas.winfo_width())))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        def _wheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
        canvas.bind('<Enter>', lambda _: canvas.bind_all('<MouseWheel>', _wheel))
        canvas.bind('<Leave>', lambda _: canvas.unbind_all('<MouseWheel>'))

        # ── Enable row ────────────────────────────────────────────────────────
        en_var = tk.BooleanVar(value=bool(slot.get('enabled', False)))
        self._client_enable_vars[slot_idx] = en_var

        en_co, en_c = card(body, padx=0, pady=4)
        en_co.pack(fill='x', padx=8, pady=(8, 4))
        en_row = tk.Frame(en_c, bg=SURFACE)
        en_row.pack(fill='x', padx=8, pady=6)
        tk.Label(en_row, text=bot_name, bg=SURFACE, fg=ACCENT,
                 font=('Segoe UI', 12, 'bold')).pack(side='left')
        Toggle(en_row, en_var, bg=SURFACE).pack(side='left', padx=(10, 0))
        en_status_lbl = tk.Label(en_row, text='', bg=SURFACE, fg=MUTED, font=FONT_UI)
        en_status_lbl.pack(side='left', padx=(8, 0))

        # Live status (dot + label + pause btn) shown inline on enable row
        pause_btn = ttk.Button(en_row, text='Pause',
                               command=lambda: self._toggle_pause_client(slot_idx),
                               style='Util.TButton')
        pause_btn.pack(side='right')
        status_lbl = tk.Label(en_row, text='not started', bg=SURFACE, fg=MUTED,
                              font=(FONT_UI[0], 8, 'italic'))
        status_lbl.pack(side='right', padx=(0, 6), fill='x', expand=True)
        dot_lbl = tk.Label(en_row, text='●', bg=SURFACE, fg=MUTED,
                           font=('Segoe UI', 10, 'bold'))
        dot_lbl.pack(side='right', padx=(0, 2))
        self._client_status_rows[slot_idx] = {
            'dot': dot_lbl, 'label': status_lbl, 'btn': pause_btn}

        # ── Window picker ─────────────────────────────────────────────────────
        win_co, win_c = card(body, padx=0, pady=4)
        win_co.pack(fill='x', padx=8, pady=(0, 4))
        win_row = tk.Frame(win_c, bg=SURFACE)
        win_row.pack(fill='x', padx=8, pady=6)
        tk.Label(win_row, text='Window:', bg=SURFACE, fg=FG,
                 font=FONT_UI, width=8, anchor='w').pack(side='left')
        saved_title = slot.get('window_title', '')
        cur = next((d for d, info in self._window_info_map.items()
                    if info['title'] == saved_title), '')
        wvar = tk.StringVar(value=cur)
        win_cb = ttk.Combobox(win_row, textvariable=wvar,
                              values=self._slave_window_choices(exclude_idx=slot_idx),
                              state='readonly', width=38)
        win_cb.pack(side='left', padx=(2, 4))
        def _on_win_selected(_e=None):
            display = wvar.get()
            info = self._window_info_map.get(display, {})
            slot['window_title'] = info.get('title', display)
            slot['_win_display'] = display  # in-memory: for direct hwnd lookup
            self._save_clients_config()
            self._refresh_clients_windows()
        win_cb.bind('<<ComboboxSelected>>', _on_win_selected)
        win_cb.bind('<MouseWheel>', lambda e: 'break')
        ttk.Button(win_row, text='Refresh', style='Util.TButton',
                   command=lambda cb=win_cb, si=slot_idx: (
                       cb.configure(values=self._slave_window_choices(exclude_idx=si))
                   )).pack(side='left', padx=(0, 4))
        self._client_window_combos.append((slot_idx, en_var, wvar, win_cb))

        # ── Content (grayed when disabled) ────────────────────────────────────
        content = tk.Frame(body, bg=BG)
        content.pack(fill='both', expand=True)

        # Ores
        ore_co, ore_c = card(content, padx=0, pady=4)
        ore_co.pack(fill='x', padx=8, pady=(0, 4))
        section_label(ore_c, 'Ores')
        ore_row = tk.Frame(ore_c, bg=SURFACE)
        ore_row.pack(fill='x', padx=8, pady=(0, 2))
        saved_ores = slot.get('ore_checkboxes', {})
        ore_vars = {ore: tk.BooleanVar(value=bool(saved_ores.get(ore, False)))
                    for ore in ORE_LIST}
        self._client_ore_vars[slot_idx] = ore_vars
        for ore in ORE_LIST:
            tk.Checkbutton(ore_row, text=ore, variable=ore_vars[ore],
                           bg=SURFACE, fg=FG, selectcolor=BORDER,
                           activebackground=SURFACE, activeforeground=FG,
                           font=FONT_UI).pack(side='left', padx=2)
        tk.Label(ore_c, text='Unchecked = inherit master ores',
                 bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 8, 'italic')).pack(anchor='w', padx=8, pady=(0, 4))

        # Mining Mode
        mm_co, mm_c = card(content, padx=0, pady=4)
        mm_co.pack(fill='x', padx=8, pady=(0, 4))
        section_label(mm_c, 'Mining Mode')
        pm_var = tk.BooleanVar(value=bool(slot.get('powermine_enabled', False)))
        pm_row = tk.Frame(mm_c, bg=SURFACE)
        pm_row.pack(anchor='w', padx=8, pady=(0, 4))
        Toggle(pm_row, pm_var, bg=SURFACE).pack(side='left', padx=(0, 8))
        tk.Label(pm_row, text='Powermine (never stop)',
                 bg=SURFACE, fg=FG, font=FONT_UI).pack(side='left')
        _saved_speed = slot.get('speed_mode')
        if _saved_speed not in ('fast', 'lazy', 'super_lazy'):
            _saved_speed = 'fast'
        sp_var = tk.StringVar(value=_saved_speed)
        sr = tk.Frame(mm_c, bg=SURFACE)
        sr.pack(fill='x', padx=8, pady=(0, 6))
        tk.Label(sr, text='Speed:', bg=SURFACE, fg=FG, font=FONT_UI).pack(side='left', padx=(0, 6))
        for _val, _txt in (('fast', 'Fast'), ('lazy', 'Lazy'), ('super_lazy', 'Super Lazy')):
            ttk.Radiobutton(sr, text=_txt, variable=sp_var, value=_val).pack(side='left', padx=4)
        def _save_mode(*_):
            slot['powermine_enabled'] = bool(pm_var.get())
            slot['speed_mode'] = sp_var.get()
            self._save_clients_config()
        pm_var.trace_add('write', _save_mode)
        sp_var.trace_add('write', _save_mode)
        spots_co, spots_c = card(content, padx=0, pady=4)
        spots_co.pack(fill='x', padx=8, pady=(0, 4))
        section_label(spots_c, 'Fixed Ore Spots')
        srow = tk.Frame(spots_c, bg=SURFACE)
        srow.pack(fill='x', padx=8, pady=(0, 6))
        spots = slot.get('fixed_ore_spots', [])
        spots_lbl = tk.Label(srow, text=f'{len(spots)} spot(s) saved',
                             bg=SURFACE, fg=MUTED, font=FONT_UI)
        spots_lbl.pack(side='left')
        ttk.Button(srow, text='Set spots…', style='Util.TButton',
                   command=lambda: self._capture_fixed_spots_for_slot(
                       slot_idx, spots_lbl)).pack(side='left', padx=(8, 0))
        def _clear_spots(s=slot, lbl=spots_lbl, si=slot_idx):
            # Close any open overlay for this slot before clearing
            _prev = getattr(self, f'_spot_overlay_{si}', None)
            if _prev is not None:
                try:
                    if _prev.winfo_exists():
                        _prev.destroy()
                except Exception:
                    pass
                setattr(self, f'_spot_overlay_{si}', None)
            s['fixed_ore_spots'] = []
            self._save_clients_config()
            lbl.config(text='0 spot(s) saved')
        ttk.Button(srow, text='Clear', style='Util.TButton',
                   command=_clear_spots).pack(side='left', padx=(4, 0))

        # Walkto
        wt_co, wt_c = card(content, padx=0, pady=4)
        wt_co.pack(fill='x', padx=8, pady=(0, 4))
        section_label(wt_c, 'WalkTo')
        wt_en_row = tk.Frame(wt_c, bg=SURFACE)
        wt_en_row.pack(fill='x', padx=8, pady=(0, 2))
        wt_var = tk.BooleanVar(value=bool(slot.get('walkto_enabled', True)))
        slot['_walkto_var'] = wt_var
        wt_cb = tk.Checkbutton(wt_en_row, text='Enable walkto for this client',
                              variable=wt_var,
                              bg=SURFACE, fg=FG, selectcolor=BORDER,
                              activebackground=SURFACE, activeforeground=FG,
                              font=FONT_UI)
        wt_cb.pack(side='left')
        rng_row = tk.Frame(wt_c, bg=SURFACE)
        rng_row.pack(fill='x', padx=8, pady=(0, 2))
        tk.Label(rng_row, text='Clicks before walkto:',
                 bg=SURFACE, fg=FG, font=FONT_UI).pack(side='left')
        wt_min = tk.StringVar(value=str(slot.get('walkto_min_clicks', 35)))
        wt_max = tk.StringVar(value=str(slot.get('walkto_max_clicks', 50)))
        slot['_wt_min'] = wt_min
        slot['_wt_max'] = wt_max
        tk.Spinbox(rng_row, from_=1, to=999, width=4, textvariable=wt_min,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(6, 2))
        tk.Label(rng_row, text='–', bg=SURFACE, fg=MUTED,
                 font=FONT_UI).pack(side='left')
        tk.Spinbox(rng_row, from_=1, to=999, width=4, textvariable=wt_max,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(2, 0))

        BANK_SHORT = ['None', 'Varrock East', 'Varrock West', 'Falador East',
                      'Falador West', 'Edgeville', 'Draynor', 'Al Kharid',
                      'Catherby', 'Seers', 'Ardougne North', 'Ardougne South']
        BANK_FULL  = ['None', 'Bank (Varrock East)', 'Bank (Varrock West)',
                      'Bank (Falador East)', 'Bank (Falador West)',
                      'Bank (Edgeville)', 'Bank (Draynor)', 'Bank (Al Kharid)',
                      'Bank (Catherby)', 'Bank (Seers)',
                      'Bank (Ardougne North)', 'Bank (Ardougne South)']
        tk.Label(wt_c, text='Bank destinations (bot picks randomly from non-blank):',
                 bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 8, 'italic')).pack(anchor='w', padx=8, pady=(4, 2))
        d_row = tk.Frame(wt_c, bg=SURFACE)
        d_row.pack(fill='x', padx=8, pady=(0, 2))
        a_var  = tk.StringVar(value=slot.get('walkto_dest_a', 'Varrock East'))
        b_var  = tk.StringVar(value=slot.get('walkto_dest_b', 'Bank (Varrock East)'))
        u_var  = tk.StringVar(value=slot.get('walkto_dest_user', ''))
        xy_var = tk.StringVar(value=slot.get('walkto_dest_xy', ''))
        slot['_dest_a'] = a_var; slot['_dest_b'] = b_var
        slot['_dest_user'] = u_var; slot['_dest_xy'] = xy_var
        ttk.Combobox(d_row, textvariable=a_var, values=BANK_SHORT,
                     state='normal', width=13).pack(side='left', padx=(0, 2))
        tk.Label(d_row, text='&', bg=SURFACE, fg=MUTED,
                 font=FONT_UI).pack(side='left', padx=2)
        ttk.Combobox(d_row, textvariable=b_var, values=BANK_FULL,
                     state='normal', width=17).pack(side='left', padx=(0, 4))
        d_row2 = tk.Frame(wt_c, bg=SURFACE)
        d_row2.pack(fill='x', padx=8, pady=(0, 6))
        tk.Label(d_row2, text='User Set:', bg=SURFACE, fg=MUTED,
                 font=FONT_UI).pack(side='left')
        tk.Entry(d_row2, textvariable=u_var, bg=BORDER, fg=FG,
                 insertbackground=FG, relief='flat',
                 font=('Consolas', 9), width=16).pack(side='left', padx=(4, 8))
        tk.Label(d_row2, text='X,Y:', bg=SURFACE, fg=MUTED,
                 font=FONT_UI).pack(side='left')
        tk.Entry(d_row2, textvariable=xy_var, bg=BORDER, fg=FG,
                 insertbackground=FG, relief='flat',
                 font=('Consolas', 9), width=9).pack(side='left', padx=(4, 0))

        # Auto-persist walkto changes
        def _auto_save(*_):
            slot['walkto_enabled'] = bool(wt_var.get())
            for k, v in (('walkto_min_clicks', wt_min), ('walkto_max_clicks', wt_max)):
                try: slot[k] = int(v.get())
                except (ValueError, tk.TclError): pass
            for k, v in (('walkto_dest_a', a_var), ('walkto_dest_b', b_var),
                         ('walkto_dest_user', u_var), ('walkto_dest_xy', xy_var)):
                slot[k] = v.get()
            self._save_clients_config()
        for _v in (wt_var, wt_min, wt_max, a_var, b_var, u_var, xy_var):
            _v.trace_add('write', _auto_save)

        # Task var (always Mining)
        t_var = tk.StringVar(value='Mining')
        self._client_task_vars[slot_idx] = t_var

        # Powermine → Walkto interlock: powermine ON forces walkto OFF
        def _pm_walkto_interlock(*_):
            if pm_var.get():
                wt_var.set(False)
                try:
                    wt_cb.config(state='disabled')
                except Exception:
                    pass
            else:
                try:
                    wt_cb.config(state='normal')
                except Exception:
                    pass
        pm_var.trace_add('write', _pm_walkto_interlock)
        _pm_walkto_interlock()  # apply initial state

        # ── Enable / disable content graying ──────────────────────────────────
        _init_done = [False]
        def _apply_enable(*_):
            enabled = bool(en_var.get())
            en_status_lbl.config(
                text='Enabled' if enabled else 'Disabled',
                fg=GREEN if enabled else MUTED)
            new_state = 'normal' if enabled else 'disabled'
            def _walk(w):
                try:
                    cls = w.winfo_class()
                    if cls in ('TCheckbutton', 'Checkbutton', 'TEntry', 'Entry',
                               'Spinbox', 'TCombobox', 'TButton', 'Button'):
                        w.configure(state=new_state)
                except Exception:
                    pass
                for ch in w.winfo_children():
                    _walk(ch)
            _walk(content)
            if enabled:
                _pm_walkto_interlock()  # re-apply powermine→walkto interlock
            try:
                win_cb.configure(state='readonly' if enabled else 'disabled')
            except Exception:
                pass
            if _init_done[0]:
                slot['enabled'] = enabled
                self._save_clients_config()

        en_var.trace_add('write', _apply_enable)
        _apply_enable()   # set initial visual state without saving
        _init_done[0] = True

    def _build_clients_tab(self, tab):
        """Replaced by per-bot tabs (Bot2/Bot3/Bot4) built in _build_ui."""
        pass

    # ── Live Status (per-client) ────────────────────────────────────────────

    def _schedule_clients_status_update(self):
        """Refresh the Live Status rows ~3x/sec while the GUI is up."""
        try:
            self._refresh_clients_status()
        except Exception:
            pass
        try:
            self.root.after(350, self._schedule_clients_status_update)
        except Exception:
            pass

    def _refresh_clients_status(self):
        rows = getattr(self, '_client_status_rows', {})
        if not rows:
            return
        bots = list(getattr(self, 'bots', []) or [])
        en_vars = getattr(self, '_client_enable_vars', [None] * 4)
        for idx, ui in rows.items():
            # Master (idx 0) is always enabled.
            en_var = en_vars[idx] if idx < len(en_vars) else None
            enabled = True if idx == 0 else bool(en_var.get()) if en_var is not None else False
            sub = bots[idx] if idx < len(bots) else None

            if not enabled:
                # Greyed-out / inactive slot.
                ui['dot'].config(fg=BORDER)
                ui['label'].config(text='(disabled — enable on card to use)',
                                   fg=BORDER)
                ui['btn'].config(text='Pause', state='disabled')
                continue

            if sub is None:
                ui['dot'].config(fg=MUTED)
                ui['label'].config(text='ready (not started)', fg=MUTED)
                ui['btn'].config(text='Pause', state='disabled')
                continue
            if not sub.running:
                ui['dot'].config(fg=RED)
                reason = (sub.stop_reason or 'stopped')
                ui['label'].config(text=f'STOPPED — {reason}', fg=MUTED)
                ui['btn'].config(text='Pause', state='disabled')
            elif sub.paused:
                ui['dot'].config(fg=AMBER)
                ui['label'].config(text=f'PAUSED — last: {sub.last_action}',
                                   fg=AMBER)
                ui['btn'].config(text='Resume', state='normal')
            else:
                ui['dot'].config(fg=GREEN)
                age = max(0, time.time() - sub.last_action_ts)
                # Append walkto countdown if enabled
                wt_suffix = ''
                if sub.config.get('walkto_enabled', False):
                    nxt = getattr(sub, '_walkto_next_at', None)
                    cur = getattr(sub, '_mine_count', 0)
                    if nxt is not None:
                        wt_suffix = f'  |  walkto in {max(0, nxt - cur)} clicks'
                ui['label'].config(text=f'ACTIVE — {sub.last_action} '
                                        f'({age:.0f}s ago){wt_suffix}', fg=FG)
                ui['btn'].config(text='Pause', state='normal')

    def _toggle_pause_client(self, slot_idx):
        bots = list(getattr(self, 'bots', []) or [])
        if slot_idx >= len(bots):
            return
        sub = bots[slot_idx]
        if not sub.running:
            return
        bot_name = 'Bot' if slot_idx == 0 else f'Bot{slot_idx + 1}'
        if sub.paused:
            sub.resume()
            self.log_debug(f'{bot_name} resumed')
        else:
            sub.pause()
            self.log_debug(f'{bot_name} paused')

    # ── Per-client Profiles ─────────────────────────────────────────────────

    def _client_profiles_dir(self):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'profiles', 'clients')
        os.makedirs(d, exist_ok=True)
        return d

    def _list_client_profiles(self):
        try:
            return sorted([f[:-5] for f in os.listdir(self._client_profiles_dir())
                           if f.endswith('.json')])
        except Exception:
            return []

    def _client_profile_path(self, name):
        safe = ''.join(ch for ch in name if ch.isalnum() or ch in ('_', '-')).strip('_-')
        return os.path.join(self._client_profiles_dir(), f'{safe or "unnamed"}.json')

    # Fields a per-client profile snapshot owns.
    _CLIENT_PROFILE_KEYS = (
        'task', 'ore_checkboxes',
        'walkto_enabled', 'walkto_min_clicks', 'walkto_max_clicks',
        'walkto_dest_a', 'walkto_dest_b', 'walkto_dest_user', 'walkto_dest_xy',
        'fixed_ore_spots',
    )

    def _save_client_profile(self, slot_idx, name):
        if not name.strip():
            messagebox.showwarning('Profiles', 'Type a profile name first.')
            return
        # Flush card-bound vars into slot first.
        self._save_clients_config()
        slot = self._clients_config[slot_idx]
        snap = {k: slot[k] for k in self._CLIENT_PROFILE_KEYS if k in slot}
        path = self._client_profile_path(name)
        if os.path.exists(path):
            if not messagebox.askyesno('Overwrite?',
                                       f'Profile "{name}" exists. Overwrite?'):
                return
        try:
            with open(path, 'w') as f:
                json.dump(snap, f, indent=2)
            self.log_debug(f'Client profile saved: {name}')
            # Refresh every card's dropdown.
            for s in self._clients_config:
                cb = s.get('_profile_combo')
                if cb is not None:
                    cb['values'] = self._list_client_profiles()
        except Exception as e:
            messagebox.showerror('Profile save error', str(e))

    def _apply_client_profile(self, slot_idx, name):
        path = self._client_profile_path(name)
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror('Profile load error', str(e))
            return
        slot = self._clients_config[slot_idx]
        for k in self._CLIENT_PROFILE_KEYS:
            if k in data:
                slot[k] = data[k]
        # Push loaded values into any card-bound vars.
        if 'task' in data:
            t_var = self._client_task_vars[slot_idx] if slot_idx < len(self._client_task_vars) else None
            if t_var is not None:
                t_var.set(data['task'])
        if 'ore_checkboxes' in data:
            ov = self._client_ore_vars[slot_idx] if slot_idx < len(self._client_ore_vars) else {}
            for k, v in ov.items():
                v.set(bool(data['ore_checkboxes'].get(k, False)))
        self._save_clients_config()
        self.log_debug(f'Client {slot_idx + 1} loaded profile: {name}')

    # ── Global Profiles ─────────────────────────────────────────────────────

    def _list_profiles(self):
        try:
            return sorted([f[:-5] for f in os.listdir(self._profiles_dir)
                           if f.endswith('.json')])
        except Exception:
            return []

    def _profile_path(self, name):
        safe = ''.join(ch for ch in name if ch.isalnum() or ch in ('_', '-')).strip('_-')
        return os.path.join(self._profiles_dir, f'{safe or "unnamed"}.json')

    def _profile_save(self):
        name = (self.profile_var.get() or '').strip()
        if not name:
            messagebox.showwarning('Profiles', 'Type a profile name first '
                                               '(e.g. "faladorironbank").')
            return
        # Persist current GUI state into self.config before snapshotting.
        try: self.save_config()
        except Exception: pass
        path = self._profile_path(name)
        if os.path.exists(path):
            if not messagebox.askyesno('Overwrite?',
                                       f'Profile "{name}" exists. Overwrite?'):
                return
        try:
            snap = {k: v for k, v in self.config.items() if not k.startswith('_')}
            with open(path, 'w') as f:
                json.dump(snap, f, indent=2)
            self.log_debug(f'Profile saved: {name}')
            self._profile_combo['values'] = self._list_profiles()
        except Exception as e:
            messagebox.showerror('Profile save error', str(e))

    def _profile_load(self):
        name = (self.profile_var.get() or '').strip()
        if not name:
            messagebox.showwarning('Profiles', 'Pick a profile to load.')
            return
        path = self._profile_path(name)
        if not os.path.exists(path):
            messagebox.showwarning('Profiles', f'Profile "{name}" not found.')
            return
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror('Profile load error', str(e))
            return
        # Merge into the active config (don't lose unrelated runtime fields),
        # then write to config.json and trigger a GUI restart so all widgets
        # rebind to the new values.
        for k, v in data.items():
            self.config[k] = v
        try:
            with open('config.json', 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            messagebox.showerror('Profile load error', f'Saved but reload failed: {e}')
            return
        self._restart = True
        self.on_closing()

    def _profile_delete(self):
        name = (self.profile_var.get() or '').strip()
        if not name:
            return
        path = self._profile_path(name)
        if not os.path.exists(path):
            return
        if not messagebox.askyesno('Delete?', f'Delete profile "{name}"?'):
            return
        try:
            os.remove(path)
            self.log_debug(f'Profile deleted: {name}')
            self._profile_combo['values'] = self._list_profiles()
            self.profile_var.set('')
        except Exception as e:
            messagebox.showerror('Profile delete error', str(e))

    def _open_client_settings(self, slot_idx):
        """Per-bot settings popup. Covers ores, fixed spots, and walkto for Bot2/3/4."""
        t_var = self._client_task_vars[slot_idx] if slot_idx < len(self._client_task_vars) else None
        if t_var is None:
            return
        ore_vars = self._client_ore_vars[slot_idx] if slot_idx < len(self._client_ore_vars) else {}
        slot = self._clients_config[slot_idx]

        bot_name = f'Bot{slot_idx + 1}'
        win = tk.Toplevel(self.root)
        win.title(f'{bot_name} Settings')
        win.configure(bg=BG)
        win.transient(self.root)
        win.geometry('420x400')
        win.resizable(False, False)

        # Mining-only build: no mode picker; force task to "Mining".
        t_var.set('Mining')

        body = tk.Frame(win, bg=BG)
        body.pack(fill='both', expand=True, padx=12, pady=(12, 6))

        def _render_body(*_):
            for w in body.winfo_children():
                w.destroy()
            mode = t_var.get()
            if mode.startswith('Mining'):
                # Ores
                tk.Label(body, text='Ores', bg=BG, fg=FG,
                         font=FONT_HDR).pack(anchor='w', pady=(6, 2))
                row = tk.Frame(body, bg=BG)
                row.pack(fill='x', pady=(0, 6))
                for ore in ('copper', 'tin', 'iron', 'coal', 'mithril', 'adamantite'):
                    tk.Checkbutton(row, text=ore, variable=ore_vars[ore],
                                   bg=BG, fg=FG, selectcolor=BORDER,
                                   activebackground=BG, activeforeground=FG,
                                   font=FONT_UI).pack(side='left', padx=2)
                tk.Label(body, text='(unchecked = inherit Master / Mining tab)',
                         bg=BG, fg=MUTED,
                         font=(FONT_UI[0], 8, 'italic')).pack(anchor='w')

                # Fixed ore spots — per-bot capture + clear buttons.
                tk.Label(body, text='Fixed ore spots', bg=BG, fg=FG,
                         font=FONT_HDR).pack(anchor='w', pady=(10, 2))
                spots_row = tk.Frame(body, bg=BG)
                spots_row.pack(fill='x', pady=(0, 6))
                spots = slot.get('fixed_ore_spots', [])
                spots_lbl = tk.Label(spots_row,
                                     text=f'{len(spots)} spot(s) saved',
                                     bg=BG, fg=MUTED, font=FONT_UI)
                spots_lbl.pack(side='left')
                ttk.Button(spots_row, text='Set spots…',
                           style='Util.TButton',
                           command=lambda: self._capture_fixed_spots_for_slot(
                               slot_idx, spots_lbl)).pack(side='left', padx=(8, 0))
                def _clear_spots(s=slot, lbl=spots_lbl):
                    s['fixed_ore_spots'] = []
                    self._save_clients_config()
                    lbl.config(text='0 spot(s) saved')
                ttk.Button(spots_row, text='Clear',
                           style='Util.TButton',
                           command=_clear_spots).pack(side='left', padx=(4, 0))

                # Walkto enable + min/max — destinations live on Master Mining tab.
                tk.Label(body, text='Walkto', bg=BG, fg=FG,
                         font=FONT_HDR).pack(anchor='w', pady=(10, 2))
                wt_row = tk.Frame(body, bg=BG)
                wt_row.pack(fill='x', pady=(0, 2))
                wt_var = tk.BooleanVar(value=bool(slot.get('walkto_enabled', True)))
                tk.Checkbutton(wt_row, text='Enable walkto for this client',
                               variable=wt_var,
                               bg=BG, fg=FG, selectcolor=BORDER,
                               activebackground=BG, activeforeground=FG,
                               font=FONT_UI).pack(side='left')
                slot['_walkto_var'] = wt_var
                rng_row = tk.Frame(body, bg=BG)
                rng_row.pack(fill='x', pady=(0, 2))
                tk.Label(rng_row, text='Clicks before walkto:',
                         bg=BG, fg=FG, font=FONT_UI).pack(side='left')
                wt_min = tk.StringVar(value=str(slot.get('walkto_min_clicks', 35)))
                wt_max = tk.StringVar(value=str(slot.get('walkto_max_clicks', 50)))
                tk.Spinbox(rng_row, from_=1, to=999, width=4,
                           textvariable=wt_min,
                           bg=SURFACE, fg=FG, relief='flat',
                           font=FONT_UI).pack(side='left', padx=(6, 2))
                tk.Label(rng_row, text='–', bg=BG, fg=MUTED,
                         font=FONT_UI).pack(side='left')
                tk.Spinbox(rng_row, from_=1, to=999, width=4,
                           textvariable=wt_max,
                           bg=SURFACE, fg=FG, relief='flat',
                           font=FONT_UI).pack(side='left', padx=(2, 0))
                slot['_wt_min'] = wt_min
                slot['_wt_max'] = wt_max

                # Per-client walkto destinations (Bank only; train hidden until F4 hotkey lands).
                BANK_SHORT = ['None', 'Varrock East', 'Varrock West',
                              'Falador East', 'Falador West', 'Edgeville',
                              'Draynor', 'Al Kharid', 'Catherby', 'Seers',
                              'Ardougne North', 'Ardougne South']
                BANK_FULL = ['None', 'Bank (Varrock East)', 'Bank (Varrock West)',
                             'Bank (Falador East)', 'Bank (Falador West)',
                             'Bank (Edgeville)', 'Bank (Draynor)',
                             'Bank (Al Kharid)', 'Bank (Catherby)',
                             'Bank (Seers)', 'Bank (Ardougne North)',
                             'Bank (Ardougne South)']
                tk.Label(body, text='Bank destinations (random pick from non-blank):',
                         bg=BG, fg=MUTED,
                         font=(FONT_UI[0], 8, 'italic')).pack(anchor='w', pady=(4, 2))
                d_row = tk.Frame(body, bg=BG)
                d_row.pack(fill='x', pady=(0, 2))
                a_var = tk.StringVar(value=slot.get('walkto_dest_a', 'Varrock East'))
                b_var = tk.StringVar(value=slot.get('walkto_dest_b', 'Bank (Varrock East)'))
                u_var = tk.StringVar(value=slot.get('walkto_dest_user', ''))
                xy_var = tk.StringVar(value=slot.get('walkto_dest_xy', ''))
                ttk.Combobox(d_row, textvariable=a_var, values=BANK_SHORT,
                             state='normal', width=14).pack(side='left', padx=(0, 2))
                tk.Label(d_row, text='&', bg=BG, fg=MUTED,
                         font=FONT_UI).pack(side='left', padx=2)
                ttk.Combobox(d_row, textvariable=b_var, values=BANK_FULL,
                             state='normal', width=18).pack(side='left', padx=(0, 4))
                d_row2 = tk.Frame(body, bg=BG)
                d_row2.pack(fill='x', pady=(0, 4))
                tk.Label(d_row2, text='User Set:', bg=BG, fg=MUTED,
                         font=FONT_UI).pack(side='left')
                tk.Entry(d_row2, textvariable=u_var, bg=SURFACE, fg=FG,
                         insertbackground=FG, relief='flat',
                         font=('Consolas', 9), width=18).pack(side='left', padx=(4, 8))
                tk.Label(d_row2, text='X,Y:', bg=BG, fg=MUTED,
                         font=FONT_UI).pack(side='left')
                tk.Entry(d_row2, textvariable=xy_var, bg=SURFACE, fg=FG,
                         insertbackground=FG, relief='flat',
                         font=('Consolas', 9), width=10).pack(side='left', padx=(4, 0))
                slot['_dest_a'] = a_var
                slot['_dest_b'] = b_var
                slot['_dest_user'] = u_var
                slot['_dest_xy'] = xy_var
            else:
                tk.Label(body,
                         text=f'{mode} settings — coming soon.\n'
                              'Once this mode is implemented, its options will appear here.',
                         bg=BG, fg=AMBER,
                         font=(FONT_UI[0], 10, 'italic'),
                         justify='left').pack(anchor='w', pady=20)

        t_var.trace_add('write', _render_body)
        _render_body()

        # Save-as-profile row (per-client snapshot).
        prof_row = tk.Frame(win, bg=BG)
        prof_row.pack(fill='x', padx=12, pady=(6, 0))
        tk.Label(prof_row, text='Save as profile:', bg=BG, fg=MUTED,
                 font=(FONT_UI[0], 8)).pack(side='left')
        save_name_var = tk.StringVar(value='')
        tk.Entry(prof_row, textvariable=save_name_var, bg=SURFACE, fg=FG,
                 insertbackground=FG, relief='flat',
                 font=('Consolas', 9), width=20).pack(side='left', padx=(4, 4))
        ttk.Button(prof_row, text='Save profile',
                   style='Util.TButton',
                   command=lambda: self._save_client_profile(slot_idx,
                                                             save_name_var.get())
                   ).pack(side='left')

        # Save / Close buttons
        btns = tk.Frame(win, bg=BG)
        btns.pack(fill='x', padx=12, pady=(0, 10))
        def _save_and_close():
            # Persist the per-client fields that the popup directly owns. Vars
            # bound to the card already persist via _save_clients_config.
            wt_var = slot.get('_walkto_var')
            wt_min_var = slot.get('_wt_min')
            wt_max_var = slot.get('_wt_max')
            if wt_var is not None:
                slot['walkto_enabled'] = bool(wt_var.get())
            for k, v in (('walkto_min_clicks', wt_min_var),
                         ('walkto_max_clicks', wt_max_var)):
                if v is not None:
                    try:
                        slot[k] = int(v.get())
                    except (ValueError, tk.TclError):
                        pass
            for k, var_key in (('walkto_dest_a', '_dest_a'),
                               ('walkto_dest_b', '_dest_b'),
                               ('walkto_dest_user', '_dest_user'),
                               ('walkto_dest_xy', '_dest_xy')):
                v = slot.get(var_key)
                if v is not None:
                    slot[k] = v.get()
            self._save_clients_config()
            win.destroy()
        ttk.Button(btns, text='Save', style='Util.TButton',
                   command=_save_and_close).pack(side='right', padx=(6, 0))
        ttk.Button(btns, text='Close', style='Util.TButton',
                   command=win.destroy).pack(side='right')

    def _capture_fixed_spots_for_slot(self, slot_idx, label_widget):
        """Open click-capture overlay and write relative spots into clients[slot_idx]."""
        # Destroy any previously-open overlay for this slot so clicks don't stack.
        prev = getattr(self, f'_spot_overlay_{slot_idx}', None)
        if prev is not None:
            try:
                if prev.winfo_exists():
                    prev.destroy()
            except Exception:
                pass
        setattr(self, f'_spot_overlay_{slot_idx}', None)

        slot = self._clients_config[slot_idx]
        title = slot.get('window_title', '')
        if not title:
            messagebox.showwarning('Fixed Spots',
                                   f'Bot{slot_idx + 1} has no window picked yet.')
            return
        # Case-insensitive search + partial fallback (handles RSCRevolution, RSCRevolution 2, etc.)
        # Try direct lookup via the stored display string — handles same-title windows
        hwnd = None
        cached_display = slot.get('_win_display', '')
        if cached_display and cached_display in self._window_info_map:
            hwnd = self._window_info_map[cached_display].get('hwnd')
        # Fall back to EnumWindows title search
        if not hwnd:
            exact_hits = []
            partial_hits = []
            def _enum_fixed(h, _):
                txt = win32gui.GetWindowText(h)
                if not txt:
                    return True
                if txt.lower() == title.lower():
                    exact_hits.append(h)
                elif title.lower() in txt.lower() or txt.lower() in title.lower():
                    partial_hits.append(h)
                return True
            win32gui.EnumWindows(_enum_fixed, None)
            hwnd = exact_hits[0] if exact_hits else (partial_hits[0] if partial_hits else None)
        if not hwnd:
            messagebox.showwarning('Fixed Spots',
                                   f'Could not find window "{title}".\n'
                                   'Make sure the game is running and a window is selected.')
            return
        try:
            rect = win32gui.GetClientRect(hwnd)
            pt = win32gui.ClientToScreen(hwnd, (0, 0))
            gx, gy, gw, gh = pt[0], pt[1], rect[2], rect[3]
        except Exception:
            messagebox.showerror('Fixed Spots', 'Could not read window position.')
            return

        sel = tk.Toplevel(self.root)
        setattr(self, f'_spot_overlay_{slot_idx}', sel)
        sel.title(f'Bot{slot_idx + 1} — pick up to 3 ore spots')
        sel.geometry(f'{gw}x{gh}+{gx}+{gy}')
        sel.attributes('-topmost', True)
        sel.attributes('-alpha', 0.35)
        sel.configure(bg='black')
        sel.overrideredirect(True)
        canvas = tk.Canvas(sel, bg='black', highlightthickness=0, cursor='crosshair')
        canvas.pack(fill='both', expand=True)
        instr = canvas.create_text(gw // 2, 22,
                           text=f'Bot{slot_idx + 1}  |  Click up to 3 spots  '
                                '|  Right-click to undo  |  Enter/Esc to confirm',
                           fill='white', font=('Consolas', 11, 'bold'))

        spots = list(slot.get('fixed_ore_spots', []))
        markers = []
        colors = ['#ff4444', '#ffaa00', '#44ddff']
        def _redraw():
            for m in markers:
                canvas.delete(m)
            markers.clear()
            for i, (rx, ry) in enumerate(spots):
                sx, sy = int(rx * gw), int(ry * gh)
                r = 18
                markers.append(canvas.create_oval(sx-r, sy-r, sx+r, sy+r,
                                                  outline=colors[i], width=3, fill=''))
                markers.append(canvas.create_text(sx, sy, text=str(i+1),
                                                  fill=colors[i],
                                                  font=('Consolas', 13, 'bold')))
            # Show confirm prompt once 3 spots chosen
            if len(spots) >= 3:
                canvas.itemconfig(instr,
                    text='3 spots selected — press Enter, click here, or Esc to confirm')
        _redraw()

        def _on_click(e):
            # If 3 spots already picked, treat any click as confirm
            if len(spots) >= 3:
                _confirm()
                return
            spots.append((e.x / gw, e.y / gh))
            _redraw()
        def _on_right(_e):
            if spots:
                spots.pop()
                _redraw()
        def _confirm(_e=None):
            if not sel.winfo_exists():
                return
            slot['fixed_ore_spots'] = list(spots)
            self._save_clients_config()
            try:
                label_widget.config(text=f'{len(spots)} spot(s) saved')
            except Exception:
                pass
            setattr(self, f'_spot_overlay_{slot_idx}', None)
            sel.destroy()

        canvas.bind('<Button-1>', _on_click)
        canvas.bind('<Button-3>', _on_right)
        # Bind keys to both canvas AND sel; overrideredirect windows can lose
        # keyboard focus — grab_set forces it.
        sel.bind('<Return>', _confirm)
        sel.bind('<Escape>', _confirm)
        canvas.bind('<Return>', _confirm)
        canvas.bind('<Escape>', _confirm)
        canvas.focus_set()
        sel.grab_set()
        sel.focus_force()

    def _jump_to_task_tab(self, task_name):
        """Switch the top-level notebook to the tab matching the given task."""
        nb = None
        for w in self.root.winfo_children():
            for ch in w.winfo_children() if hasattr(w, 'winfo_children') else []:
                if isinstance(ch, ttk.Notebook):
                    nb = ch
                    break
            if nb:
                break
        # Fallback: scan all descendants.
        if nb is None:
            stack = list(self.root.winfo_children())
            while stack:
                w = stack.pop()
                if isinstance(w, ttk.Notebook):
                    nb = w
                    break
                stack.extend(w.winfo_children())
        if nb is None:
            return
        # Map task name to tab text prefix.
        wanted = task_name.split(' (')[0].strip()
        for i in range(nb.index('end')):
            try:
                txt = nb.tab(i, 'text').strip()
            except Exception:
                continue
            if txt.startswith(wanted):
                nb.select(i)
                return

    def _slot_assignments(self):
        """Return dict {window_title: tag} for every window already chosen by
        any slot. Tag is 'bot' for Bot (master), 'bot N' for Bot2/3/4."""
        out = {}
        master = getattr(self, 'window_var', None)
        if master is not None:
            t = self._title_from_display(master.get())
            if t:
                out[t] = 'master'
        for entry in getattr(self, '_client_window_combos', []):
            idx, _en, wvar, _cb = entry
            display = wvar.get()
            if display.endswith('  (master)'):
                display = display[:-len('  (master)')]
            elif ')' in display and ' (client ' in display:
                display = display.rsplit('  (client ', 1)[0]
            t = self._window_info_map.get(display, {}).get('title')
            if t and t not in out:
                out[t] = f'client {idx + 1}'
        return out

    def _slave_window_choices(self, exclude_idx=None):
        """Return all detected Java windows — no filtering."""
        return self.get_java_windows()

    def _refresh_clients_windows(self):
        for entry in getattr(self, '_client_window_combos', []):
            idx, _en, _wvar, cb = entry
            cb['values'] = self._slave_window_choices(exclude_idx=idx)

    def _save_clients_config(self):
        """Persist Bot2/3/4 cards to config['clients'] (slot 0 = master = unchanged)."""
        clients = [{} for _ in range(4)]
        for (idx, en_var, wvar, _cb) in self._client_window_combos:
            display = wvar.get()
            if display.endswith('  (master)'):
                display = display[:-len('  (master)')]
            elif '  (client ' in display:
                display = display.rsplit('  (client ', 1)[0]
            elif '  (bot' in display.lower():
                display = display.rsplit('  (', 1)[0]
            info = self._window_info_map.get(display, {})
            # Index by slot (idx), not iteration order (i).
            ore_vars = self._client_ore_vars[idx] if idx < len(self._client_ore_vars) else {}
            task_var = self._client_task_vars[idx] if idx < len(self._client_task_vars) else None
            slot_in = self._clients_config[idx] if idx < len(self._clients_config) else {}
            ores = {k: v.get() for k, v in ore_vars.items()}
            # Prefer the title stored directly on slot (set immediately on selection)
            # over the _window_info_map lookup which may fail if the display string drifted.
            saved_title = slot_in.get('window_title', '') or info.get('title', '')
            entry = {
                'enabled': bool(en_var.get()),
                'window_title': saved_title,
            }
            if task_var:
                entry['task'] = task_var.get()
            if any(ores.values()):
                entry['ore_checkboxes'] = ores
            # Preserve fields owned directly by the slot dict.
            for k in ('walkto_enabled', 'walkto_min_clicks', 'walkto_max_clicks',
                      'walkto_dest_a', 'walkto_dest_b',
                      'walkto_dest_user', 'walkto_dest_xy',
                      'fixed_ore_spots', 'powermine_enabled', 'speed_mode'):
                if k in slot_in:
                    entry[k] = slot_in[k]
            clients[idx] = entry
        self.config['clients'] = clients
        self.save_config()
        enabled_count = sum(1 for c in clients[1:] if c.get('enabled') and c.get('window_title'))
        self.log_debug(f'Saved bots config ({enabled_count} bot(s) enabled)')

    def _build_experimental_tab(self, tab):
        """Experimental features tab."""
        canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
        vscroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview,
                               bg=BG, troughcolor=BG, width=18, highlightthickness=0, bd=0)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = tk.Frame(canvas, bg=BG)
        win_id = canvas.create_window((0, 0), window=body, anchor='nw')
        def _resize(e=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.itemconfig(win_id, width=canvas.winfo_width())
        body.bind('<Configure>', _resize)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win_id, width=e.width))
        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        canvas.bind('<Enter>', lambda _: canvas.bind_all('<MouseWheel>', _wheel))
        canvas.bind('<Leave>', lambda _: canvas.unbind_all('<MouseWheel>'))

        # ── Teleport Detector (moved from Anti-Ban) ─────────────────────────
        co_tp, c_tp = card(body, padx=0, pady=6)
        co_tp.pack(fill='x', pady=(0, 6))
        section_label(c_tp, 'Teleport Detector  [Experimental]')

        self.teleport_detect_var = tk.BooleanVar(
            value=self.config.get('teleport_detection_enabled', True))
        toggle_row(c_tp, 'Stop if scenery changes drastically  [DEFAULT ON]',
                   self.teleport_detect_var).pack(anchor='w', padx=8, pady=(2, 2))

        self.teleport_thresh_var = tk.IntVar(
            value=int(self.config.get('teleport_threshold', 35)))
        tr = tk.Frame(c_tp, bg=SURFACE)
        tr.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(tr, text='Sensitivity', bg=SURFACE, fg=MUTED,
                 font=FONT_UI, width=10, anchor='w').pack(side='left')
        tp_lbl = tk.Label(tr, text=str(self.teleport_thresh_var.get()),
                          bg=BORDER, fg=ACCENT, font=('Consolas', 8, 'bold'), width=4)
        tp_lbl.pack(side='right', padx=4)
        ttk.Scale(tr, from_=15, to=80, orient='horizontal',
                  variable=self.teleport_thresh_var,
                  command=lambda v: (self.teleport_thresh_var.set(int(float(v))),
                                     tp_lbl.config(text=str(int(float(v)))))
                  ).pack(side='left', fill='x', expand=True)

        # On-trigger chat reactions: preset multi-select + custom + random pick.
        tk.Label(c_tp, text='On-trigger chat reactions:',
                 bg=SURFACE, fg=FG, font=FONT_UI).pack(anchor='w', padx=8, pady=(4, 2))

        self.teleport_pick_random_var = tk.BooleanVar(
            value=bool(self.config.get('teleport_pick_random', True)))
        tk.Checkbutton(c_tp, text='Let bot randomly pick from enabled reactions',
                       variable=self.teleport_pick_random_var,
                       bg=SURFACE, fg=FG, selectcolor=BORDER,
                       activebackground=SURFACE, activeforeground=FG,
                       font=FONT_UI).pack(anchor='w', padx=14, pady=(0, 2))

        TELEPORT_DEFAULT = ('wtf,waeaw,what,okay,hey,what thef,whatfhekfk,wut,'
                            'wowa,wow,hello??,admin?,what is there an admin here?,'
                            'who tp,why tp,what tpd me for')

        tk.Label(c_tp, text='Edit this if you want, separated by , commas, no spacing.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic')
                 ).pack(anchor='w', padx=14, pady=(2, 2))

        self.teleport_reactions_var = tk.StringVar(
            value=self.config.get('teleport_reactions_text', TELEPORT_DEFAULT))
        ent = ttk.Entry(c_tp, textvariable=self.teleport_reactions_var,
                        style='TEntry')
        ent.pack(fill='x', padx=14, pady=(0, 6))

        def _save_tp(*_):
            self.config['teleport_detection_enabled'] = bool(self.teleport_detect_var.get())
            try:
                self.config['teleport_threshold'] = int(self.teleport_thresh_var.get())
            except (ValueError, tk.TclError):
                pass
            self.config['teleport_reactions_text'] = self.teleport_reactions_var.get()
            self.config['teleport_pick_random'] = bool(self.teleport_pick_random_var.get())
            try: self.save_config()
            except Exception: pass
        self.teleport_reactions_var.trace_add('write', _save_tp)
        self.teleport_pick_random_var.trace_add('write', _save_tp)
        self.teleport_detect_var.trace_add('write', _save_tp)
        self.teleport_thresh_var.trace_add('write', _save_tp)

        # ── Anti-AFK (formerly Clickback) ───────────────────────────────────
        co_cb, c_cb = card(body, padx=0, pady=6)
        co_cb.pack(fill='x', pady=(0, 6))
        section_label(c_cb, 'Anti-AFK  [Experimental]')

        self.clickback_var = tk.BooleanVar(value=self.config.get('clickback_enabled', False))
        self.clickback_var.trace_add('write', self._on_clickback_change)
        toggle_row(c_cb, 'Enable periodic Anti-AFK clicks',
                   self.clickback_var).pack(anchor='w', padx=8, pady=(4, 0))

        cb_row = tk.Frame(c_cb, bg=SURFACE)
        cb_row.pack(fill='x', padx=8, pady=(2, 2))
        tk.Label(cb_row, text='Min minutes:', bg=SURFACE, fg=FG,
                 font=FONT_UI).pack(side='left')
        self.clickback_min_var = tk.StringVar(
            value=str(self.config.get('clickback_min_min', 5)))
        tk.Spinbox(cb_row, from_=1, to=120, width=5,
                   textvariable=self.clickback_min_var,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(4, 10))
        tk.Label(cb_row, text='Max minutes:', bg=SURFACE, fg=FG,
                 font=FONT_UI).pack(side='left')
        self.clickback_max_var = tk.StringVar(
            value=str(self.config.get('clickback_max_min', 15)))
        tk.Spinbox(cb_row, from_=1, to=120, width=5,
                   textvariable=self.clickback_max_var,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(4, 0))

        tk.Label(c_cb, text='Range you set is jittered down internally so it never fires '
                            'on the round number — e.g. 5 min → 4:00–4:30, 15 min → 14:00–14:30.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=380, justify='left').pack(anchor='w', padx=8, pady=(0, 4))

        # Click A (clickback spot) and Click B (mining tile) capture
        ab_row = tk.Frame(c_cb, bg=SURFACE)
        ab_row.pack(fill='x', padx=8, pady=(2, 4))
        a = self.config.get('clickback_a')
        b = self.config.get('clickback_b')
        self._cb_a_label = tk.Label(ab_row,
                                    text=f"A: {a[0]},{a[1]}" if a else 'A: not set',
                                    bg=SURFACE, fg=FG, font=FONT_UI)
        self._cb_a_label.pack(side='left', padx=(0, 4))
        ttk.Button(ab_row, text='Set Click A',
                   command=lambda: self._capture_screen_click(self._save_clickback_a),
                   style='Util.TButton').pack(side='left', padx=(0, 12))
        self._cb_b_label = tk.Label(ab_row,
                                    text=f"B: {b[0]},{b[1]}" if b else 'B: not set',
                                    bg=SURFACE, fg=FG, font=FONT_UI)
        self._cb_b_label.pack(side='left', padx=(0, 4))
        ttk.Button(ab_row, text='Set Click B',
                   command=lambda: self._capture_screen_click(self._save_clickback_b),
                   style='Util.TButton').pack(side='left')

        tk.Label(c_cb, text='A = clickback spot (somewhere safe). B = mining tile to return to. '
                            'On each fire: click A, brief pause, click B.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=380, justify='left').pack(anchor='w', padx=8, pady=(0, 6))

        def _save_clickback(*_):
            for k, v in (('clickback_min_min', self.clickback_min_var),
                         ('clickback_max_min', self.clickback_max_var)):
                try:
                    self.config[k] = int(v.get())
                except (ValueError, tk.TclError):
                    pass
        self.clickback_min_var.trace_add('write', _save_clickback)
        self.clickback_max_var.trace_add('write', _save_clickback)

        # ── WalkTo Command ────────────────────────────────────────────────────
        co, c = card(body, padx=0, pady=6)
        co.pack(fill='x', padx=8, pady=(6, 6))
        section_label(c, 'WalkTo Command  [Experimental]')

        tk.Label(c, text='After X–X ore clicks, automatically types  ::walkto <destination>  in chat.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=380, justify='left').pack(anchor='w', padx=8, pady=(0, 6))

        # Enable toggle
        self.walkto_enabled_var = tk.BooleanVar(value=self.config.get('walkto_enabled', False))
        toggle_row(c, 'Enable WalkTo after clicks', self.walkto_enabled_var).pack(
            anchor='w', padx=8, pady=(0, 6))

        def _on_walkto_toggle(*_):
            if self.walkto_enabled_var.get():
                self.powermine_var.set(False)
                self._powermine_toggle.set_disabled(True)
            else:
                self._powermine_toggle.set_disabled(False)
        self.walkto_enabled_var.trace_add('write', _on_walkto_toggle)
        _on_walkto_toggle()  # apply initial state

        # Click range row
        range_row = tk.Frame(c, bg=SURFACE)
        range_row.pack(fill='x', padx=8, pady=(0, 6))
        tk.Label(range_row, text='Clicks between walkto:', bg=SURFACE, fg=FG,
                 font=FONT_UI).pack(side='left')

        self.walkto_min_var = tk.StringVar(value=str(self.config.get('walkto_min_clicks', 35)))
        self.walkto_max_var = tk.StringVar(value=str(self.config.get('walkto_max_clicks', 50)))

        tk.Label(range_row, text='  Min', bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left')
        tk.Spinbox(range_row, from_=1, to=999, width=5, textvariable=self.walkto_min_var,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(2, 8))

        tk.Label(range_row, text='Max', bg=SURFACE, fg=MUTED, font=FONT_UI).pack(side='left')
        tk.Spinbox(range_row, from_=1, to=999, width=5, textvariable=self.walkto_max_var,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(2, 0))

        # High-bank-click warning: >45 clicks before banking is risky on low mining levels.
        self._walkto_warned = False
        def _walkto_max_warn(*_):
            try:
                v = int(self.walkto_max_var.get())
            except (ValueError, tk.TclError):
                return
            if v > 45 and not self._walkto_warned:
                self._walkto_warned = True
                messagebox.showwarning(
                    'High click count',
                    f'Walkto max set to {v}. If your mining level is below ~40, '
                    'clicking 45+ times before banking can fill inventory and trigger logout.')
            elif v <= 45:
                self._walkto_warned = False
        self.walkto_max_var.trace_add('write', _walkto_max_warn)

        # Two side-by-side comboboxes per slot:
        #   left  = short location name (Varrock East, Falador West, ...)
        #   right = full ::walkto string (Bank (Varrock East), ...)
        # Bot picks randomly from all non-blank entries — always RNG, no toggle.
        BANK_SHORT_PRESETS = [
            'None', 'Varrock East', 'Varrock West', 'Falador East', 'Falador West',
            'Edgeville', 'Draynor', 'Al Kharid', 'Catherby', 'Seers',
            'Ardougne North', 'Ardougne South',
        ]
        BANK_FULL_PRESETS = [
            'None', 'Bank (Varrock East)', 'Bank (Varrock West)',
            'Bank (Falador East)', 'Bank (Falador West)',
            'Bank (Edgeville)', 'Bank (Draynor)', 'Bank (Al Kharid)',
            'Bank (Catherby)', 'Bank (Seers)',
            'Bank (Ardougne North)', 'Bank (Ardougne South)',
        ]
        TRAIN_SHORT_PRESETS = [
            'None', 'Varrock East Mine', 'Varrock West Mine', 'Mining Guild',
            'Falador Mining Site', 'Dwarven Mine', 'Al Kharid Mine',
            'Lumbridge Swamp Mine', 'Rimmington Mine',
        ]
        TRAIN_FULL_PRESETS = [
            'None', 'Mine (Varrock East)', 'Mine (Varrock West)', 'Mine (Mining Guild)',
            'Mine (Falador)', 'Mine (Dwarven)', 'Mine (Al Kharid)',
            'Mine (Lumbridge Swamp)', 'Mine (Rimmington)',
        ]

        # Grid container so headers + inputs align in clean columns.
        grid = tk.Frame(c, bg=SURFACE)
        grid.pack(fill='x', padx=4, pady=(4, 2))
        # Column widths (in chars): label, short, &, full, user, xy
        COL_W = {'lbl': 6, 'a': 13, 'amp': 1, 'b': 18, 'user': 11, 'xy': 7}

        # Header row — placed via grid so each header sits over its input.
        tk.Label(grid, text='', bg=SURFACE, width=COL_W['lbl']).grid(row=0, column=0)
        tk.Label(grid, text='Short name', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold'), width=COL_W['a'], anchor='w'
                 ).grid(row=0, column=1, padx=(2, 4), sticky='w')
        tk.Label(grid, text='', bg=SURFACE, width=COL_W['amp']).grid(row=0, column=2)
        tk.Label(grid, text='Full name', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold'), width=COL_W['b'], anchor='w'
                 ).grid(row=0, column=3, padx=(0, 4), sticky='w')
        tk.Label(grid, text='User Set', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold'), width=COL_W['user'], anchor='w'
                 ).grid(row=0, column=4, padx=(0, 4), sticky='w')
        tk.Label(grid, text='X,Y', bg=SURFACE, fg=MUTED,
                 font=(FONT_UI[0], 7, 'bold'), width=COL_W['xy'], anchor='w'
                 ).grid(row=0, column=5, sticky='w')

        def _dest_row(grid_row, slot_label, key_a, key_b, key_user, key_xy,
                      default_a, default_b, presets_a, presets_b):
            tk.Label(grid, text=slot_label, bg=SURFACE, fg=ACCENT,
                     font=('Consolas', 9, 'bold'), width=COL_W['lbl'], anchor='w'
                     ).grid(row=grid_row, column=0, sticky='w')
            var_a = tk.StringVar(value=self.config.get(key_a, default_a))
            var_b = tk.StringVar(value=self.config.get(key_b, default_b))
            var_user = tk.StringVar(value=self.config.get(key_user, ''))
            var_xy = tk.StringVar(value=self.config.get(key_xy, ''))
            cb_a = ttk.Combobox(grid, textvariable=var_a, values=presets_a,
                                state='normal', width=COL_W['a'])
            cb_a.grid(row=grid_row, column=1, padx=(2, 4), sticky='w')
            cb_a.bind('<MouseWheel>', lambda e: 'break')
            tk.Label(grid, text='&', bg=SURFACE, fg=MUTED,
                     font=FONT_UI, width=COL_W['amp']).grid(row=grid_row, column=2)
            cb_b = ttk.Combobox(grid, textvariable=var_b, values=presets_b,
                                state='normal', width=COL_W['b'])
            cb_b.grid(row=grid_row, column=3, padx=(0, 4), sticky='w')
            cb_b.bind('<MouseWheel>', lambda e: 'break')
            ent_user = tk.Entry(grid, textvariable=var_user, bg=BORDER, fg=FG,
                                insertbackground=FG, relief='flat',
                                font=('Consolas', 9), width=COL_W['user'])
            ent_user.grid(row=grid_row, column=4, padx=(0, 4), sticky='w')
            ent_xy = tk.Entry(grid, textvariable=var_xy, bg=BORDER, fg=FG,
                              insertbackground=FG, relief='flat',
                              font=('Consolas', 9), width=COL_W['xy'])
            ent_xy.grid(row=grid_row, column=5, sticky='w')
            def _save(*_):
                self.config[key_a] = var_a.get()
                self.config[key_b] = var_b.get()
                self.config[key_user] = var_user.get()
                self.config[key_xy] = var_xy.get()
            for v in (var_a, var_b, var_user, var_xy):
                v.trace_add('write', _save)
            return var_a, var_b, var_user, var_xy

        tk.Label(c, text='Destinations (::walkto). Bot picks randomly from all non-blank '
                         'entries each cycle. Blank = ignored.',
                 bg=SURFACE, fg=FG, font=FONT_UI,
                 wraplength=420, justify='left').pack(anchor='w', padx=8, pady=(4, 2))

        (self.walkto_dest1_a_var, self.walkto_dest1_b_var,
         self.walkto_dest1_user_var, self.walkto_dest1_xy_var) = _dest_row(
            1, 'Bank',
            'walkto_dest1_a', 'walkto_dest1_b', 'walkto_dest1_user', 'walkto_dest1_xy',
            'Varrock East', 'Bank (Varrock East)',
            BANK_SHORT_PRESETS, BANK_FULL_PRESETS)
        (self.walkto_train1_a_var, self.walkto_train1_b_var,
         self.walkto_train1_user_var, self.walkto_train1_xy_var) = _dest_row(
            2, 'Train',
            'walkto_train1_a', 'walkto_train1_b', 'walkto_train1_user', 'walkto_train1_xy',
            'None', 'None',
            TRAIN_SHORT_PRESETS, TRAIN_FULL_PRESETS)

        tk.Label(c, text='Note: randomizes between all non-blank entries (Short, Full, User Set, X,Y) '
                         '— at random typing speed. "User Set" = your own walkto string captured '
                         'in-game. X,Y example: "1024 1003".',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=440, justify='left').pack(anchor='w', padx=8, pady=(2, 4))

        tk.Label(c, text='Tip: also accepts custom strings or coords (e.g. "1024 1003" '
                         '→ ::walkto 1024 1003).',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 7, 'italic'),
                 wraplength=420, justify='left').pack(anchor='w', padx=8, pady=(0, 4))

        # Live counter: clicks-until-walkto (updated by _schedule_live_update).
        self._walkto_status_label = tk.Label(c, text='Clicks until walkto: —',
                                             bg=SURFACE, fg=ACCENT,
                                             font=('Consolas', 9, 'bold'))
        self._walkto_status_label.pack(anchor='w', padx=8, pady=(2, 4))

        # Beep after ::walkto sent — toggle + delay.
        beep_row = tk.Frame(c, bg=SURFACE)
        beep_row.pack(fill='x', padx=8, pady=(2, 2))
        self.walkto_beep1_enabled_var = tk.BooleanVar(
            value=bool(self.config.get('walkto_beep1_enabled', True)))
        tk.Checkbutton(beep_row, text='Beep after ::walkto',
                       variable=self.walkto_beep1_enabled_var,
                       bg=SURFACE, fg=FG, selectcolor=BORDER,
                       activebackground=SURFACE, activeforeground=FG,
                       font=FONT_UI).pack(side='left')
        tk.Label(beep_row, text='delay (sec):', bg=SURFACE, fg=MUTED,
                 font=FONT_UI).pack(side='left', padx=(8, 2))
        self.walkto_beep1_var = tk.StringVar(
            value=str(self.config.get('walkto_beep1_secs', 40)))
        tk.Spinbox(beep_row, from_=1, to=600, width=5,
                   textvariable=self.walkto_beep1_var,
                   bg=SURFACE, fg=FG, buttonbackground=BORDER, relief='flat',
                   font=FONT_UI).pack(side='left', padx=(2, 4))

        tk.Label(c, text='Tip: Varrock East mine → Varrock East bank ≈ 37s, so set delay around 40.',
                 bg=SURFACE, fg=MUTED, font=(FONT_UI[0], 8, 'italic'),
                 wraplength=380, justify='left').pack(anchor='w', padx=8, pady=(0, 4))

        def _save_beep_delays(*_):
            try:
                self.config['walkto_beep1_secs'] = int(self.walkto_beep1_var.get())
            except (ValueError, tk.TclError):
                pass
            self.config['walkto_beep1_enabled'] = bool(self.walkto_beep1_enabled_var.get())
        self.walkto_beep1_var.trace_add('write', _save_beep_delays)
        self.walkto_beep1_enabled_var.trace_add('write', _save_beep_delays)


        # Save button
        ttk.Button(c, text='Save', command=self.save_config,
                   style='Util.TButton').pack(anchor='e', padx=8, pady=(0, 6))

        # ── Hotkeys ──────────────────────────────────────────────────────────
        co_hk, c_hk = card(body, padx=0, pady=6)
        co_hk.pack(fill='x', pady=(0, 6))
        section_label(c_hk, 'Hotkeys  [Master Bot Only]')
        hk_rows = [
            ('F6', 'Start / Stop bot'),
            ('F5', 'Go to Bank now  (bot must be running; uses Bank destination above)'),
            ('F4', 'Walk to Train area  (starts bot if stopped; uses Train destination above)'),
        ]
        for key, desc in hk_rows:
            row = tk.Frame(c_hk, bg=SURFACE)
            row.pack(fill='x', padx=8, pady=2)
            tk.Label(row, text=key, bg=BORDER, fg=ACCENT,
                     font=('Consolas', 9, 'bold'), width=4, relief='flat',
                     padx=4).pack(side='left', padx=(0, 8))
            tk.Label(row, text=desc, bg=SURFACE, fg=FG,
                     font=FONT_UI, anchor='w').pack(side='left', fill='x')

    def _apply_antiban_master_state(self):
        """Gray out / reactivate all sub-widgets under the anti-ban master toggle."""
        c = getattr(self, '_antiban_sub_frame', None)
        if c is None:
            return
        enabled = bool(self.antiban_master_var.get())
        state = 'normal' if enabled else 'disabled'
        children = c.winfo_children()
        skip = getattr(self, '_antiban_master_anchor_count', 0)
        def _walk(widget):
            try:
                cls = widget.winfo_class()
                if cls in ('TCheckbutton', 'Checkbutton', 'TEntry', 'Entry',
                           'TScale', 'Scale', 'TRadiobutton', 'Radiobutton',
                           'TCombobox', 'TButton', 'Button'):
                    widget.configure(state=state)
            except Exception:
                pass
            for ch in widget.winfo_children():
                _walk(ch)
        for w in children[skip:]:
            _walk(w)

    # ── Speed / antiban interlock ────────────────────────────────────────────

    def _on_speed_change(self):
        """When Fast is selected, force-disable mouse-outside-window. Lazy re-enables it."""
        if self.mining_speed_var.get() == 'fast':
            self.mouse_outside_var.set(False)
            if hasattr(self, '_mouse_outside_toggle'):
                self._mouse_outside_toggle.set_disabled(True)
        else:
            if hasattr(self, '_mouse_outside_toggle'):
                self._mouse_outside_toggle.set_disabled(False)

    def _on_mouse_outside_change(self):
        """When mouse-outside is toggled on, force Lazy mode."""
        if self.mouse_outside_var.get():
            self.mining_speed_var.set('lazy')

    def _on_hover_mode_change(self, *_):
        """Hover Mode interlocks: disable mouse-outside and lazy-idle when enabled.
        Writes directly to the shared config so a running bot picks it up instantly."""
        enabled = bool(self.hover_mode_var.get())
        self.config['hover_mode_enabled'] = enabled
        if enabled:
            if hasattr(self, 'mouse_outside_var'):
                self.mouse_outside_var.set(False)
            if hasattr(self, 'lazy_idle_pause_var'):
                self.lazy_idle_pause_var.set(False)
            self.config['mouse_outside_window'] = False
            self.config['lazy_idle_pause_enabled'] = False
        try:
            self.save_config()
        except Exception:
            pass

    def _on_clickback_change(self, *_):
        """Clickback cannot coexist with camera auto-rotation (fixed spots require
        a known camera angle). When enabled, camera rotation is force-disabled."""
        if not hasattr(self, 'clickback_var'):
            return
        enabled = bool(self.clickback_var.get())
        if enabled:
            # Disable camera rotation — clickback clicks fixed coords so rotation
            # would invalidate the A/B positions.
            if hasattr(self, 'camera_rotation_var'):
                self.camera_rotation_var.set(False)
            self.config['camera_rotation_enabled'] = False
        self.config['clickback_enabled'] = enabled
        try:
            self.save_config()
        except Exception:
            pass

    def _capture_screen_click(self, on_click):
        """Open a fullscreen translucent overlay; capture one mouse click and
        pass its absolute screen coords to on_click(x, y)."""
        ov = tk.Toplevel(self.root)
        ov.attributes('-fullscreen', True)
        ov.attributes('-alpha', 0.25)
        ov.configure(bg='black', cursor='crosshair')
        ov.attributes('-topmost', True)
        tk.Label(ov, text='Click anywhere to set spot — Esc to cancel',
                 bg='black', fg='white',
                 font=('Segoe UI', 14, 'bold')).place(relx=0.5, rely=0.04, anchor='n')
        def _grab(e):
            x, y = e.x_root, e.y_root
            ov.destroy()
            try:
                on_click(x, y)
            except Exception as ex:
                self.log_debug(f'capture_click callback error: {ex}')
        ov.bind('<Button-1>', _grab)
        ov.bind('<Escape>', lambda e: ov.destroy())
        ov.focus_force()

    def _save_teleport_reactions(self, presets):
        """Persist teleport-detector settings (toggle, threshold, enabled presets,
        custom phrases, random-pick toggle) on any change."""
        try:
            sel = [presets[i] for i in self._teleport_listbox.curselection()]
        except Exception:
            sel = []
        self.config['teleport_detection_enabled'] = bool(self.teleport_detect_var.get())
        try:
            self.config['teleport_threshold'] = int(self.teleport_thresh_var.get())
        except (ValueError, tk.TclError):
            pass
        self.config['teleport_reactions_enabled'] = sel
        self.config['teleport_reactions_custom'] = self.teleport_custom_var.get()
        self.config['teleport_pick_random'] = bool(self.teleport_pick_random_var.get())
        try: self.save_config()
        except Exception: pass

    def _save_clickback_a(self, x, y):
        self.config['clickback_a'] = [int(x), int(y)]
        if hasattr(self, '_cb_a_label'):
            self._cb_a_label.config(text=f'A: {x},{y}')
        try: self.save_config()
        except Exception: pass

    def _save_clickback_b(self, x, y):
        self.config['clickback_b'] = [int(x), int(y)]
        if hasattr(self, '_cb_b_label'):
            self._cb_b_label.config(text=f'B: {x},{y}')
        try: self.save_config()
        except Exception: pass

    def _on_theme_change(self, event=None):
        """Save theme/font and restart the GUI."""
        theme = self.theme_var.get()
        if theme == 'RSC Classic':
            self.font_var.set('Courier New')
        self.config['theme'] = self.theme_var.get()
        self.config['font'] = self.font_var.get()
        self.save_config()
        self._restart = True
        self.on_closing()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def update_inventory(self, cur, total):
        try:
            pct = cur / max(total, 1)
            color = RED if pct >= 0.90 else AMBER if pct >= 0.70 else GREEN
            self.live_inventory_label.config(text=f'{cur}/{total}', fg=color)
        except Exception:
            pass

    def on_confidence_change(self, value):
        try:
            self.confidence_value_label.config(text=f'{float(value):.2f}')
        except Exception:
            pass

    def increment_obtain_count(self):
        try:
            self.obtain_count += 1
            self.log_debug(f'Ore obtained  ({self.obtain_count} total)')
        except Exception:
            pass

    def reset_obtain_count(self):
        try:
            self.obtain_count = 0
        except Exception:
            pass

    def update_live_stats(self, fatigue=None, last_click_ms=None, mouse_x=None, mouse_y=None, inventory_count=None, inventory_total=30):
        """Update live statistics display in real-time"""
        try:
            # Update runtime
            if hasattr(self, '_start_time') and self._start_time:
                elapsed = int(time.time() - self._start_time)
                hrs, rem = divmod(elapsed, 3600)
                mins, secs = divmod(rem, 60)
                if hrs > 0:
                    self.live_runtime_label.config(text=f'⏱ {hrs}:{mins:02d}:{secs:02d}')
                else:
                    self.live_runtime_label.config(text=f'⏱ {mins:02d}:{secs:02d}')

            # Update fatigue — color ramps green→amber→red as fatigue climbs
            if fatigue is not None:
                color = RED if fatigue >= 85 else AMBER if fatigue >= 60 else GREEN if fatigue >= 30 else MUTED
                self.live_fatigue_label.config(text=f'{int(fatigue)}%', fg=color)

            # Update inventory count (X/total)
            if inventory_count is not None:
                self.update_inventory(int(inventory_count), int(inventory_total))

            # Merge mouse coords + last-click age into the single top-bar label
            coord_part = f'🖱 {int(mouse_x)}, {int(mouse_y)}' if (mouse_x is not None and mouse_y is not None) else '🖱 ----, ----'
            if last_click_ms is None or last_click_ms == 0:
                click_part = '----ms'
            else:
                elapsed_ms = int(time.time() * 1000 - last_click_ms)
                click_part = f'{elapsed_ms}ms'
            self.mouse_coord_label.config(text=f'{coord_part}   {click_part}')
        
        except Exception as e:
            print(f"[GUI] Error updating live stats: {e}")

    def log_debug(self, msg):
        try:
            self.debug_text.config(state='normal')
            self.debug_text.insert('end', f'{time.strftime("%H:%M:%S")}  {msg}\n')
            # Keep only the last 10 lines
            lines = int(self.debug_text.index('end-1c').split('.')[0])
            if lines > 10:
                self.debug_text.delete('1.0', f'{lines - 10}.0')
            self.debug_text.see('end')
            self.debug_text.config(state='disabled')
        except Exception:
            pass
    def on_window_selected(self, event=None):
        self._update_win_info_label()
        self.flash_window(times=3)

    def _update_win_info_label(self):
        if not hasattr(self, '_win_info_label'):
            return
        display = self.window_var.get()
        info = self._window_info_map.get(display)
        if info:
            text = (f'PID {info["pid"]}   '
                    f'Position: {info["pos"]}   '
                    f'Size: {info["size"]}')
        else:
            text = display
        self._win_info_label.config(text=text)

    def refresh_windows(self):
        java_windows = self.get_java_windows()
        if hasattr(self, '_window_combo'):
            self._window_combo['values'] = java_windows
            if java_windows:
                self._window_combo.set(java_windows[0])
        self._update_win_info_label()
        self.log_debug(f'Refreshed: {len(java_windows)} Java window(s) found')

    def _bring_selected_to_front(self):
        """Bring the currently selected game window to the foreground."""
        title = self._title_from_display(self.window_var.get())
        if not title:
            return
        try:
            hwnd = win32gui.FindWindow(None, title)
            if not hwnd:
                return
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            except Exception:
                pass
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        except Exception as e:
            self.log_debug(f'Bring-to-front failed: {e}')

    def flash_window(self, times=3):
        title = self._title_from_display(self.window_var.get())
        def _flash():
            hwnd_list = []
            win32gui.EnumWindows(
                lambda h, _: hwnd_list.append(h) or True
                if title.lower() in win32gui.GetWindowText(h).lower() else True,
                None)
            for hwnd in hwnd_list:
                for _ in range(times):
                    try:
                        win32gui.FlashWindow(hwnd, True); time.sleep(0.18)
                        win32gui.FlashWindow(hwnd, False); time.sleep(0.18)
                    except Exception:
                        pass
        threading.Thread(target=_flash, daemon=True).start()

    def _popup_window_selector(self):
        """Open a standalone Toplevel listing all detected Java windows with live info."""
        java_windows = self.get_java_windows()
        dlg = tk.Toplevel(self.root)
        dlg.title('Select Game Window')
        dlg.geometry('560x340')
        dlg.configure(bg=BG)
        dlg.grab_set()

        tk.Label(dlg, text='Detected Java Windows', bg=BG, fg=ACCENT,
                 font=(FONT_UI[0], 10, 'bold')).pack(pady=(10, 4))

        cols = ('Title', 'PID', 'Position', 'Size')
        tree = ttk.Treeview(dlg, columns=cols, show='headings', height=10)
        for col, w in zip(cols, (220, 70, 100, 90)):
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor='w')

        for d in java_windows:
            info = self._window_info_map.get(d, {})
            tree.insert('', 'end', iid=d, values=(
                info.get('title', d),
                info.get('pid', '?'),
                info.get('pos', '?'),
                info.get('size', '?'),
            ))
        tree.pack(fill='both', expand=True, padx=8, pady=4)

        def _select():
            sel = tree.selection()
            if not sel:
                return
            self.window_var.set(sel[0])
            if hasattr(self, '_window_combo'):
                self._window_combo.set(sel[0])
            self._update_win_info_label()
            self.flash_window(times=3)
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=6)
        ttk.Button(btn_row, text='Select', command=_select,
                   style='Start.TButton').pack(side='left', padx=6)
        ttk.Button(btn_row, text='Cancel', command=dlg.destroy,
                   style='Util.TButton').pack(side='left', padx=6)
        tree.bind('<Double-1>', lambda _: _select())

    def _apply_brightness(self):
        """Overlay a click-through tint on just the game window.
        <100% = darken (black tint), >100% = brighten (white tint), 100% = off."""
        import win32con
        title = self._title_from_display(self.window_var.get())
        pct   = self._brightness_var.get()   # 50-200
        self.config['window_brightness'] = pct

        hwnd = win32gui.FindWindow(None, title)
        if not hwnd:
            self.log_debug(f'Brightness: window "{title}" not found')
            return

        # Tear down any existing tint
        tint = getattr(self, '_brightness_tint', None)
        if tint is not None:
            try: tint.destroy()
            except Exception: pass
            self._brightness_tint = None
        if hasattr(self, '_brightness_job') and self._brightness_job:
            try: self.root.after_cancel(self._brightness_job)
            except Exception: pass
            self._brightness_job = None

        if pct == 100:
            self.log_debug('Brightness: tint cleared (100%)')
            return

        if pct >= 100:
            color = '#FFFFFF'
            alpha = min(0.55, (pct - 100) / 100.0 * 0.55)
        else:
            color = '#000000'
            alpha = min(0.55, (100 - pct) / 50.0 * 0.55)

        tint = tk.Toplevel(self.root)
        tint.overrideredirect(True)
        tint.configure(bg=color)
        tint.attributes('-topmost', True)
        tint.attributes('-alpha', alpha)
        self._brightness_tint = tint

        def reposition():
            try:
                if not win32gui.IsWindow(hwnd):
                    return
                rect = win32gui.GetClientRect(hwnd)
                pt = win32gui.ClientToScreen(hwnd, (0, 0))
                tint.geometry(f'{rect[2]}x{rect[3]}+{pt[0]}+{pt[1]}')
                # Make click-through via WS_EX_LAYERED | WS_EX_TRANSPARENT
                thwnd = int(tint.frame(), 16) if False else win32gui.FindWindow(None, tint.title())
                thwnd = tint.winfo_id()
                # Get the toplevel HWND
                parent = ctypes.windll.user32.GetParent(thwnd)
                while parent:
                    thwnd = parent
                    parent = ctypes.windll.user32.GetParent(thwnd)
                ex = win32gui.GetWindowLong(thwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(thwnd, win32con.GWL_EXSTYLE,
                                       ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW)
            except Exception as e:
                self.log_debug(f'Brightness reposition err: {e}')
            self._brightness_job = self.root.after(250, reposition)

        import ctypes
        reposition()
        self.log_debug(f'Brightness tint {pct}% ({color} a={alpha:.2f}) on "{title}"')

    def start_bot(self):
        if self.running:
            return
        # Persist whatever is currently shown in the Clients tab before reading it.
        try:
            self._save_clients_config()
        except Exception:
            pass
        self.save_config()
        if not any(v.get() for v in self.checkbox_vars.values()):
            messagebox.showwarning('Warning', 'No ores selected!')
            return
        if not self.main_model_var.get():
            messagebox.showwarning('Warning', 'At least one model must be enabled!')
            return
        self.running = True
        self._start_time = time.time()
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.status_dot.config(text='● RUNNING', fg=GREEN)
        self.reset_obtain_count()
        self.update_inventory(0, 30)
        self.click_count = 0
        try: self.click_count_label.config(text='⛏ 0')
        except Exception: pass
        seed = self.config.get('mouse_settings', {}).get('mouse_seed', 'auto')
        self.log_debug(f'Bot starting... (mouse seed: {seed})')

        # Multi-client: collect any enabled extra clients from Clients tab.
        clients_cfg = self.config.get('clients', [])
        # Skip slaves whose task isn't Mining for now — WIP modes warn instead.
        extra_clients = []
        for slot in clients_cfg[1:]:
            if not (slot.get('enabled') and slot.get('window_title')):
                continue
            task = slot.get('task', 'Mining')
            if not task.startswith('Mining'):
                self.log_debug(f'⚠ Bot with task "{task}" skipped — only Mining is wired.')
                continue
            extra_clients.append(slot)

        # Interlock: when 2+ bots are active, force-disable single-client-only modes.
        if extra_clients:
            self.config['hover_mode_enabled'] = False
            self.config['powermine_enabled'] = False
            self.config['mouse_outside_window'] = False
            if hasattr(self, 'hover_mode_var'): self.hover_mode_var.set(False)
            if hasattr(self, 'mouse_outside_var'): self.mouse_outside_var.set(False)
            mc_on = self.config.get('multi_client_mode', False)
            self.log_debug(f'Multi-bot active ({1 + len(extra_clients)} bots) — '
                           f'hover/powermine/park-outside disabled. '
                           f'Multi-Client mode: {"ON" if mc_on else "OFF (legacy turn-gate)"}')

        # Resolve hwnds from _window_info_map NOW (before tagging renames the windows).
        # find_window() in bot.py searches by title — but after _tag_window_by_title()
        # renames windows (e.g. "RSCRevolution2" → "RSCRevolution2 — Bot"), a
        # title-based search would fail or return the wrong hwnd.
        master_display = getattr(self, 'window_var', None)
        master_display = master_display.get() if master_display else ''
        master_hwnd = self._window_info_map.get(master_display, {}).get('hwnd')
        # Build window_title → hwnd from in-memory _clients_config which holds
        # _win_display (set on combobox selection).  This key is NOT persisted to
        # config.json, so we can't read it from extra_clients (which comes from
        # self.config['clients']).
        _title_to_hwnd = {}
        for _cs in self._clients_config:
            _disp = _cs.get('_win_display', '')
            _hwnd = self._window_info_map.get(_disp, {}).get('hwnd')
            _wt = _cs.get('window_title', '')
            if _hwnd and _wt:
                _title_to_hwnd[_wt] = _hwnd

        # Window tagging: rename each game window so "— Bot / — Bot2" shows in Alt-Tab.
        self._window_title_originals = {}
        master_title = self.config.get('window_title', '')
        if master_title:
            self._tag_window_by_title(master_title, 'Bot')
        for i, ec in enumerate(extra_clients, start=2):
            self._tag_window_by_title(ec['window_title'], f'Bot{i}')

        self.bot = MiningBot(self.config, self, client_id=0, hwnd=master_hwnd)
        self.bots = [self.bot]
        for i, ec in enumerate(extra_clients, start=1):
            sub_cfg = dict(self.config)
            sub_cfg['window_title'] = ec['window_title']
            if 'ore_checkboxes' in ec:
                # Slave tab now uses same YOLO class names as master — copy directly.
                sub_cfg['ore_checkboxes'] = dict(ec['ore_checkboxes'])
            # Per-client speed / powermine override (falls back to master if not set)
            if 'speed_mode' in ec:
                sub_cfg['speed_mode'] = ec['speed_mode']
                sub_cfg['fast_mining_enabled'] = (ec['speed_mode'] == 'fast')
            if 'powermine_enabled' in ec:
                sub_cfg['powermine_enabled'] = ec['powermine_enabled']
            # Per-client walkto override
            for k in ('walkto_enabled', 'walkto_min_clicks', 'walkto_max_clicks',
                      'walkto_dest_a', 'walkto_dest_b',
                      'walkto_dest_user', 'walkto_dest_xy',
                      'fixed_ore_spots'):
                if k in ec:
                    if k == 'walkto_dest_a':
                        sub_cfg['walkto_dest1_a'] = ec[k]
                    elif k == 'walkto_dest_b':
                        sub_cfg['walkto_dest1_b'] = ec[k]
                    elif k == 'walkto_dest_user':
                        sub_cfg['walkto_dest1_user'] = ec[k]
                    elif k == 'walkto_dest_xy':
                        sub_cfg['walkto_dest1_xy'] = ec[k]
                    else:
                        sub_cfg[k] = ec[k]
            ec_hwnd = _title_to_hwnd.get(ec.get('window_title', ''))
            self.bots.append(MiningBot(sub_cfg, self, client_id=i,
                                       window_title=ec['window_title'],
                                       hwnd=ec_hwnd))
        # Auto-login pass before the mining loop starts. This MUST complete
        # before the mining thread starts, otherwise camera-rotation arrow
        # keys land in the password field and clear it.
        if self.config.get('autologin_enabled', False):
            self.log_debug('Auto-login: running OCR login sequence...')
            try:
                import autologin, win32gui
                title = self.config.get('window_title', '')
                hwnd = win32gui.FindWindow(None, title) if title else 0
                if hwnd:
                    rect = win32gui.GetWindowRect(hwnd)
                    ok = autologin.ensure_logged_in(rect, hwnd, instant=False, timeout=60.0)
                    self.log_debug('Auto-login: logged in' if ok else 'Auto-login: timed out (still on login screen)')
                    if not ok:
                        self.running = False
                        self.btn_start.config(state='normal')
                        self.btn_stop.config(state='disabled')
                        self.status_dot.config(text='● STOPPED — login failed', fg=RED)
                        return
                else:
                    self.log_debug(f'Auto-login: window "{title}" not found')
            except Exception as e:
                self.log_debug(f'Auto-login error: {e}')
        # Multi-client mode: master's loop handles all windows; slaves only run detection.
        if self.config.get('multi_client_mode', False) and len(self.bots) > 1:
            self.bot._peer_bots = list(self.bots[1:])
            for sub in self.bots[1:]:
                sub._background_only = True
            # Disable the old turn-gate (not needed in multi-client mode)
            MiningBot._ACTIVE_CLIENT_IDS = []
            MiningBot._TURN_IDX[0] = 0
            MiningBot._TURN_SINCE[0] = time.time()
            for b in self.bots:
                print(f'[MC] Bot{b.client_id+1} hwnd={b.hwnd} title={b.config.get("window_title","?")}')
            self.log_debug(f'Multi-Client mode ON — master cycles {len(self.bots)} windows')
        else:
            # Initialise round-robin turn state BEFORE threads start so the gate
            # in bot.py sees the correct list from the very first iteration.
            MiningBot._ACTIVE_CLIENT_IDS = [b.client_id for b in self.bots]
            MiningBot._TURN_IDX[0] = 0
            MiningBot._TURN_SINCE[0] = time.time()
            self.log_debug(f'Turn order: {MiningBot._ACTIVE_CLIENT_IDS}')

        self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self.bot_thread.start()
        # Launch secondary bot threads.
        self._extra_threads = []
        for sub in self.bots[1:]:
            bot_name = f'Bot{sub.client_id + 1}'
            t = threading.Thread(target=lambda b=sub: self._run_extra_bot(b),
                                 daemon=True, name=f'bot-{sub.client_id}')
            t.start()
            self._extra_threads.append(t)
            self.log_debug(f'{bot_name} thread started → window: {sub.config.get("window_title", "?")}')
        self._schedule_live_update()
        self.root.update_idletasks()
        self.root.minsize(660, 680)
        self.root.geometry('660x680')
        self._start_overlay()
        self.root.geometry('660x680')
        # Guard: re-apply geometry for 2s after start.
        # The 50ms live-update loop changes label text continuously, each of which
        # can trigger a tkinter layout recalc and silently override geometry.
        # A <Configure> guard on the root window catches ALL causes of resize
        # during startup without needing to guess a fixed timeout.
        import time as _time
        _guard_until = _time.time() + 2.0
        def _geom_guard(e=None):
            if e is not None and getattr(e, 'widget', None) is not self.root:
                return
            if _time.time() < _guard_until:
                self.root.geometry('660x680')
        self.root.bind('<Configure>', _geom_guard)
        self.root.after(2100, lambda: self.root.unbind('<Configure>'))

    def _schedule_live_update(self):
        """Periodically update live statistics from bot - very fast 50ms updates"""
        if self.running and self.bot:
            # Live walkto-counter in Experimental tab + top bar.
            try:
                nxt = getattr(self.bot, '_walkto_next_at', None)
                cur = getattr(self.bot, '_mine_count', 0)
                wt_enabled = self.config.get('walkto_enabled', False)
                lbl = getattr(self, '_walkto_status_label', None)
                bar_lbl = getattr(self, '_walkto_bar_label', None)
                if nxt is not None and wt_enabled:
                    remaining = max(0, nxt - cur)
                    if lbl is not None:
                        lbl.config(text=f'Clicks until walkto: {remaining}  (at {nxt}, current {cur})')
                    if bar_lbl is not None:
                        bar_lbl.config(text=f'🚶 {remaining}')
                else:
                    if lbl is not None:
                        lbl.config(text='Clicks until walkto: — (walkto disabled)')
                    if bar_lbl is not None:
                        bar_lbl.config(text='')
            except Exception:
                pass
            try:
                self.update_live_stats(
                    fatigue=self.bot.current_fatigue,
                    last_click_ms=self.bot.last_click_time,
                    mouse_x=self.bot.mouse_x,
                    mouse_y=self.bot.mouse_y,
                    # Inventory is intentionally omitted here — it is updated
                    # exclusively by the OCR callback in bot.py so the display
                    # only ever reflects the real #/30 read from the game.
                )
                # Clicked-rocks counter in top bar
                n = int(getattr(self.bot, '_mine_count', 0))
                if n != self.click_count:
                    self.click_count = n
                    self.click_count_label.config(text=f'⛏ {n}')
                # Break countdown
                be = getattr(self.bot, 'break_end_time', 0) or 0
                remaining = int(be - time.time())
                if remaining > 0:
                    mm, ss = divmod(remaining, 60)
                    self.break_countdown_label.config(text=f'☕ BREAK {mm:02d}:{ss:02d}')
                else:
                    if self.break_countdown_label.cget('text'):
                        self.break_countdown_label.config(text='')
            except Exception as e:
                pass
            self.root.after(50, self._schedule_live_update)  # Update every 50ms for smooth mouse tracking

    # ── Fixed Spot Selector ──────────────────────────────────────────────────

    def _spot_btn_text(self):
        n = len(self._fixed_spots)
        return f'📍 Select ore spots ({n}/3)' if n < 3 else '📍 Spots set (3/3)'

    def _clear_fixed_spots(self):
        self._fixed_spots = []
        self.spot_btn_label.set(self._spot_btn_text())
        self.config['fixed_ore_spots'] = []

    def _open_spot_selector(self):
        """Overlay a click-capture window over the game window to pick ore spots."""
        hwnd = None
        title = self.config.get('window_title', '')
        try:
            hwnd = win32gui.FindWindow(None, title)
        except Exception:
            pass
        if not hwnd:
            messagebox.showwarning('Fixed Spots', 'Game window not found — launch the game first.')
            return

        try:
            rect = win32gui.GetClientRect(hwnd)
            pt = win32gui.ClientToScreen(hwnd, (0, 0))
            gx, gy, gw, gh = pt[0], pt[1], rect[2], rect[3]
        except Exception:
            messagebox.showerror('Fixed Spots', 'Could not read game window position.')
            return

        sel = tk.Toplevel(self.root)
        sel.title('Click up to 3 ore spots — then close')
        sel.geometry(f'{gw}x{gh}+{gx}+{gy}')
        sel.attributes('-topmost', True)
        sel.attributes('-alpha', 0.35)
        sel.configure(bg='black')
        sel.overrideredirect(True)

        canvas = tk.Canvas(sel, bg='black', highlightthickness=0, cursor='crosshair')
        canvas.pack(fill='both', expand=True)

        # Instruction banner
        canvas.create_text(gw // 2, 22, text='Click up to 3 ore spots  |  Right-click to undo  |  Press Enter/Escape to confirm',
                           fill='white', font=('Consolas', 11, 'bold'))

        spots = list(self._fixed_spots)  # copy existing spots in
        markers = []

        def _redraw():
            for m in markers:
                canvas.delete(m)
            markers.clear()
            colors = ['#ff4444', '#ffaa00', '#44ddff']
            for i, (rx, ry) in enumerate(spots):
                sx, sy = int(rx * gw), int(ry * gh)
                r = 18
                m1 = canvas.create_oval(sx-r, sy-r, sx+r, sy+r,
                                        outline=colors[i], width=3, fill='')
                m2 = canvas.create_text(sx, sy, text=str(i+1),
                                        fill=colors[i], font=('Consolas', 13, 'bold'))
                markers.extend([m1, m2])

        _redraw()

        def _on_click(e):
            if len(spots) >= 3:
                return
            spots.append((e.x / gw, e.y / gh))
            _redraw()
            if len(spots) == 3:
                canvas.create_text(gw // 2, 48,
                                   text='3 spots selected — close or press Enter',
                                   fill='#44ddff', font=('Consolas', 10))

        def _on_right(e):
            if spots:
                spots.pop()
                _redraw()

        def _confirm(e=None):
            self._fixed_spots = list(spots)
            self.config['fixed_ore_spots'] = self._fixed_spots
            self.spot_btn_label.set(self._spot_btn_text())
            sel.destroy()

        canvas.bind('<Button-1>', _on_click)
        canvas.bind('<Button-3>', _on_right)
        sel.bind('<Return>', _confirm)
        sel.bind('<Escape>', _confirm)
        canvas.bind('<Double-Button-1>', _confirm)

    # ────────────────────────────────────────────────────────────────────────────

    def _run_bot(self):
        try:
            self.bot.run()
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror('Bot Error', str(e)))
            self.root.after(0, self.stop_bot)

    def _run_extra_bot(self, sub_bot):
        bot_name = f'Bot{sub_bot.client_id + 1}'
        try:
            if getattr(sub_bot, '_background_only', False):
                sub_bot.start_background_only()
            else:
                sub_bot.run()
        except Exception as e:
            self.log_debug(f'[{bot_name}] stopped: {e}')

    def _tag_window_by_title(self, title, role_tag):
        """Append " — <role_tag>" to the matching game window's title bar.
        Stores original title in self._window_title_originals[hwnd] so we
        can restore on stop."""
        try:
            target = title
            hwnd_found = None
            def _enum(hwnd, _):
                nonlocal hwnd_found
                txt = win32gui.GetWindowText(hwnd)
                if txt == target:
                    hwnd_found = hwnd
                elif hwnd_found is None and target.lower() in (txt or '').lower():
                    hwnd_found = hwnd
                return True
            win32gui.EnumWindows(_enum, None)
            if hwnd_found is None:
                self.log_debug(f'Tag: window "{title}" not found')
                return
            original = win32gui.GetWindowText(hwnd_found)
            if ' — ' in original:
                # Already tagged; don't double-stack.
                return
            self._window_title_originals[hwnd_found] = original
            new_title = f'{original} — {role_tag}'
            win32gui.SetWindowText(hwnd_found, new_title)
            self.log_debug(f'Tagged hwnd {hwnd_found}: {role_tag}')
        except Exception as e:
            self.log_debug(f'Tag error: {e}')

    def _restore_window_titles(self):
        for hwnd, original in list(getattr(self, '_window_title_originals', {}).items()):
            try:
                if win32gui.IsWindow(hwnd):
                    win32gui.SetWindowText(hwnd, original)
            except Exception:
                pass
        self._window_title_originals = {}

    def stop_bot(self):
        if not self.running:
            return
        self.running = False
        # Clear turn list so any lingering bot threads exit the turn-gate loop.
        MiningBot._ACTIVE_CLIENT_IDS = []
        if self.bot:
            self.bot.stop()
        for sub in getattr(self, 'bots', [])[1:]:
            try: sub.stop()
            except Exception: pass
        # Restore any window titles we tagged during start.
        try: self._restore_window_titles()
        except Exception: pass
        self._stop_overlay()
        self._start_time = None
        self.live_runtime_label.config(text='⏱ 00:00')
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        reason = getattr(self.bot, 'stop_reason', '') if self.bot else ''
        label = f'● STOPPED — {reason}' if reason else '● STOPPED'
        self.status_dot.config(text=label, fg=RED)
        self.log_debug(f'Bot stopped. {reason}')

    def show_stop_reason(self, reason):
        try:
            self.status_dot.config(text=f'● STOPPED — {reason}', fg=RED)
        except Exception:
            pass

    # ── Tkinter-based YOLO overlay ───────────────────────────────────────────

    # BGR ore colors from detector → RGB for PIL
    _ORE_COLORS_RGB = {
        'adamantite': (255, 0, 0),
        'mithril':    (128, 0, 128),
        'coal':       (100, 100, 100),
        'iron':       (200, 200, 200),
        'tin':        (0, 255, 255),
        'copper':     (255, 165, 0),
        'empty':      (255, 255, 0),
    }
    CHROMA_KEY = (255, 0, 255)   # magenta — will be invisible in-game

    def _on_overlay_mode_change(self):
        """Rebuild overlay window when In-Game/Pop-Out radio toggles."""
        if getattr(self, 'running', False) and getattr(self, '_overlay_win', None) is not None:
            self._start_overlay()

    def _start_overlay(self):
        """Create the overlay Toplevel and start polling frames from the bot."""
        # Destroy any existing overlay before creating a new one
        self._stop_overlay()
        # Sweep: destroy ANY leftover toplevels titled 'Mining Bot Overlay'
        try:
            for child in list(self.root.winfo_children()):
                if isinstance(child, tk.Toplevel) and child.title() == 'Mining Bot Overlay':
                    try: child.destroy()
                    except Exception: pass
        except Exception:
            pass
        self._overlay_win = None
        self._overlay_label = None
        self._overlay_canvas = None
        self._overlay_canvas_item = None
        self._overlay_photo = None
        self._last_overlay_geom = None
        self._det_seen_at = {}
        # Bump generation so any in-flight poll callbacks from prior overlays exit
        self._overlay_gen = getattr(self, '_overlay_gen', 0) + 1

        mode = self.overlay_mode_var.get()
        chroma_hex = '#FF00FF'

        top = tk.Toplevel(self.root)
        top.title('Mining Bot Overlay')
        top.protocol('WM_DELETE_WINDOW', lambda: None)

        if mode == 'ingame':
            top.configure(bg=chroma_hex)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            self._overlay_canvas = tk.Canvas(top, bg=chroma_hex, highlightthickness=0)
            self._overlay_canvas.pack(fill='both', expand=True)
            self._overlay_canvas_item = None
            self._overlay_label = None
            top.update_idletasks()
            # Set WS_EX_LAYERED | TRANSPARENT | TOPMOST, then chroma-key
            try:
                # Tk wraps the toplevel in a frame — get the real HWND
                wm_frame = top.wm_frame()
                overlay_hwnd = int(wm_frame, 16) if wm_frame else 0
                if not overlay_hwnd:
                    overlay_hwnd = ctypes.windll.user32.GetParent(
                        top.winfo_id())
                if overlay_hwnd:
                    ex = win32gui.GetWindowLong(overlay_hwnd, win32con.GWL_EXSTYLE)
                    ex |= (win32con.WS_EX_LAYERED |
                           win32con.WS_EX_TRANSPARENT |
                           win32con.WS_EX_TOPMOST)
                    win32gui.SetWindowLong(overlay_hwnd, win32con.GWL_EXSTYLE, ex)
                    # LWA_COLORKEY = 0x01 — makes COLORREF magenta fully transparent
                    ctypes.windll.user32.SetLayeredWindowAttributes(
                        overlay_hwnd, 0x00FF00FF, 0, 0x01)
            except Exception:
                pass
        else:
            # Pop-Out: standalone window, NOT topmost, positioned beside the game
            top.configure(bg='black')
            top.overrideredirect(False)
            top.attributes('-topmost', False)
            # Position to the right of the game window (if found), else top-left
            try:
                if self.bot and self.bot.hwnd:
                    rect = win32gui.GetClientRect(self.bot.hwnd)
                    pt = win32gui.ClientToScreen(self.bot.hwnd, (0, 0))
                    gx, gy, gw, gh = pt[0], pt[1], rect[2], rect[3]
                    px = gx + gw + 12
                    py = gy
                    top.geometry(f'512x340+{px}+{py}')
                else:
                    top.geometry('512x340+40+40')
            except Exception:
                top.geometry('512x340+40+40')
            self._overlay_label = tk.Label(top, bg='black')
            self._overlay_label.pack(fill='both', expand=True)

        self._overlay_win = top
        self._overlay_win_gen = self._overlay_gen
        # Pop-out Toplevel steals focus from the game window; give it back
        if mode != 'ingame':
            def _refocus_game():
                if self.bot and self.bot.hwnd:
                    try:
                        self.bot.bring_window_to_front()
                    except Exception:
                        pass
            self.root.after(800, _refocus_game)
        self._poll_overlay_frame(gen=self._overlay_gen)

    def _draw_boxes_only(self, detections, width, height):
        """Render detection boxes + stats ROI box on a chroma-key background."""
        from PIL import ImageDraw, ImageFont
        img = Image.new('RGB', (width, height), self.CHROMA_KEY)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype('consola.ttf', 13)
        except Exception:
            font = ImageFont.load_default()

        # Info Panel — Hits/Prayer/Fatigue/FPS (top-left)
        draw.rectangle([0, 0, int(width * 0.22), int(height * 0.28)],
                       outline=(0, 255, 255), width=2)
        draw.text((3, 3), 'Info Panel', fill=(0, 255, 255), font=font)

        # Chat/OCR ROI — incoming game text (bottom-left)
        chat_y1 = int(height * 0.72)
        chat_y2 = int(height * 0.92)
        chat_x2 = int(width * 0.95)
        draw.rectangle([0, chat_y1, chat_x2, chat_y2],
                       outline=(255, 200, 0), width=2)
        draw.text((3, chat_y1 + 3), 'ROI', fill=(255, 200, 0), font=font)

        box_w = max(1, self.config.get('overlay_box_thickness', 2))
        _ORE_SHORT = {
            'adamantite_rock': 'Addy', 'mithril_rock': 'Mith',
            'coal_rock': 'Coal', 'iron_rock': 'Iron',
            'tin_rock': 'Tin', 'copper_rock': 'Copper', 'empty_ore_rock': 'Empty',
        }
        show_empty = self.show_empty_var.get() if hasattr(self, 'show_empty_var') else self.config.get('show_empty_ore', False)
        for det in detections:
            name = det['class_name']
            if name == 'empty_ore_rock' and not show_empty:
                continue
            x1, y1, x2, y2 = [int(v) for v in det['box']]
            conf = det['confidence']
            color = (0, 255, 0)
            for key, c in self._ORE_COLORS_RGB.items():
                if key in name:
                    color = c
                    break
            draw.rectangle([x1, y1, x2, y2], outline=color, width=box_w)
            short = _ORE_SHORT.get(name, name.replace('_rock', '').replace('_', ' ').title())
            label = f"{short} {conf:.0%}"
            draw.text((x1, max(y1 - 14, 0)), label, fill=color, font=font)
        return img

    def _poll_overlay_frame(self, gen=None):
        """Redraw overlay whenever the bot publishes a new detection frame
        (1.8s cadence) or flags an immediate refresh. Ghost polls from a
        prior overlay generation exit immediately."""
        if gen is not None and gen != getattr(self, '_overlay_gen', 0):
            return
        if not self.running or self._overlay_win is None:
            return
        refresh = False
        try:
            refresh = bool(getattr(self.bot, '_overlay_refresh_flag', False))
            if refresh:
                self.bot._overlay_refresh_flag = False
        except Exception:
            pass
        try:
            frame, region, detections, buf_ts = self.bot._overlay_buf.get()
        except Exception:
            frame, region, detections, buf_ts = None, None, [], 0.0
        last_ts = getattr(self, '_overlay_last_ts', 0.0)
        new_frame = buf_ts > last_ts
        if not (refresh or new_frame or not getattr(self, '_overlay_first_drawn', False)):
            self.root.after(200, lambda: self._poll_overlay_frame(gen=gen))
            return
        self._overlay_last_ts = buf_ts
        self._overlay_first_drawn = True
        try:
            mode = self.overlay_mode_var.get()

            if mode == 'ingame':
                if region is not None:
                    x, y, w, h = region
                    new_geom = (x, y, w, h)
                    if getattr(self, '_last_overlay_geom', None) != new_geom:
                        self._overlay_win.geometry(f'{w}x{h}+{x}+{y}')
                        self._last_overlay_geom = new_geom

                    img = self._draw_boxes_only(detections or [], w, h)
                    photo = ImageTk.PhotoImage(img)
                    if self._overlay_canvas_item is None:
                        self._overlay_canvas_item = self._overlay_canvas.create_image(
                            0, 0, anchor='nw', image=photo)
                    else:
                        self._overlay_canvas.itemconfigure(
                            self._overlay_canvas_item, image=photo)
                    self._overlay_photo = photo
            else:
                if frame is not None:
                    rgb = frame[:, :, ::-1] if frame.shape[2] == 3 else frame
                    img = Image.fromarray(rgb)
                    from PIL import ImageDraw, ImageFont
                    orig_w, orig_h = img.size
                    draw = ImageDraw.Draw(img)
                    sy2 = int(orig_h * 0.28)
                    sx2 = int(orig_w * 0.22)
                    try:
                        fnt = ImageFont.truetype('consola.ttf', 13)
                    except Exception:
                        fnt = ImageFont.load_default()
                    draw.rectangle([0, 0, sx2, sy2], outline=(0, 255, 255), width=2)
                    draw.text((3, 3), 'Info Panel', fill=(0, 255, 255), font=fnt)
                    chat_y1 = int(orig_h * 0.72)
                    chat_y2 = int(orig_h * 0.92)
                    draw.rectangle([0, chat_y1, int(orig_w * 0.95), chat_y2],
                                   outline=(255, 200, 0), width=2)
                    draw.text((3, chat_y1 + 3), 'ROI', fill=(255, 200, 0), font=fnt)
                    win_w = self._overlay_win.winfo_width()
                    win_h = self._overlay_win.winfo_height()
                    if win_w > 10 and win_h > 10:
                        img = img.resize((win_w, win_h), Image.NEAREST)
                    photo = ImageTk.PhotoImage(img)
                    self._overlay_label.configure(image=photo)
                    self._overlay_photo = photo
        except Exception:
            pass
        self.root.after(200, lambda: self._poll_overlay_frame(gen=gen))

    def _stop_overlay(self):
        """Destroy the overlay window."""
        try:
            if self._overlay_win is not None:
                self._overlay_win.destroy()
        except Exception:
            pass
        self._overlay_win = None
        self._overlay_label = None
        self._overlay_canvas = None
        self._overlay_canvas_item = None
        self._overlay_photo = None
        self._det_seen_at = {}

    def _f5_goto_bank(self):
        """F5 hotkey: immediately send ::walkto to bank while bot is running."""
        if self.bot and self.running:
            self.bot._force_goto_bank = True
            self.log_debug('F5 pressed — forcing walkto bank')

    def _f4_goto_train(self):
        """F4 hotkey: walk to training area. Starts bot first if not running."""
        if self.bot and self.running:
            self.bot._force_goto_train = True
            self.log_debug('F4 pressed — forcing walkto train area')
        elif not self.running:
            # Flag that after start we should immediately walkto train
            self._f4_pending_train = True
            self.start_bot()

    def toggle_bot(self, event=None):
        if self.running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_hotkey_listener(self):
        self._hotkey_alive = True
        def _thread():
            user32 = ctypes.windll.user32
            was_f4 = was_f5 = was_f6 = False
            VK_F4, VK_F5 = 0x73, 0x74
            self.log_debug('Global hotkey listener started (F4/F5/F6 polling)')
            while self._hotkey_alive:
                try:
                    # F6 — toggle start/stop
                    state6 = user32.GetAsyncKeyState(VK_F6)
                    if state6 & 0x8000:
                        if not was_f6:
                            was_f6 = True
                            try:
                                self.root.after(0, self.toggle_bot)
                            except Exception:
                                pass
                    else:
                        was_f6 = False

                    # F5 — go to bank now
                    state5 = user32.GetAsyncKeyState(VK_F5)
                    if state5 & 0x8000:
                        if not was_f5:
                            was_f5 = True
                            try:
                                self.root.after(0, self._f5_goto_bank)
                            except Exception:
                                pass
                    else:
                        was_f5 = False

                    # F4 — go to train area (+ start if not running)
                    state4 = user32.GetAsyncKeyState(VK_F4)
                    if state4 & 0x8000:
                        if not was_f4:
                            was_f4 = True
                            try:
                                self.root.after(0, self._f4_goto_train)
                            except Exception:
                                pass
                    else:
                        was_f4 = False

                except Exception:
                    pass
                time.sleep(0.05)  # 50ms poll – low CPU usage
        threading.Thread(target=_thread, daemon=True).start()

    def on_closing(self):
        self._hotkey_alive = False
        self.stop_bot()
        self.root.destroy()


if __name__ == '__main__':
    while True:
        _load_active_theme()
        root = tk.Tk()
        app = MiningBotGUI(root)
        root.mainloop()
        if not getattr(app, '_restart', False):
            break
