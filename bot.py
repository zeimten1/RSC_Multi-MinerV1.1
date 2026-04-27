import os
import time
import random
import math
import threading
import win32gui
import win32con
import win32api
from mss import mss
import numpy as np
from detector import Detector
from mouse import HumanMouse
from banking import BankingFSM
import cv2
import winsound
import ctypes

try:
    import easyocr
    _HAVE_OCR = True
    _ocr_reader = None
except Exception:
    _HAVE_OCR = False

try:
    import pytesseract
    import os as _os
    for _tess_path in [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]:
        if _os.path.isfile(_tess_path):
            pytesseract.pytesseract.tesseract_cmd = _tess_path
            break
    pytesseract.get_tesseract_version()   # raises if binary still missing
    _HAVE_PYTESSERACT = True
    print(f'[OCR] Tesseract ready: {pytesseract.pytesseract.tesseract_cmd}')
except Exception:
    _HAVE_PYTESSERACT = False


# Thread-safe frame buffer so the GUI can poll the latest annotated frame.
class _DetectionBuffer:
    """Thread-safe buffer holding the latest YOLO detection results."""
    def __init__(self):
        self._data = ([], None, None)  # (detections, frame, region_tuple)
        self._ts = 0.0                 # timestamp of the latest frame
        self._lock = threading.Lock()

    def update(self, detections, frame, region_tuple):
        with self._lock:
            self._data = (detections, frame, region_tuple)
            self._ts = time.time()

    def get(self):
        with self._lock:
            return self._data, self._ts


class _OverlayBuffer:
    def __init__(self):
        self._frame = None
        self._region = None
        self._detections = []
        self._ts = 0.0
        self._lock = threading.Lock()

    def update_frame(self, frame, region=None, detections=None):
        with self._lock:
            self._frame = frame
            if region is not None:
                self._region = region
            if detections is not None:
                self._detections = detections
            self._ts = time.time()

    def get(self):
        with self._lock:
            return self._frame, self._region, self._detections, self._ts


class MiningBot:
    # Shared across all instances so multi-client setups take turns on the
    # single physical mouse. Acquired around any sequence that does
    # bring-window-to-front + move + click.
    MOUSE_LOCK = threading.Lock()

    # ── Round-robin turn control ──────────────────────────────────────────────
    # Set by the GUI at start: ordered list of active client_ids.
    # Only the client whose id == _ACTIVE_CLIENT_IDS[_TURN_IDX % n] may run
    # the click / rotate path. After each click the holder advances the index.
    # _TURN_SINCE records when the current holder acquired the turn so we can
    # auto-advance if a bot is stuck (no ore found) after TURN_TIMEOUT_S secs.
    _ACTIVE_CLIENT_IDS = []   # e.g. [0, 1] for master + Bot2
    _TURN_IDX = [0]           # current position in the list
    _TURN_SINCE = [0.0]       # monotonic time when current holder got the turn
    _TURN_LOCK = threading.Lock()
    TURN_TIMEOUT_S = 10.0     # auto-advance after this many seconds if no click

    def __init__(self, config, gui, client_id=0, window_title=None, hwnd=None):
        self.config = config
        self.gui = gui
        self.client_id = client_id
        if window_title:
            # Per-client override of which window this bot owns.
            self.config = dict(config)
            self.config['window_title'] = window_title
        self.running = False
        self.stop_reason = ''
        # hwnd can be pre-resolved by the GUI before window titles are tagged/renamed,
        # avoiding find_window confusion when multiple windows share the same base title.
        self.hwnd = hwnd or None
        self.detector = Detector(config)
        self.banking = BankingFSM(self)
        mouse_cfg = dict(config["mouse_settings"])
        # Auto-randomize seed each session unless user pinned one
        if mouse_cfg.get("mouse_seed") is None:
            mouse_cfg["mouse_seed"] = random.randint(0, 9999)
        self._mouse_seed = mouse_cfg["mouse_seed"]
        print(f"[MOUSE] Profile seed: {self._mouse_seed}")
        self.mouse = HumanMouse(mouse_cfg)
        self.sct = None
        self.inventory_count = 0
        self.inventory_total = 30
        self._inv_fallback_limit = random.randint(28, 30)
        self._click_attempts = {}
        self._blacklist = {}  # key -> expire_time
        
        self._det_buf = _DetectionBuffer()

        # Live tracking
        self.current_fatigue = 0
        self._high_fatigue_count = 0
        self._fatigue_stop_threshold = random.randint(90, 100)
        self.last_click_time = 0
        self.mouse_x = 0  # Current mouse X coordinate
        self.mouse_y = 0  # Current mouse Y coordinate
        
        self.last_break_time = time.time()
        self.next_break_interval = self.get_random_break_interval()
        self.break_end_time = 0

        self._mine_count = 0
        self._last_mine_count_time = 0.0
        self._last_click_center = None  # (screen_x, screen_y) of last click

        self._overlay_buf = _OverlayBuffer()
        self._overlay_refresh_flag = False
        
        self.no_ore_counter = 0
        self.max_no_ore_moves = 5
        self.consecutive_no_ore_count = 0
        # Last time we saw a live game signal (ore detection, inventory OCR,
        # or fatigue OCR). If this goes stale for 30s the bot is likely not
        # logged in — stop as a fail-safe.
        self._last_signal_time = time.time()
        self._last_rotation_time = 0.0
        self._camera_settle_secs = 0.85
        self._last_clicked_key = None
        self._last_clicked_class = None
        self._last_acted_frame_ts = 0.0  # timestamp of the frame we last clicked on
        self._watchdog_ts = time.time()
        self._watchdog_stage = 'init'
        self._inv_fallback_limit = 30  # kept for reference, not used for click counting

        # Mining speed mode (Fast vs Lazy)
        self.fast_mining_enabled = config.get('fast_mining_enabled', True)

        # Anti-ban master switch — when False, disables all antiban checks
        # (individual feature toggles are honored when master is True).
        self.antiban_master_enabled = config.get('antiban_master_enabled', True)

        # F4/F5 hotkey trigger flags (set by GUI hotkey listener thread).
        self._force_goto_bank = False
        self._force_goto_train = False

        # Super-Lazy break tracking
        self._sl_next_break_at = None  # mine-count threshold for next long break

        # "Standing here" suppression (avoid double-acting within 15s)
        self._standing_last_check = 0.0
        self._standing_last_detected = 0.0

        # Live status surfaced to the GUI per-client.
        self.paused = False
        self.last_action = 'Idle'
        self.last_action_ts = time.time()

        # Multi-client mode support.
        # _peer_bots: set on master by start_bot() when multi_client_mode is on.
        # _background_only: set on slave bots — run detection threads only, no action loop.
        self._peer_bots = []
        self._background_only = False

        # Teleport / environment-change detector
        self._env_baseline = None       # small grayscale fingerprint (numpy array)
        self._env_last_check = 0.0
        self._env_pause_until = 0.0     # skip checks during known self-caused motion
        self._env_trip_count = 0        # consecutive drastic frames required to trip
        self._last_window_region = None  # shared with OCR background thread

    def _stop_bot(self, reason, beep_pattern=None):
        """Central stop handler — sets reason, beeps, updates GUI."""
        self.stop_reason = reason
        self.running = False
        print(f"[STOP] {reason}")
        try:
            self.gui.log_debug(f'⛔ STOPPED: {reason}')
        except Exception:
            pass
        try:
            self.gui.root.after(0, lambda r=reason: self.gui.show_stop_reason(r))
        except Exception:
            pass
        # Always beep on stop — use provided pattern, or default alarm
        try:
            pattern = beep_pattern or [(1200, 200), (900, 200), (1500, 400)]
            for freq, dur in pattern:
                winsound.Beep(freq, dur)
        except Exception:
            pass
        try:
            self.gui.root.after(0, self.gui.stop_bot)
        except Exception:
            pass

    def _speed_mode(self):
        """Resolve the active speed mode for THIS client. 'fast' / 'lazy' / 'super_lazy'.
        Reads `speed_mode` first; falls back to legacy `fast_mining_enabled`."""
        mode = (self.config.get('speed_mode') or '').lower().strip()
        if mode in ('fast', 'lazy', 'super_lazy'):
            return mode
        return 'fast' if self.config.get('fast_mining_enabled', True) else 'lazy'

    def _set_action(self, msg):
        """Update last_action / timestamp — read by GUI status panel."""
        self.last_action = msg
        self.last_action_ts = time.time()

    def pause(self):
        self.paused = True
        self._set_action('Paused')

    def resume(self):
        self.paused = False
        self._set_action('Resumed')

    def _schedule_next_clickback(self):
        """Pick the next clickback fire time using a jittered minute range.
        User picks V minutes; actual fire = V*60 - random(30, 60) seconds.
        So 5 → 4:00–4:30, 15 → 14:00–14:30."""
        try:
            mn = int(self.config.get('clickback_min_min', 5))
            mx = int(self.config.get('clickback_max_min', 15))
        except (TypeError, ValueError):
            mn, mx = 5, 15
        if mn > mx: mn, mx = mx, mn
        v = random.randint(mn, mx)
        delay = v * 60 - random.uniform(30.0, 60.0)
        self._next_clickback_at = time.time() + max(60.0, delay)
        self._dbg(f'[CLICKBACK] next fire in {delay:.0f}s (base {v}m)')

    def _do_clickback(self):
        """Perform Click A then Click B at user-configured screen coords."""
        a = self.config.get('clickback_a')
        b = self.config.get('clickback_b')
        if not a or not b:
            self._dbg('[CLICKBACK] skipped — A or B not set')
            return
        try:
            self.gui.log_debug(f'Clickback fire: A{tuple(a)} → B{tuple(b)}')
        except Exception:
            pass
        try:
            with MiningBot.MOUSE_LOCK:
                self.bring_window_to_front()
                time.sleep(0.08)
                self.mouse.move_and_click((int(a[0]), int(a[1])))
                time.sleep(random.uniform(0.4, 1.0))
                self.mouse.move_and_click((int(b[0]), int(b[1])))
        except Exception as e:
            self._dbg(f'[CLICKBACK] error: {e}')

    def _pick_walkto_destination(self):
        """Pool Bank entries (short, full, user-set, X,Y) and pick one at random.
        Always RNG, no toggle. 'None' or blank = ignored."""
        pool = []
        for k in ('walkto_dest1_a', 'walkto_dest1_b',
                  'walkto_dest1_user', 'walkto_dest1_xy'):
            v = (self.config.get(k, '') or '').strip()
            if v and v.lower() != 'none':
                pool.append(v)
        if not pool:
            return (self.config.get('walkto_destination', '') or '').strip()
        return random.choice(pool)

    def _pick_walkto_train_destination(self):
        """Pool Train entries (short, full, user-set, X,Y) and pick one at random.
        'None' or blank = ignored."""
        pool = []
        for k in ('walkto_train1_a', 'walkto_train1_b',
                  'walkto_train1_user', 'walkto_train1_xy'):
            v = (self.config.get(k, '') or '').strip()
            if v and v.lower() != 'none':
                pool.append(v)
        return random.choice(pool) if pool else ''

    def _pick_teleport_reaction(self):
        """Pick what to type after a teleport-detect trigger.
        Source: a single comma-separated user-editable string. Random pick if
        `teleport_pick_random` else first item."""
        raw = (self.config.get('teleport_reactions_text', '') or '').strip()
        pool = [s.strip() for s in raw.split(',') if s.strip()]
        if not pool:
            # Legacy fallbacks
            legacy = (self.config.get('teleport_message', '') or '').strip()
            if legacy:
                pool = [legacy]
        if not pool:
            return ''
        if self.config.get('teleport_pick_random', True):
            return random.choice(pool)
        return pool[0]

    def _schedule_walkto_beeps(self):
        """Fire one user-configurable beep after ::walkto is sent (toggle-gated).
        Runs on a detached timer so it fires even after the bot stops."""
        if not self.config.get('walkto_beep1_enabled', True):
            return
        try:
            delay1 = float(self.config.get('walkto_beep1_secs', 40))
        except (TypeError, ValueError):
            delay1 = 40.0
        delay1 = max(1.0, min(600.0, delay1))

        def _beep1():
            try:
                winsound.Beep(1000, 250)
                self.gui.log_debug(f'🔔 WalkTo beep (+{delay1:.0f}s)')
            except Exception:
                pass
        threading.Timer(delay1, _beep1).start()

    def get_click_position(self, box):
        """Click within ±10px of the box center, clamped inside the box."""
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        x = int(max(x1 + 2, min(x2 - 2, cx + random.randint(-10, 10))))
        y = int(max(y1 + 2, min(y2 - 2, cy + random.randint(-10, 10))))
        return (x, y)
    
    def get_distance_from_center(self, box, frame_width, frame_height):
        """Calculate distance from ore center to screen center"""
        x1, y1, x2, y2 = box
        ore_cx = (x1 + x2) / 2.0
        ore_cy = (y1 + y2) / 2.0
        
        screen_cx = frame_width / 2.0
        screen_cy = frame_height / 2.0
        
        # Euclidean distance
        distance = ((ore_cx - screen_cx) ** 2 + (ore_cy - screen_cy) ** 2) ** 0.5
        return distance
    
    def get_random_break_interval(self):
        """Get random interval before next break"""
        min_sec = self.config["break_settings"].get("min_seconds_between_breaks", 600)
        max_sec = self.config["break_settings"].get("max_seconds_between_breaks", 3600)
        return random.uniform(min_sec, max_sec)
    
    def get_random_break_duration(self):
        """Get random break duration"""
        min_sec = self.config["break_settings"].get("min_break_duration_seconds", 60)
        max_sec = self.config["break_settings"].get("max_break_duration_seconds", 1200)
        return random.uniform(min_sec, max_sec)
    
    def find_window(self):
        """Resolve self.hwnd from the configured window title.
        Prefers exact match, then case-insensitive partial match.
        Handles RSCRevolution / RSCRevolution 2 naming variants automatically."""
        # Prefer a pre-resolved hwnd (avoids same-title confusion + post-tagging renames).
        try:
            if self.hwnd and win32gui.IsWindow(self.hwnd):
                title = win32gui.GetWindowText(self.hwnd)
                print(f'[CLIENT {self.client_id}] Using pre-resolved hwnd={self.hwnd} title="{title}"')
                return True
        except Exception:
            self.hwnd = None  # invalid handle — fall through to search

        target_title = self.config.get("window_title", "")
        if not target_title:
            return False

        exact = []
        partial = []

        def enum_callback(hwnd, _):
            txt = win32gui.GetWindowText(hwnd)
            if not txt:
                return True
            if txt.lower() == target_title.lower():
                exact.append(hwnd)
            elif target_title.lower() in txt.lower() or txt.lower() in target_title.lower():
                partial.append(hwnd)
            return True

        win32gui.EnumWindows(enum_callback, None)

        chosen = exact[0] if exact else (partial[0] if partial else None)
        if chosen:
            self.hwnd = chosen
            print(f'[CLIENT {self.client_id}] hwnd={chosen} title="{target_title}" '
                  f'({"exact" if exact else "substring"})')
            return True
        return False
    
    def bring_window_to_front(self):
        if self.hwnd:
            try:
                # AttachThreadInput trick — lets SetForegroundWindow work
                # even when another window in our process has focus
                foreground_hwnd = win32gui.GetForegroundWindow()
                fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(
                    foreground_hwnd, None)
                cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
                attached = False
                if fg_tid != cur_tid:
                    ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, True)
                    attached = True
                win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(self.hwnd)
                if attached:
                    ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                try:
                    win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(self.hwnd)
                except Exception:
                    pass
            time.sleep(0.2)
    
    def move_camera(self):
        # Cooldown: don't rotate again for 1.5–2.5s so rotations don't stack back-to-back.
        # Check BEFORE incrementing so the zoom-out counter only counts real rotations.
        if time.time() - self._last_rotation_time < random.uniform(1.5, 2.5):
            return

        self.no_ore_counter += 1

        # Smart-zoom removed per user request — was unreliable and conflicted with
        # clickback/hover. Just reset the counter and let normal rotation continue.
        if self.no_ore_counter >= self.max_no_ore_moves:
            self.no_ore_counter = 0
            time.sleep(random.uniform(0.7, 1.1))
            return

        if random.random() < 0.80:
            self._mouse_rotate()
        else:
            self._keyboard_rotate()
        self._last_rotation_time = time.time()
        self._pause_env_check(3.0, reset_baseline=True)

    def _force_rotate(self):
        """Force camera rotation immediately without the odd/even check"""
        if random.random() < 0.80:
            self._mouse_rotate()
        else:
            self._keyboard_rotate()
        self._last_rotation_time = time.time()
        self._pause_env_check(3.0, reset_baseline=True)
        time.sleep(random.uniform(0.3, 0.8))

    def _keyboard_rotate(self):
        # Focus first so keybd_event reaches the game, then also send PostMessage
        # as a belt-and-suspenders fallback (Java may prefer one path or the other).
        self.bring_window_to_front()
        actions = [win32con.VK_LEFT, win32con.VK_RIGHT, win32con.VK_UP, win32con.VK_DOWN]
        sequence_length = 1 if random.random() < 0.8 else 2
        for _ in range(sequence_length):
            key = random.choice(actions)
            press_duration = random.uniform(0.10, 0.25)
            win32api.keybd_event(key, 0, 0, 0)
            win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, key, 0)
            time.sleep(press_duration)
            win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, key, 0)
            time.sleep(random.uniform(0.25, 0.55))

    def _zoom_out(self):
        """Scroll down to zoom out after repeated no-ore rotations."""
        try:
            rect = win32gui.GetClientRect(self.hwnd)
            pt = win32gui.ClientToScreen(self.hwnd, (rect[2] // 2, rect[3] // 2))
            win32api.SetCursorPos(pt)
            time.sleep(0.05)
            for _ in range(random.randint(2, 4)):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -120, 0)
                time.sleep(random.uniform(0.08, 0.15))
            self._last_rotation_time = time.time()
            print("[CAMERA] Zoomed out after 5 failed rotations")
            try:
                self.gui.log_debug('Zoomed out — no ores found after 5 rotations')
            except Exception:
                pass
        except Exception:
            pass

    def _mouse_rotate(self):
        # Bring window to front so middle-drag is received by the game
        self.bring_window_to_front()
        try:
            rect = win32gui.GetClientRect(self.hwnd)
            pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
            cx = pt[0] + random.randint(int(rect[2] * 0.3), int(rect[2] * 0.7))
            cy = pt[1] + random.randint(int(rect[3] * 0.3), int(rect[3] * 0.7))
            win32api.SetCursorPos((cx, cy))
            time.sleep(0.05)
        except Exception:
            return
        start_x, start_y = win32api.GetCursorPos()
        # Larger horizontal drag so RSC registers a meaningful camera rotation
        target_x = start_x + random.randint(-150, 150)
        target_y = start_y + random.randint(-20, 20)

        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
        time.sleep(random.uniform(0.04, 0.08))
        steps = random.randint(12, 20)
        for i in range(1, steps + 1):
            t = i / steps
            x = int(start_x + (target_x - start_x) * t)
            y = int(start_y + (target_y - start_y) * t)
            win32api.SetCursorPos((x, y))
            time.sleep(random.uniform(0.008, 0.020))
        time.sleep(random.uniform(0.05, 0.10))
        win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
        time.sleep(random.uniform(0.15, 0.25))

    def _read_inventory_from_frame(self, frame):
        """Read inventory count (X/30) from top-right corner of RSC window.
        Based on RSC UI: the "3/30" text sits at the very top-right corner,
        roughly X:88-100%, Y:0-6% of the game window.
        """
        if not _HAVE_OCR:
            return None
        import re
        h, w = frame.shape[:2]

        # RSC inventory counter: top-right, a few px from window edge, tic-tac sized
        x1 = int(w * 0.88)
        y1 = max(0, int(h * 0.01))   # ~1% down to skip window border pixels
        x2 = w
        y2 = int(h * 0.07)           # tight crop — text is very small
        roi = frame[y1:y2, x1:x2]

        if roi.size == 0:
            return None

        try:
            global _ocr_reader
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)

            import cv2
            # Upscale 6x — text is very small (tic-tac sized), needs aggressive scaling
            roi_up = cv2.resize(roi, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)

            def _try_ocr(img):
                r = _ocr_reader.readtext(img, detail=0, allowlist='0123456789/')
                return " ".join(r).strip() if r else ""

            # Method 1: raw upscaled
            detected_text = _try_ocr(roi_up)

            # Method 2: isolate yellow/orange text (RSC inventory font color)
            # Yellow-orange = high R, high G, low B in BGR
            if not detected_text or not re.search(r'\d', detected_text):
                hsv = cv2.cvtColor(roi_up, cv2.COLOR_BGR2HSV)
                # Hue 15-35 covers orange→yellow, high saturation & value
                mask = cv2.inRange(hsv, (15, 100, 100), (35, 255, 255))
                isolated = cv2.bitwise_and(roi_up, roi_up, mask=mask)
                gray_iso = cv2.cvtColor(isolated, cv2.COLOR_BGR2GRAY)
                _, thresh_iso = cv2.threshold(gray_iso, 50, 255, cv2.THRESH_BINARY)
                detected_text = _try_ocr(thresh_iso)

            # Method 3: plain grayscale threshold fallback
            if not detected_text or not re.search(r'\d', detected_text):
                gray = cv2.cvtColor(roi_up, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
                detected_text = _try_ocr(thresh)

            if detected_text:
                m = re.search(r'(\d+)\s*/\s*(\d+)', detected_text)
                if m:
                    cur = int(m.group(1))
                    total = int(m.group(2))
                    if 0 <= cur <= 31 and 25 <= total <= 31:
                        return cur, total
                # Fallback: OCR dropped "/" — e.g. "730" → cur=7 total=30
                m2 = re.search(r'(\d{1,2})(30|29|28|27|26|25)', detected_text)
                if m2:
                    cur = int(m2.group(1))
                    total = int(m2.group(2))
                    if 0 <= cur <= 31:
                        return cur, total
        except Exception:
            pass
        return None

    def check_fatigue_message(self, frame, window_region):
        """Check bottom-left chat area for 'you are too tired to mine this rock'.
        Zooms in 3× so small red game-message text reads reliably."""
        if not _HAVE_OCR or not self.config.get("fatigue_detection_enabled", True):
            return False

        try:
            global _ocr_reader
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)

            h, w = frame.shape[:2]
            # Bottom-left chat line where RSC prints "You are too tired..."
            roi = frame[int(h * 0.70):int(h * 0.95), 0:int(w * 0.75)]
            if roi.size == 0:
                return False

            # Upscale 3× for small chat text
            roi_up = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

            keywords = ("too tired to mine", "too tired", "tired to mine")

            def _contains(text):
                t = text.lower()
                return any(k in t for k in keywords)

            # Pass 1: raw upscaled
            results = _ocr_reader.readtext(roi_up, detail=0)
            detected = " ".join(results).lower() if results else ""
            if _contains(detected):
                self._dbg(f'[FATIGUE MSG] {detected}')
                return True

            # Pass 2: isolate red channel (fatigue warning is red text)
            b, g, r = cv2.split(roi_up)
            red_mask = ((r.astype(int) - g.astype(int) > 40) &
                        (r.astype(int) - b.astype(int) > 40) & (r > 120)).astype(np.uint8) * 255
            results2 = _ocr_reader.readtext(red_mask, detail=0)
            detected2 = " ".join(results2).lower() if results2 else ""
            if _contains(detected2):
                self._dbg(f'[FATIGUE MSG red] {detected2}')
                return True
        except Exception as e:
            self._dbg(f'[FATIGUE MSG] err: {e}')
        return False
    
    
    def check_fatigue_bar_topleft(self, frame):
        """
        Alternative fatigue detection: Check the fatigue bar on top-left of game window.
        The fatigue indicator is usually in the top-left stats area.
        Returns True if fatigue bar appears to be at 100% (red/full).
        """
        try:
            h, w = frame.shape[:2]
            
            # Top-left corner where stats/fatigue bar typically is (roughly first 15% width, first 20% height)
            roi_topleft = frame[0:int(h * 0.25), 0:int(w * 0.20)]
            
            if roi_topleft.size == 0:
                return False
            
            # Look for red color (fatigue bar is typically red at high fatigue)
            # Red in BGR is (B, G, R) = (0-50, 0-100, 200-255)
            b, g, r = cv2.split(roi_topleft)
            
            # Create mask for red pixels (high fatigue indicator)
            red_mask = (r > 180) & (g < 120) & (b < 120)
            
            # If more than 5% of top-left area is red, fatigue is likely high
            red_percentage = np.count_nonzero(red_mask) / roi_topleft.size * 100
            
            if red_percentage > 5:
                print(f"[FATIGUE BAR] Detected high fatigue bar (red: {red_percentage:.1f}%)")
                try:
                    self.gui.log_debug(f'⚠️ FATIGUE BAR: High fatigue detected ({red_percentage:.1f}% red)')
                except Exception:
                    pass
                return True
            
        except Exception as e:
            print(f"[FATIGUE BAR] Error checking fatigue bar: {e}")
        
        return False

    def _fatigue_line_variants(self, fat_line):
        """Yield image variants for OCR: raw, green-threshold, red-threshold."""
        yield fat_line
        for ch_idx in (1, 2):  # green, then red (BGR)
            ch = fat_line[:, :, ch_idx]
            ch_up = cv2.resize(ch, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
            _, binary = cv2.threshold(ch_up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            yield binary

    def read_menu_bar_fatigue(self, frame):
        """Read fatigue % from the top-left stat panel (Hits/Prayer/Fatigue/FPS).
        Primary: pytesseract with INTER_NEAREST upscale (preserves RSC pixel font).
        Fallback: EasyOCR on same variants."""
        if not self.config.get("fatigue_detection_enabled", True):
            return None

        import re

        try:
            h, w = frame.shape[:2]
            roi = frame[0:int(h * 0.35), 0:int(w * 0.25)]
            if roi.size == 0:
                return None

            def _preprocess(img):
                """8× INTER_NEAREST upscale + multiple binary variants."""
                big = cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
                gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY) if len(big.shape) == 3 else big
                _, bw_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                _, bw80 = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
                variants = [bw_otsu, cv2.bitwise_not(bw_otsu), cv2.bitwise_not(bw80)]
                if len(img.shape) == 3:
                    hsv = cv2.cvtColor(big, cv2.COLOR_BGR2HSV)
                    yel = cv2.inRange(hsv, (15, 50, 80), (45, 255, 255))
                    variants.append(yel)
                return variants

            def _parse(text):
                m = re.search(r'(\d{1,3})\s*%?', text.strip())
                if m:
                    v = int(m.group(1))
                    if 0 <= v <= 100:
                        return v
                return None

            # Fatigue is line 3 of 4 → ~45-78% of panel height
            fat_y1 = int(roi.shape[0] * 0.45)
            fat_y2 = int(roi.shape[0] * 0.78)
            fat_crop = roi[fat_y1:fat_y2, :] if (fat_y2 - fat_y1) > 2 else roi
            crop_variants = _preprocess(fat_crop if fat_crop.size > 0 else roi)

            # --- pytesseract (primary) ---
            if _HAVE_PYTESSERACT:
                cfg = '--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789%'
                for img_v in crop_variants:
                    try:
                        v = _parse(pytesseract.image_to_string(img_v, config=cfg))
                        if v is not None:
                            self._dbg(f'[FATIGUE] tess {v}%')
                            self.current_fatigue = v
                            return v
                    except Exception:
                        pass
                # retry on full ROI
                for img_v in _preprocess(roi):
                    try:
                        v = _parse(pytesseract.image_to_string(img_v, config=cfg))
                        if v is not None:
                            self._dbg(f'[FATIGUE] tess-full {v}%')
                            self.current_fatigue = v
                            return v
                    except Exception:
                        pass

            # --- EasyOCR (fallback) ---
            if _HAVE_OCR:
                global _ocr_reader
                if _ocr_reader is None:
                    _ocr_reader = easyocr.Reader(['en'], gpu=False)
                for img_v in crop_variants:
                    try:
                        results = _ocr_reader.readtext(img_v, detail=0,
                                                       allowlist='0123456789%')
                        v = _parse(' '.join(results))
                        if v is not None:
                            self._dbg(f'[FATIGUE] ocr {v}%')
                            self.current_fatigue = v
                            return v
                    except Exception:
                        pass

            self._dbg('[FATIGUE] all methods failed')

        except Exception as e:
            self._dbg(f'[FATIGUE] error: {e}')

        return None
    
    def should_take_break(self):
        if not self.config["break_settings"].get("breaks_enabled", True):
            return False
        return time.time() - self.last_break_time >= self.next_break_interval
    
    def take_break(self):
        duration = self.get_random_break_duration()
        self.break_end_time = time.time() + duration
        print(f"Taking break for {duration:.0f}s...")
        try:
            self.gui.log_debug(f'☕ Break started ({int(duration)}s)')
        except Exception:
            pass
        time.sleep(duration)
        self.break_end_time = 0
        self.last_break_time = time.time()
        self.next_break_interval = self.get_random_break_interval()
    
    def get_micro_break(self):
        """Get a random micro break duration if enabled"""
        if self.config["break_settings"].get("micro_breaks_enabled", False):
            min_ms = self.config["break_settings"].get("micro_break_min_ms", 100)
            max_ms = self.config["break_settings"].get("micro_break_max_ms", 500)
            return random.randint(min_ms, max_ms) / 1000.0
        return 0
    
    def _dbg(self, msg):
        """Log only when verbose debug is enabled."""
        if not self.config.get('verbose_debug', False):
            return
        ts = time.strftime('%H:%M:%S')
        print(f'[DBG {ts}] {msg}')
        try:
            self.gui.log_debug(f'[V] {msg}')
        except Exception:
            pass

    def _start_watchdog(self):
        """Background thread — alerts if main loop stalls >10s."""
        def _watch():
            while self.running:
                time.sleep(5)
                if not self.running:
                    break
                stall = time.time() - self._watchdog_ts
                if stall > 10:
                    msg = f'⚠ WATCHDOG: loop stalled {stall:.1f}s at stage [{self._watchdog_stage}]'
                    print(msg)
                    try:
                        self.gui.log_debug(msg)
                    except Exception:
                        pass
        t = threading.Thread(target=_watch, daemon=True)
        t.start()

    def _start_ocr_thread(self):
        """Background thread: runs slow EasyOCR every ~6s.
        Stores results in self.current_fatigue / self.inventory_count so the
        main action loop never blocks on OCR."""
        def _ocr_loop():
            from mss import mss as _mss_ocr
            sct = _mss_ocr()
            interval = 6.0
            while self.running:
                t0 = time.time()
                try:
                    region = self._last_window_region
                    if region is None:
                        time.sleep(0.5)
                        continue

                    screenshot = sct.grab(region)
                    frame = np.array(screenshot)[:, :, :3]

                    # Inventory count
                    inv = self._read_inventory_from_frame(frame)
                    if inv is not None:
                        cur, total = inv
                        self.inventory_count = cur
                        self.inventory_total = total
                        self._last_signal_time = time.time()
                        try:
                            self.gui.root.after(0, lambda c=cur, t=total: self.gui.update_inventory(c, t))
                        except Exception:
                            pass
                        if self.config.get('stop_on_full_inventory', True) and not self.config.get('powermine_enabled', False):
                            if cur >= 28 and total >= 25:
                                self._stop_bot(f'Inventory full ({cur}/{total})',
                                               [(1200, 300), (1200, 300), (1500, 500)])
                                return

                    # Fatigue bar %
                    fat_val = self.read_menu_bar_fatigue(frame)
                    if fat_val is not None:
                        self.current_fatigue = fat_val
                        self._last_signal_time = time.time()
                        try:
                            self.gui.root.after(0, lambda v=fat_val: self.gui.update_live_stats(fatigue=v))
                        except Exception:
                            pass

                    # "Too tired to mine" chat message
                    if self.check_fatigue_message(frame, region):
                        self._stop_bot('Too tired to mine', [(1000, 200), (1000, 200)])
                        return

                    # "You have been standing here" anti-AFK nudge
                    self._check_standing_here(frame)

                    # Chat-text stop phrases
                    if (self.config.get('antiban_master_enabled', True)
                            and self.config.get('chat_text_stop_enabled', False)):
                        hit = self._detect_chat_text(frame)
                        if hit:
                            self._stop_bot(f'Chat text matched: "{hit}"',
                                           [(1600, 200), (1000, 200)])
                            return

                except Exception as e:
                    self._dbg(f'OCR thread error: {e}')

                elapsed = time.time() - t0
                time.sleep(max(0.0, interval - elapsed))

        t = threading.Thread(target=_ocr_loop, daemon=True, name='ocr-thread')
        t.start()

    def _start_detection_thread(self):
        """Dedicated thread: captures + runs YOLO continuously.
        Uses a generation counter so stop+restart never leaves a zombie thread."""
        self._detection_gen = getattr(self, '_detection_gen', 0) + 1
        my_gen = self._detection_gen

        def _loop():
            from mss import mss as _mss_det
            sct = _mss_det()
            def _label(mode):
                return {'fast': 'fast 800-1200ms',
                        'lazy': 'lazy 1200-2400ms',
                        'super_lazy': 'super-lazy 10-30s'}.get(mode, 'lazy')
            print(f'[DETECT] Detection thread started gen={my_gen} '
                  f'({_label(self._speed_mode())})')
            while self.running and self._detection_gen == my_gen:
                t0 = time.time()
                # Re-evaluate per tick so a live mode-switch takes effect immediately.
                mode = self._speed_mode()
                if mode == 'fast':
                    poll_interval = random.uniform(0.80, 1.20)
                elif mode == 'super_lazy':
                    poll_interval = random.uniform(10.0, 30.0)
                else:
                    poll_interval = random.uniform(1.20, 2.40)
                try:
                    rect = win32gui.GetClientRect(self.hwnd)
                    pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
                    region = {
                        'left': pt[0], 'top': pt[1],
                        'width': rect[2] - rect[0], 'height': rect[3] - rect[1],
                    }
                    screenshot = sct.grab(region)
                    frame = np.ascontiguousarray(np.array(screenshot)[:, :, :3])
                    detections, annotated = self.detector.detect_with_vis(frame, region)
                    reg_tuple = (region['left'], region['top'], region['width'], region['height'])
                    self._det_buf.update(detections, frame, reg_tuple)
                    self._overlay_buf.update_frame(annotated, region=reg_tuple, detections=detections)
                except Exception as e:
                    self._dbg(f'Detection thread error: {e}')
                elapsed = time.time() - t0
                sleep_t = max(0.0, poll_interval - elapsed)
                time.sleep(sleep_t)
        t = threading.Thread(target=_loop, daemon=True, name='detection-thread')
        self._detection_thread = t
        t.start()

    def start_background_only(self):
        """Multi-client slave: OCR thread only — MC loop drives YOLO + clicking."""
        if not self.find_window():
            raise Exception(f"Window '{self.config['window_title']}' not found")
        self.running = True
        from mss import mss as _mss
        self.sct = _mss()
        # Start OCR so fatigue/inventory are read for this window.
        # Skip detection thread — master's MC loop does live YOLO for all windows.
        # Skip watchdog — MC loop updates self._watchdog_ts on master; slaves don't need it.
        self._start_ocr_thread()
        # Keep thread alive; update watchdog timestamp so if watchdog IS running it won't fire.
        while self.running:
            self._watchdog_ts = time.time()
            time.sleep(1.0)

    def _run_multi_client_loop(self):
        """Single action loop that hops through master + all peer bot windows.
        Stays in each window until an ore is clicked (or 30s timeout), THEN hops.
        Mouse never leaves a window until the click is made."""
        from mss import mss as _mss_mc
        mc_sct = _mss_mc()
        all_bots = [self] + list(self._peer_bots)
        mc_idx = 0
        print(f'[MC] Multi-Client loop started — {len(all_bots)} windows: '
              + ', '.join(f'Bot{b.client_id+1}(hwnd={b.hwnd})' for b in all_bots))
        try:
            self.gui.log_debug(f'Multi-Client loop: {len(all_bots)} windows active')
        except Exception:
            pass

        while self.running:
            self._watchdog_ts = time.time()

            cur = all_bots[mc_idx % len(all_bots)]
            mc_idx += 1

            if cur.paused:
                time.sleep(0.05)
                continue

            # Skip while mid-walkto or blocked (no-ore 30s timeout).
            if time.time() < getattr(cur, '_mc_skip_until', 0):
                _rem = int(cur._mc_skip_until - time.time())
                print(f'[MC] Bot{cur.client_id+1} blocked — {_rem}s remaining')
                time.sleep(0.05)
                continue

            # Validate window handle
            if not cur.hwnd or not win32gui.IsWindow(cur.hwnd):
                print(f'[MC] Bot{cur.client_id+1} hwnd={cur.hwnd} invalid — skipping')
                time.sleep(0.1)
                continue

            try:
                rect = win32gui.GetClientRect(cur.hwnd)
                pt = win32gui.ClientToScreen(cur.hwnd, (0, 0))
                win_region = {
                    'left': pt[0], 'top': pt[1],
                    'width': rect[2] - rect[0], 'height': rect[3] - rect[1],
                }
            except Exception as e:
                print(f'[MC] Bot{cur.client_id+1} region error: {e}')
                time.sleep(0.1)
                continue

            # Bring window to front — mouse was pre-positioned here last cycle.
            with MiningBot.MOUSE_LOCK:
                cur.bring_window_to_front()

            print(f'[MC] → Bot{cur.client_id+1} (hwnd={cur.hwnd})')
            cur._last_window_region = win_region

            # ── Inner loop: stay in this window until ore clicked or 30s ──────
            _win_start = time.time()
            _inner_no_ore = 0
            _did_click = False

            while self.running and not _did_click:
                self._watchdog_ts = time.time()

                # 30-second no-ore timeout → block this window, move on.
                if time.time() - _win_start > 30.0:
                    print(f'[MC] Bot{cur.client_id+1} no ore for 30s — blocking 30s')
                    cur._mc_skip_until = time.time() + 30.0
                    break

                # Live YOLO using master's warm model
                try:
                    screenshot = mc_sct.grab(win_region)
                    frame = np.ascontiguousarray(np.array(screenshot)[:, :, :3])
                    detections, annotated = self.detector.detect_with_vis(frame, win_region)
                    reg_tuple = (win_region['left'], win_region['top'],
                                 win_region['width'], win_region['height'])
                    self._overlay_buf.update_frame(annotated, region=reg_tuple, detections=detections)
                    cur._det_buf.update(detections, frame, reg_tuple)
                except Exception as e:
                    print(f'[MC] YOLO error on Bot{cur.client_id+1}: {e}')
                    time.sleep(0.2)
                    continue

                # Ore-checkbox filter (fall back to master if slave has none enabled)
                _ore_cfg = cur.config.get('ore_checkboxes', {})
                if not any(_ore_cfg.values()):
                    _ore_cfg = self.config.get('ore_checkboxes', {})

                mineable = [
                    d for d in detections
                    if d['class_name'] != 'empty_ore_rock'
                    and _ore_cfg.get(d['class_name'], False)
                ]

                # Fixed-spot filter
                fixed_spots = cur.config.get('fixed_ore_spots', [])
                if not cur.config.get('camera_rotation_enabled', True) and fixed_spots:
                    fh, fw = frame.shape[:2]
                    def _near_fixed(det, _fw=fw, _fh=fh, _spots=fixed_spots):
                        bx1, by1, bx2, by2 = det['box']
                        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
                        for rx, ry in _spots:
                            if math.sqrt((cx - rx * _fw) ** 2 + (cy - ry * _fh) ** 2) < 55:
                                return True
                        return False
                    mineable = [d for d in mineable if _near_fixed(d)]

                if not mineable:
                    _inner_no_ore += 1
                    _elapsed = int(time.time() - _win_start)
                    print(f'[MC] Bot{cur.client_id+1} no ore (#{_inner_no_ore}, {_elapsed}s elapsed)')
                    # Rotate camera every 3rd miss while waiting
                    if (cur.config.get('camera_rotation_enabled', True)
                            and _inner_no_ore % 3 == 0):
                        with MiningBot.MOUSE_LOCK:
                            cur.move_camera()
                    time.sleep(0.15)
                    continue

                # ── Ore found — verify it's still filled, then click ──────────
                _inner_no_ore = 0
                fh, fw = frame.shape[:2]
                mineable.sort(key=lambda x: cur.get_distance_from_center(x['box'], fw, fh))
                target = mineable[0]
                tbx1, tby1, tbx2, tby2 = target['box']
                t_cx = (tbx1 + tbx2) / 2
                t_cy = (tby1 + tby2) / 2

                # Fresh YOLO pass to confirm the rock hasn't gone empty since
                # the previous frame was captured (latency between scan & click).
                try:
                    _vshot = mc_sct.grab(win_region)
                    _vframe = np.ascontiguousarray(np.array(_vshot)[:, :, :3])
                    _vdets, _vann = self.detector.detect_with_vis(_vframe, win_region)
                    # Check: is the closest detection at target's location now empty?
                    _target_still_valid = True
                    for _vd in _vdets:
                        _vx1, _vy1, _vx2, _vy2 = _vd['box']
                        _vcx = (_vx1 + _vx2) / 2
                        _vcy = (_vy1 + _vy2) / 2
                        if math.sqrt((_vcx - t_cx) ** 2 + (_vcy - t_cy) ** 2) < 40:
                            if _vd['class_name'] == 'empty_ore_rock':
                                _target_still_valid = False
                                print(f'[MC] Bot{cur.client_id+1} pre-click verify: rock went empty — skip')
                            break
                    if not _target_still_valid:
                        time.sleep(0.1)
                        continue
                except Exception as _ve:
                    print(f'[MC] pre-click verify error: {_ve}')
                    # Proceed anyway — verification is best-effort

                click_pos = cur.get_click_position(target['box'])
                screen_x = int(click_pos[0] + win_region['left'])
                screen_y = int(click_pos[1] + win_region['top'])

                # Target box in screen coords — used for post-click verification.
                _box_sx1 = int(tbx1 + win_region['left'])
                _box_sy1 = int(tby1 + win_region['top'])
                _box_sx2 = int(tbx2 + win_region['left'])
                _box_sy2 = int(tby2 + win_region['top'])

                print(f'[MC] Bot{cur.client_id+1} clicking {target["class_name"]} @ ({screen_x},{screen_y})')
                with MiningBot.MOUSE_LOCK:
                    self._set_action(f'MC: Mining {target["class_name"]} (Bot{cur.client_id+1})')
                    cur.mouse.move_and_click((screen_x, screen_y))

                    # Verify cursor landed inside the ore's bounding box.
                    # Overshoot-correct drift or mid-air jitter can put it just outside.
                    _cx, _cy = win32api.GetCursorPos()
                    if not (_box_sx1 <= _cx <= _box_sx2 and _box_sy1 <= _cy <= _box_sy2):
                        print(f'[MC] Bot{cur.client_id+1} cursor missed box ({_cx},{_cy}) — forcing re-click')
                        win32api.SetCursorPos((screen_x, screen_y))
                        time.sleep(random.uniform(0.04, 0.08))
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        time.sleep(random.uniform(0.06, 0.12))
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

                cur.last_click_time = int(time.time() * 1000)
                _now_ms = cur.last_click_time
                if _now_ms - getattr(cur, '_last_mine_count_time', 0) >= 500:
                    cur._mine_count = getattr(cur, '_mine_count', 0) + 1
                    cur._last_mine_count_time = _now_ms

                _did_click = True

            # ── After clicking: pre-position toward next window ───────────────
            if _did_click:
                try:
                    _next_bot = all_bots[mc_idx % len(all_bots)]
                    if _next_bot.hwnd and win32gui.IsWindow(_next_bot.hwnd):
                        _nr = win32gui.GetClientRect(_next_bot.hwnd)
                        _np = win32gui.ClientToScreen(_next_bot.hwnd, (0, 0))
                        _nw = _nr[2] - _nr[0]
                        _nh = _nr[3] - _nr[1]
                        _next_fixed = _next_bot.config.get('fixed_ore_spots', [])
                        if _next_fixed:
                            # Move toward a random fixed spot in the next window ±20px
                            _spot = random.choice(_next_fixed)
                            _ncx = _np[0] + int(_spot[0] * _nw) + random.randint(-20, 20)
                            _ncy = _np[1] + int(_spot[1] * _nh) + random.randint(-20, 20)
                        else:
                            # No fixed spots — drift to window centre ±50px
                            _ncx = _np[0] + _nw // 2 + random.randint(-50, 50)
                            _ncy = _np[1] + _nh // 2 + random.randint(-50, 50)
                        with MiningBot.MOUSE_LOCK:
                            cur.mouse.move_mouse(_ncx, _ncy)
                except Exception:
                    pass

                # ── WalkTo trigger (per-window) ───────────────────────────────
                if cur.config.get('walkto_enabled', False):
                    _wdest = cur._pick_walkto_destination()
                    if _wdest:
                        _mn = int(cur.config.get('walkto_min_clicks', 35))
                        _mx = int(cur.config.get('walkto_max_clicks', 50))
                        if not hasattr(cur, '_mc_walkto_next_at'):
                            cur._mc_walkto_next_at = cur._mine_count + random.randint(_mn, max(_mn, _mx))
                        if cur._mine_count >= cur._mc_walkto_next_at:
                            _cmd = f'::walkto {_wdest}'
                            print(f'[MC] Bot{cur.client_id+1} walkto: {_cmd}')
                            try:
                                self.gui.log_debug(f'MC WalkTo Bot{cur.client_id+1}: {_cmd}')
                            except Exception:
                                pass
                            cur._schedule_walkto_beeps()
                            with MiningBot.MOUSE_LOCK:
                                cur._type_ingame_message(_cmd)
                            cur._mc_skip_until = time.time() + 45.0
                            cur._mc_walkto_next_at = (cur._mine_count
                                                       + random.randint(_mn, max(_mn, _mx)))
                            continue  # hop immediately; no speed-mode sleep needed

                # ── Speed-mode sleep then hop ─────────────────────────────────
                _mode = cur._speed_mode()
                if _mode == 'fast':
                    time.sleep(random.uniform(0.80, 1.20))
                elif _mode == 'super_lazy':
                    time.sleep(random.uniform(10.0, 30.0))
                else:  # lazy
                    time.sleep(random.uniform(1.20, 2.40))

    def run(self):
        if not self.find_window():
            raise Exception(f"Window '{self.config['window_title']}' not found")
        
        self.bring_window_to_front()
        self.running = True
        self.last_break_time = time.time()
        print(f"Bot started! Fatigue stop threshold: {self._fatigue_stop_threshold}%")
        try:
            self.gui.log_debug(f'Bot started — fatigue stop @ {self._fatigue_stop_threshold}%')
        except Exception:
            pass

        try:
            # reset GUI counters on start
            self.gui.root.after(0, self.gui.reset_obtain_count)
            self.gui.root.after(0, lambda: self.gui.update_inventory(0, 30))
        except Exception:
            pass

        self._mouse_parked_outside = False

        # mss for OCR (inventory/fatigue reads — separate from detection thread)
        from mss import mss as _mss
        self.sct = _mss()

        self._start_watchdog()
        self._start_detection_thread()
        self._start_ocr_thread()

        # Brief wait so detection thread has at least one frame ready
        time.sleep(0.35)

        # Multi-client mode: master's loop cycles all windows; slaves run background only.
        if self._peer_bots:
            self._run_multi_client_loop()
            return

        action_loop_hz = 0.040  # 40ms action loop — detection thread drives YOLO at 100ms
        last_loop_time = time.time()

        while self.running:
            self._watchdog_ts = time.time()
            self._watchdog_stage = 'action-loop-hz'
            elapsed = time.time() - last_loop_time
            if elapsed < action_loop_hz:
                time.sleep(action_loop_hz - elapsed)
            last_loop_time = time.time()

            # Per-client pause: skip work entirely until resumed.
            if self.paused:
                time.sleep(0.2)
                continue

            try:
                self._watchdog_stage = 'break-check'
                if self.should_take_break():
                    self._watchdog_stage = 'taking-break'
                    self._dbg('Taking scheduled break')
                    self.take_break()
                    self.bring_window_to_front()

                # F5 hotkey: immediately go to bank (GUI sets this flag)
                if self._force_goto_bank:
                    self._force_goto_bank = False
                    dest = self._pick_walkto_destination()
                    if dest:
                        cmd = f'::walkto {dest}'
                        self._dbg(f'[F5] Forced bank: {cmd}')
                        try:
                            self.gui.log_debug(f'F5 → {cmd}')
                        except Exception:
                            pass
                        self._schedule_walkto_beeps()
                        self._type_ingame_message(cmd)
                        self._stop_bot(f'F5 WalkTo bank: {cmd}', [])
                        break
                    else:
                        try:
                            self.gui.log_debug('F5: no bank destination configured')
                        except Exception:
                            pass

                # F4 hotkey: go to training area
                if self._force_goto_train:
                    self._force_goto_train = False
                    dest = self._pick_walkto_train_destination()
                    if dest:
                        cmd = f'::walkto {dest}'
                        self._dbg(f'[F4] Forced train: {cmd}')
                        try:
                            self.gui.log_debug(f'F4 → {cmd}')
                        except Exception:
                            pass
                        self._type_ingame_message(cmd)
                    else:
                        try:
                            self.gui.log_debug('F4: no train destination configured')
                        except Exception:
                            pass

                # Get current window rect for click coord translation + OCR
                self._watchdog_stage = 'win32-rect'
                rect = win32gui.GetClientRect(self.hwnd)
                pt = win32gui.ClientToScreen(self.hwnd, (0, 0))
                window_region = {
                    'left': pt[0], 'top': pt[1],
                    'width': rect[2] - rect[0], 'height': rect[3] - rect[1],
                }
                self._last_window_region = window_region

                # Read latest detections from the dedicated detection thread (no YOLO here)
                self._watchdog_stage = 'read-detections'
                (detections, frame, _reg), frame_ts = self._det_buf.get()
                if frame is None:
                    time.sleep(0.05)
                    continue

                # Banking FSM tick: when active, it consumes the iteration so
                # the normal mining click-cycle is skipped.
                if not self.banking.is_idle():
                    if self.banking.tick(detections, frame):
                        time.sleep(0.05)
                        continue

                # Periodic clickback: A → pause → B at jittered intervals.
                if self.config.get('clickback_enabled', False):
                    if not hasattr(self, '_next_clickback_at'):
                        self._schedule_next_clickback()
                    elif time.time() >= self._next_clickback_at:
                        self._do_clickback()
                        self._schedule_next_clickback()

                # Gate: only act once per fresh YOLO scan AND only on frames
                # captured AFTER the most recent camera rotation finished.
                # Without the rotation check, a frame captured mid-rotation
                # passes the freshness test but holds stale geometry → misclick.
                if frame_ts <= self._last_acted_frame_ts:
                    time.sleep(0.05)
                    continue
                rot_settle = self._camera_settle_secs
                if frame_ts < (self._last_rotation_time + rot_settle):
                    # Frame predates the rotation-settle window — wait for a
                    # truly post-rotation capture before acting.
                    time.sleep(0.05)
                    continue

                # ── Round-robin gate ─────────────────────────────────────────
                # In multi-client mode only the "active" bot runs the action
                # path (click OR rotate). The others spin here at 40ms until
                # the turn is passed to them. This ensures the physical mouse
                # never interleaves between windows mid-action.
                if len(MiningBot._ACTIVE_CLIENT_IDS) > 1:
                    _my_turn = False
                    with MiningBot._TURN_LOCK:
                        _n = len(MiningBot._ACTIVE_CLIENT_IDS)
                        _cur = MiningBot._ACTIVE_CLIENT_IDS[MiningBot._TURN_IDX[0] % _n]
                        # Auto-advance a stale turn so one dead bot can't block all others
                        if _cur != self.client_id:
                            if time.time() - MiningBot._TURN_SINCE[0] > MiningBot.TURN_TIMEOUT_S:
                                MiningBot._TURN_IDX[0] = (MiningBot._TURN_IDX[0] + 1) % _n
                                MiningBot._TURN_SINCE[0] = time.time()
                                _cur = MiningBot._ACTIVE_CLIENT_IDS[MiningBot._TURN_IDX[0] % _n]
                        _my_turn = (_cur == self.client_id)
                    if not _my_turn:
                        time.sleep(0.05)
                        continue  # leave frame un-consumed so we act on it when turn arrives
                # ─────────────────────────────────────────────────────────────

                self._last_acted_frame_ts = frame_ts  # consume this scan
                self._dbg(f'Got {len(detections)} detections from buffer')
                now_sig = time.time()
                if detections:
                    self._last_signal_time = now_sig
                # Fail-safe: if no live signal (ore detection / inventory OCR /
                # fatigue OCR) for 30s, assume the game isn't logged in.
                if now_sig - self._last_signal_time > 30:
                    # Zoom out fully before stopping so the game state is visible
                    try:
                        self.bring_window_to_front()
                        time.sleep(0.5)
                        self._zoom_out()
                        time.sleep(1.0)
                    except Exception:
                        pass
                    self._stop_bot('Fail-safe: no game signal for 30s (likely logged out)',
                                   [(1400, 250), (900, 250)])
                    break
                
                # Check if last clicked ore has since depleted (only clear attempts on success).
                # We deliberately do NOT penalise "still showing" here because the ore
                # takes several seconds to deplete and would double-count with the increment
                # already applied when the click was dispatched.
                if self._last_clicked_key is not None:
                    empty_keys = set()
                    for det in detections:
                        bx1, by1, bx2, by2 = det["box"]
                        dk = (int((bx1+bx2)/2)//10, int((by1+by2)/2)//10)
                        if det["class_name"] == "empty_ore_rock":
                            empty_keys.add(dk)
                    if self._last_clicked_key in empty_keys:
                        self._click_attempts.pop(self._last_clicked_key, None)
                        self._dbg(f'[CLICK CHECK] Ore depleted at {self._last_clicked_key}')
                    self._last_clicked_key = None

                # Filter mineable ores
                mineable = []
                for det in detections:
                    ore_name = det["class_name"]
                    if ore_name == "empty_ore_rock":
                        continue
                    if self.config["ore_checkboxes"].get(ore_name, False):
                        mineable.append(det)
                
                # Fixed-spot filter: when rotation off + spots defined, only mine near those spots
                fixed_spots = self.config.get('fixed_ore_spots', [])
                if not self.config.get('camera_rotation_enabled', True) and fixed_spots:
                    frame_h, frame_w = frame.shape[:2]
                    def _near_spot(det):
                        bx1, by1, bx2, by2 = det['box']
                        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
                        for rx, ry in fixed_spots:
                            sx, sy = rx * frame_w, ry * frame_h
                            if math.sqrt((cx - sx)**2 + (cy - sy)**2) < 55:
                                return True
                        return False
                    mineable = [d for d in mineable if _near_spot(d)]

                if mineable:
                    # Ores detected — reset no-ore counter regardless of settle state
                    self.no_ore_counter = 0
                    self.consecutive_no_ore_count = 0

                    # Skip clicking if camera recently rotated — positions are stale
                    secs_since_rotation = time.time() - self._last_rotation_time
                    if secs_since_rotation < self._camera_settle_secs:
                        wait = self._camera_settle_secs - secs_since_rotation
                        print(f"[CAMERA] Settling ({wait:.2f}s) before clicking")
                        time.sleep(wait)
                        continue  # Re-scan with fresh frame after settle
                    
                    # PRIMARY: Sort by distance from center (closest ore to character)
                    # SECONDARY: Sort by priority order (if configured)
                    priority_order = self.config["priority_order"]
                    frame_h, frame_w = frame.shape[:2]
                    
                    # Sort: closest to center first, then by priority order if same distance
                    mineable.sort(key=lambda x: (
                        self.get_distance_from_center(x["box"], frame_w, frame_h),  # Primary: closest to center
                        priority_order.index(x["class_name"]) if x["class_name"] in priority_order else 999  # Secondary: priority
                    ))
                    
                    target = mineable[0]
                    target_distance = self.get_distance_from_center(target["box"], frame_w, frame_h)
                    
                    print(f"Mining: {target['class_name']} (distance: {target_distance:.1f}px from center)")
                    try:
                        self.gui.log_debug(f"Mining: {target['class_name']} (distance: {target_distance:.1f}px from center)")
                    except Exception:
                        pass
                    bx1, by1, bx2, by2 = target["box"]
                    center = (int((bx1+bx2)/2), int((by1+by2)/2))
                    key = (center[0]//10, center[1]//10)
                    # purge expired blacklist entries
                    now = time.time()
                    for bk in list(self._blacklist.keys()):
                        if self._blacklist[bk] <= now:
                            del self._blacklist[bk]

                    # Same-spot double-click guard (always on, distinct from periodic
                    # "clickback" feature). Skips if target is within 35px of the
                    # previous click and inside the 3s cooldown window.
                    _scr_cx = center[0] + window_region['left']
                    _scr_cy = center[1] + window_region['top']
                    _cooldown_ms = 3000
                    if (not self.config.get('hover_mode_enabled', False)
                            and self._last_click_center is not None):
                        _dx = _scr_cx - self._last_click_center[0]
                        _dy = _scr_cy - self._last_click_center[1]
                        if math.sqrt(_dx*_dx + _dy*_dy) < 35:
                            _since_ms = time.time() * 1000 - self.last_click_time
                            if _since_ms < _cooldown_ms:
                                time.sleep(0.05)
                                continue

                    # In fixed-spot mode (rotation disabled + spots set), skip blacklisting
                    # entirely — there's nowhere else to go, so blacklisting deadlocks the bot.
                    fixed_spot_mode = (not self.config.get('camera_rotation_enabled', True)
                                       and bool(fixed_spots))
                    if not fixed_spot_mode:
                        if key in self._blacklist:
                            try:
                                self.gui.log_debug('Ore blacklisted — rotating for new target')
                            except Exception:
                                pass
                            self._force_rotate()
                            time.sleep(self.config['detection_settings']['no_ore_retry_delay_ms'] / 1000.0)
                            if len(MiningBot._ACTIVE_CLIENT_IDS) > 1:
                                with MiningBot._TURN_LOCK:
                                    _n = len(MiningBot._ACTIVE_CLIENT_IDS)
                                    MiningBot._TURN_IDX[0] = (MiningBot._TURN_IDX[0] + 1) % _n
                                    MiningBot._TURN_SINCE[0] = time.time()
                            continue
                        self._click_attempts[key] = self._click_attempts.get(key, 0)
                        if self._click_attempts[key] >= 3:
                            self._blacklist[key] = now + 30.0
                            try:
                                self.gui.log_debug('Ore stuck (3 clicks) — blacklisted 30s')
                            except Exception:
                                pass
                            self._force_rotate()
                            time.sleep(self.config['detection_settings']['no_ore_retry_delay_ms'] / 1000.0)
                            if len(MiningBot._ACTIVE_CLIENT_IDS) > 1:
                                with MiningBot._TURN_LOCK:
                                    _n = len(MiningBot._ACTIVE_CLIENT_IDS)
                                    MiningBot._TURN_IDX[0] = (MiningBot._TURN_IDX[0] + 1) % _n
                                    MiningBot._TURN_SINCE[0] = time.time()
                            continue
                    
                    # Pre-click YOLO poll: verify the target is still the ore we
                    # want — not empty_rock. Uses the freshest detection buffer.
                    tgt_bx1, tgt_by1, tgt_bx2, tgt_by2 = target["box"]
                    tgt_cx = (tgt_bx1 + tgt_bx2) / 2
                    tgt_cy = (tgt_by1 + tgt_by2) / 2
                    (latest_dets, _, _), _ = self._det_buf.get()
                    still_valid = False
                    for _d in latest_dets:
                        if _d['class_name'] == 'empty_ore_rock':
                            continue
                        _bx1, _by1, _bx2, _by2 = _d['box']
                        _dcx = (_bx1 + _bx2) / 2
                        _dcy = (_by1 + _by2) / 2
                        if abs(_dcx - tgt_cx) < 40 and abs(_dcy - tgt_cy) < 40:
                            still_valid = True
                            break
                    if not still_valid:
                        self._dbg(f'[CLICK] Target already empty/gone — skipping click')
                        try:
                            self.gui.log_debug('Target depleted before click — skipping')
                        except Exception:
                            pass
                        continue

                    # get click position (frame-local) and convert to screen coords
                    click_pos = self.get_click_position(target["box"])
                    click_pos = (int(click_pos[0] + window_region["left"]), int(click_pos[1] + window_region["top"]))

                    # Acquire the shared mouse lock so a second client can't interleave
                    # mid-click. Single-client = uncontested. Window focus + click
                    # must be atomic per client.
                    with MiningBot.MOUSE_LOCK:
                        self._watchdog_stage = 'bring-to-front'
                        self.bring_window_to_front()
                        time.sleep(0.1)

                        self._watchdog_stage = 'mouse-move-click'
                        self._dbg(f'Clicking {target["class_name"]} at {click_pos}')
                        self.mouse_x = click_pos[0]
                        self.mouse_y = click_pos[1]

                        self._mouse_parked_outside = False
                        self.mouse.move_and_click(click_pos)
                        self._set_action(f'Mining {target["class_name"]}')

                    # Record the time of this click (in milliseconds since epoch)
                    self.last_click_time = int(time.time() * 1000)
                    self._pause_env_check(5.0)  # keep baseline so terror still detectable

                    # ── Round-robin: pass turn to next bot right after clicking ──
                    # We advance immediately so the next bot can click during our
                    # post-click delay, maximising clicks-per-minute across all clients.
                    if len(MiningBot._ACTIVE_CLIENT_IDS) > 1:
                        with MiningBot._TURN_LOCK:
                            _n = len(MiningBot._ACTIVE_CLIENT_IDS)
                            MiningBot._TURN_IDX[0] = (MiningBot._TURN_IDX[0] + 1) % _n
                            MiningBot._TURN_SINCE[0] = time.time()

                    # Antiban: move mouse outside the game window after clicking
                    # HOVER MODE: always stays on-screen to hover next ore, so skip this
                    if (self.config.get('mouse_outside_window', False)
                            and not self.config.get('hover_mode_enabled', False)):
                        try:
                            left = window_region['left']
                            top = window_region['top']
                            w = window_region['width']
                            h = window_region['height']
                            # Park mouse on left, right, or bottom only — never top
                            edge = random.randint(0, 2)
                            offset = random.randint(5, 40)
                            if edge == 0:
                                ox, oy = left - offset, random.randint(top + int(h * 0.3), top + h)
                            elif edge == 1:
                                ox, oy = left + w + offset, random.randint(top + int(h * 0.3), top + h)
                            else:
                                ox, oy = random.randint(left + int(w * 0.1), left + int(w * 0.9)), top + h + offset
                            self.mouse.move_mouse(ox, oy)
                            self._mouse_parked_outside = True

                            if self._speed_mode() == 'fast':
                                # Fast mode: very brief pause outside then return immediately
                                time.sleep(random.uniform(0.08, 0.25))
                                rx = random.randint(left + int(w * 0.15), left + int(w * 0.85))
                                ry = random.randint(top + int(h * 0.15), top + int(h * 0.85))
                                self.mouse.move_mouse(rx, ry)
                                self._mouse_parked_outside = False
                            # Lazy / super-lazy: mouse stays outside until next ore
                        except Exception:
                            pass

                    # record attempt and stamp last clicked for next-frame verification
                    self._click_attempts[key] = self._click_attempts.get(key, 0) + 1
                    self._last_clicked_key = key
                    self._last_clicked_class = target["class_name"]
                    self._last_click_center = (_scr_cx, _scr_cy)

                    now_ms = time.time() * 1000
                    if now_ms - self._last_mine_count_time >= 500:
                        self._mine_count += 1
                        self._last_mine_count_time = now_ms

                    # Walkto trigger: after a random number of clicks, type ::walkto <dest>
                    if self.config.get('walkto_enabled', False):
                        dest = self._pick_walkto_destination()
                        if dest:
                            if not hasattr(self, '_walkto_next_at'):
                                mn = int(self.config.get('walkto_min_clicks', 35))
                                mx = int(self.config.get('walkto_max_clicks', 50))
                                self._walkto_next_at = self._mine_count + random.randint(mn, max(mn, mx))
                            if self._mine_count >= self._walkto_next_at:
                                cmd = f'::walkto {dest}'
                                self._dbg(f'[WALKTO] Typing: {cmd}')
                                try:
                                    self.gui.log_debug(f'WalkTo: {cmd}')
                                except Exception:
                                    pass
                                self._schedule_walkto_beeps()
                                self._set_action(f'WalkTo: {cmd}')
                                if self.config.get('banking_enabled', False):
                                    # Hand over to the banking FSM — it issues
                                    # the walkto itself and drives bank-deposit-return.
                                    self.banking.begin_bank_run(dest)
                                else:
                                    self._type_ingame_message(cmd)
                                    self._stop_bot(f'WalkTo executed: {cmd}', [])

                    self._watchdog_stage = 'post-click-sleep'
                    hover_mode = self.config.get('hover_mode_enabled', False)
                    hover_clicked = False

                    if hover_mode and self.running:
                        fixed_spots = self.config.get('fixed_ore_spots', [])
                        f_h, f_w = frame.shape[:2]

                        if fixed_spots:
                            num_spots = len(fixed_spots)
                            # Which fixed spot did we just click?
                            # Find nearest spot to click_pos (screen coords).
                            cur_idx = 0
                            _min_d = float('inf')
                            for _i, (_rx, _ry) in enumerate(fixed_spots):
                                _sx = _rx * f_w + window_region['left']
                                _sy = _ry * f_h + window_region['top']
                                _d = math.sqrt((click_pos[0]-_sx)**2 + (click_pos[1]-_sy)**2)
                                if _d < _min_d:
                                    _min_d = _d
                                    cur_idx = _i
                            next_idx = (cur_idx + 1) % num_spots
                            rx, ry = fixed_spots[next_idx]

                            # Screen coords of next spot
                            next_sx = int(rx * f_w + window_region['left'])
                            next_sy = int(ry * f_h + window_region['top'])

                            # Try to refine aim to actual ore detection near that spot
                            (fresh_dets, _, _), _ = self._det_buf.get()
                            hx, hy = next_sx, next_sy
                            _next_ore_confirmed = False
                            for _d in fresh_dets:
                                if _d['class_name'] == 'empty_ore_rock':
                                    continue
                                if not self.config['ore_checkboxes'].get(_d['class_name'], False):
                                    continue
                                _b = _d['box']
                                _dcx = (_b[0] + _b[2]) / 2
                                _dcy = (_b[1] + _b[3]) / 2
                                if math.sqrt((_dcx + window_region['left'] - next_sx) ** 2 +
                                             (_dcy + window_region['top'] - next_sy) ** 2) < 60:
                                    _cp = self.get_click_position(_d['box'])
                                    hx = int(_cp[0] + window_region['left'])
                                    hy = int(_cp[1] + window_region['top'])
                                    _next_ore_confirmed = True
                                    break

                            try:
                                self.gui.log_debug(f'Hover {cur_idx}→{next_idx} ore_confirmed={_next_ore_confirmed}')
                            except Exception:
                                pass

                            if not _next_ore_confirmed:
                                self._dbg(f'[HOVER] no ore at spot {next_idx} — skipping click')
                            else:
                                # Move to next spot immediately
                                self.mouse.move_mouse(hx, hy)
                                self._watchdog_ts = time.time()

                                # Wait for current spot to go empty — failsafe 1400-1600ms
                                failsafe = random.uniform(1.4, 1.6)
                                transitioned = self._wait_for_ore_empty_at(
                                    float(click_pos[0]), float(click_pos[1]),
                                    window_region, max_wait=failsafe)
                                self._watchdog_ts = time.time()

                                if self.running:
                                    self._dbg(f'[HOVER] {"depleted" if transitioned else "failsafe"} → clicking spot {next_idx}')
                                    time.sleep(random.uniform(0.04, 0.10))
                                    self.mouse.click()
                                    _ht = time.time()
                                    self.last_click_time = int(_ht * 1000)
                                    self._last_click_center = (float(hx), float(hy))
                                    self._pause_env_check(5.0)
                                    _now_ms2 = _ht * 1000
                                    if _now_ms2 - self._last_mine_count_time >= 500:
                                        self._mine_count += 1
                                        self._last_mine_count_time = _now_ms2
                                    hover_clicked = True
                        else:
                            # No fixed spots — fallback: find nearest available ore
                            next_ore = self._get_hover_target(target, window_region)
                            if next_ore is not None:
                                hx, hy, h_key, h_det = next_ore
                                self.mouse.move_mouse(hx, hy)
                                self._watchdog_ts = time.time()
                                failsafe = random.uniform(1.4, 1.6)
                                transitioned = self._wait_for_ore_empty_at(
                                    float(click_pos[0]), float(click_pos[1]),
                                    window_region, max_wait=failsafe)
                                self._watchdog_ts = time.time()
                                if self.running:
                                    time.sleep(random.uniform(0.04, 0.10))
                                    self.mouse.click()
                                    _ht = time.time()
                                    self.last_click_time = int(_ht * 1000)
                                    self._last_click_center = (float(hx), float(hy))
                                    self._pause_env_check(5.0)
                                    _now_ms2 = _ht * 1000
                                    if _now_ms2 - self._last_mine_count_time >= 500:
                                        self._mine_count += 1
                                        self._last_mine_count_time = _now_ms2
                                    hover_clicked = True

                    if not hover_clicked:
                        _mode = self._speed_mode()
                        if _mode == 'fast':
                            post_delay = random.uniform(0.8, 1.2)
                        elif _mode == 'super_lazy':
                            # 1–30s, biased toward the high end (triangular with mode=25)
                            post_delay = random.triangular(1.0, 30.0, 25.0)
                        else:
                            post_delay = random.uniform(1.2, 2.4)
                        post_delay += self.get_micro_break()
                        self._watchdog_ts = time.time()
                        self._dbg(f'Post-click sleep {post_delay:.2f}s')
                        time.sleep(post_delay)

                        # Super Lazy: random long break every 10–40 clicks
                        if _mode == 'super_lazy':
                            if self._sl_next_break_at is None:
                                self._sl_next_break_at = self._mine_count + random.randint(10, 40)
                            if self._mine_count >= self._sl_next_break_at:
                                _break_secs = random.uniform(10.0, 45.0)
                                self._dbg(f'[SUPER LAZY] Long break {_break_secs:.1f}s after {self._mine_count} clicks')
                                try:
                                    self.gui.log_debug(f'Super Lazy break: {_break_secs:.1f}s')
                                except Exception:
                                    pass
                                self._watchdog_ts = time.time()
                                time.sleep(_break_secs)
                                self._sl_next_break_at = self._mine_count + random.randint(10, 40)

                    # Lazy / super-lazy idle pause (toggle)
                    _mode_check = self._speed_mode()
                    if (_mode_check in ('lazy', 'super_lazy')
                            and self.config.get('lazy_idle_pause_enabled', False)
                            and not self.config.get('hover_mode_enabled', False)):
                        # Slow down further when powermine is also on — user feedback: too fast.
                        _pm = self.config.get('powermine_enabled', False)
                        _pause_lo, _pause_hi = (8, 35) if _pm else (5, 25)
                        _idle_lo, _idle_hi = (8.0, 25.0) if _pm else (5.0, 20.0)
                        if not hasattr(self, '_lazy_next_pause_at'):
                            self._lazy_next_pause_at = self._mine_count + random.randint(_pause_lo, _pause_hi)
                        if self._mine_count >= self._lazy_next_pause_at:
                            idle_secs = random.uniform(_idle_lo, _idle_hi)
                            print(f"[LAZY IDLE] Pausing {idle_secs:.1f}s (mouse outside window)")
                            try:
                                self.gui.log_debug(f'Lazy idle pause: {idle_secs:.1f}s')
                            except Exception:
                                pass
                            try:
                                rect2 = win32gui.GetClientRect(self.hwnd)
                                pt2 = win32gui.ClientToScreen(self.hwnd, (0, 0))
                                iw, ih = rect2[2], rect2[3]
                                edge2 = random.randint(0, 2)
                                off2 = random.randint(20, 60)
                                if edge2 == 0:
                                    ox = pt2[0] - off2
                                    oy = pt2[1] + random.randint(ih // 3, ih)
                                elif edge2 == 1:
                                    ox = pt2[0] + iw + off2
                                    oy = pt2[1] + random.randint(ih // 3, ih)
                                else:
                                    ox = pt2[0] + random.randint(iw // 10, iw * 9 // 10)
                                    oy = pt2[1] + ih + off2
                                self.mouse.move_mouse(ox, oy)
                            except Exception:
                                pass
                            time.sleep(idle_secs)
                            self._lazy_next_pause_at = self._mine_count + random.randint(_pause_lo, _pause_hi)

                else:
                    rotation_enabled = self.config.get("camera_rotation_enabled", True)

                    if rotation_enabled:
                        print(f"[NO ORE] No ores found — count {self.consecutive_no_ore_count + 1}/30")
                        try:
                            self.gui.log_debug(f'No ores — rotating ({self.consecutive_no_ore_count + 1}/30)')
                        except Exception:
                            pass
                        self.consecutive_no_ore_count += 1
                        # 30-rotation failsafe is always on (no longer optional).
                        if (self.config.get('antiban_master_enabled', True)
                                and self.consecutive_no_ore_count >= 30):
                            self._stop_bot(
                                'Antiban failsafe — no ores found 30 times in a row',
                                [(1500, 200), (1200, 200), (900, 400)]
                            )
                            break
                        self._watchdog_stage = 'camera-rotate'
                        self._dbg('Rotating camera')
                        self._set_action('Rotating camera (no ore)')
                        self.move_camera()
                        # Force the next click to wait for a brand-new
                        # post-rotation frame: invalidate any in-flight frame.
                        self._last_acted_frame_ts = time.time()
                    # Fixed-spot mode: silently wait for ore respawn
                    time.sleep(self.config['detection_settings']['no_ore_retry_delay_ms'] / 1000.0)
                    # ── Round-robin: pass turn after no-ore cycle ──────────────
                    if len(MiningBot._ACTIVE_CLIENT_IDS) > 1:
                        with MiningBot._TURN_LOCK:
                            _n = len(MiningBot._ACTIVE_CLIENT_IDS)
                            MiningBot._TURN_IDX[0] = (MiningBot._TURN_IDX[0] + 1) % _n
                            MiningBot._TURN_SINCE[0] = time.time()

                # Fast pixel checks (no OCR) — mod crown + environment change
                # Slow OCR (inventory, fatigue bar, chat text) runs in background thread
                now_chk = time.time()
                if now_chk - getattr(self, '_last_chk_time', 0) >= 2.0:
                    self._last_chk_time = now_chk
                    try:
                        screenshot_chk = self.sct.grab(window_region)
                        frame_check = np.array(screenshot_chk)[:, :, :3]

                        if (self.config.get('antiban_master_enabled', True)
                                and self.config.get('mod_crown_detection_enabled', False)):
                            if self._detect_mod_crown(frame_check):
                                self._stop_bot('Mod crown detected in chat',
                                               [(1800, 200), (1200, 200), (1800, 400)])
                                break

                        if self._check_environment_change(frame_check):
                            msg = self._pick_teleport_reaction()
                            if msg:
                                self._dbg(f'[TELEPORT] Typing reaction: {msg}')
                                self._type_ingame_message(msg)
                            self._stop_bot('Scenery changed drastically — possible teleport',
                                           [(1500, 250), (900, 250), (1500, 500)])
                            break
                    except Exception:
                        pass

                # Fatigue stop — uses cached value updated by OCR background thread
                # Hard-disable when powermine + powermine_disable_fatigue flag set.
                _pm_no_fatigue = (self.config.get('powermine_enabled', False)
                                  and self.config.get('powermine_disable_fatigue', False))
                if (self.config.get('antiban_master_enabled', True)
                        and self.config.get('fatigue_detection_enabled', True)
                        and not _pm_no_fatigue):
                    if self.current_fatigue >= self._fatigue_stop_threshold:
                        self._high_fatigue_count += 1
                        self._dbg(f'Fatigue {self.current_fatigue}% >= {self._fatigue_stop_threshold}% ({self._high_fatigue_count}/3)')
                        try:
                            self.gui.log_debug(f'⚠ Fatigue {self.current_fatigue}% (stop@{self._fatigue_stop_threshold}%, {self._high_fatigue_count}/3)')
                        except Exception:
                            pass
                    else:
                        self._high_fatigue_count = 0
                    if self._high_fatigue_count >= 3:
                        self._stop_bot(f'Fatigue {self.current_fatigue}% >= threshold {self._fatigue_stop_threshold}%',
                                       [(1000, 200), (1000, 300), (800, 500)])
                        break

            except Exception as e:
                print(f"Error in bot loop: {e}")
                time.sleep(1)
        
        try:
            self.gui.log_debug('Bot stopped')
        except Exception:
            pass
        print("Bot stopped!")
    
    # ── Hover Mode helpers ────────────────────────────────────────────────────

    def _get_hover_target(self, current_target, window_region):
        """Return (screen_x, screen_y, grid_key, det) for the next best mineable ore,
        excluding the ore currently being mined. Returns None if no candidate found."""
        (detections, frame, _), _ = self._det_buf.get()
        enabled_ores = self.config.get('ore_checkboxes', {})
        priority_order = self.config.get('priority_order', [])
        fixed_spots = self.config.get('fixed_ore_spots', [])
        use_fixed = (not self.config.get('camera_rotation_enabled', True) and bool(fixed_spots))

        candidates = []
        cur_bx1, cur_by1, cur_bx2, cur_by2 = current_target['box']
        cur_cx = (cur_bx1 + cur_bx2) / 2
        cur_cy = (cur_by1 + cur_by2) / 2

        if window_region is None:
            return None

        frame_w = window_region['width']
        frame_h = window_region['height']

        for det in detections:
            cn = det['class_name']
            if cn == 'empty_ore_rock':
                continue
            if not enabled_ores.get(cn, False):
                continue
            bx1, by1, bx2, by2 = det['box']
            dcx = (bx1 + bx2) / 2
            dcy = (by1 + by2) / 2
            # Skip the ore we just clicked (within 15px)
            if abs(dcx - cur_cx) < 15 and abs(dcy - cur_cy) < 15:
                continue
            # Respect fixed ore spots — only hover to ores near a configured spot
            if use_fixed:
                near = any(
                    math.sqrt((dcx - rx * frame_w) ** 2 + (dcy - ry * frame_h) ** 2) < 55
                    for rx, ry in fixed_spots
                )
                if not near:
                    continue
            grid_key = (int(dcx) // 10, int(dcy) // 10)
            if grid_key in self._blacklist and self._blacklist[grid_key] > time.time():
                continue
            dist = self.get_distance_from_center(det['box'], frame_w, frame_h)
            pri = priority_order.index(cn) if cn in priority_order else 999
            candidates.append((dist, pri, det, grid_key))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[0], x[1]))
        dist, pri, det, grid_key = candidates[0]
        click_pos = self.get_click_position(det['box'])
        sx = int(click_pos[0] + window_region['left'])
        sy = int(click_pos[1] + window_region['top'])
        return sx, sy, grid_key, det

    def _wait_for_ore_empty(self, grid_key, current_class, max_wait=12.0):
        """Poll _det_buf until the rock at grid_key is detected as empty_ore_rock.
        In RSC the depleted rock stays visible — it changes class, it doesn't
        disappear. A YOLO miss (not found at all) is NOT treated as depletion.
        Returns True once empty_ore_rock is seen 2 consecutive reads,
        False on timeout."""
        deadline = time.time() + max_wait
        consec_empty = 0
        last_frame_ts = 0.0
        while time.time() < deadline and self.running:
            self._watchdog_ts = time.time()
            (detections, _, _), frame_ts = self._det_buf.get()
            if frame_ts <= last_frame_ts:
                time.sleep(0.05)
                continue
            last_frame_ts = frame_ts

            found_empty = False
            for det in detections:
                bx1, by1, bx2, by2 = det['box']
                dcx = (bx1 + bx2) / 2
                dcy = (by1 + by2) / 2
                k = (int(dcx) // 10, int(dcy) // 10)
                if k == grid_key and det['class_name'] == 'empty_ore_rock':
                    found_empty = True
                    break

            if found_empty:
                self._dbg(f'[HOVER] Rock depleted at {grid_key}')
                return True

        return False

    def _wait_for_ore_empty_at(self, screen_x, screen_y, window_region, max_wait=1.5):
        """Hover-mode depletion check using screen coords.
        Watches for empty_ore_rock within 55px of (screen_x, screen_y).
        Returns True on the FIRST detection frame that shows empty (rock respawns
        ~0.8s after depletion — no time to wait for a second confirmation frame).
        Returns False on timeout (failsafe)."""
        deadline = time.time() + max_wait
        last_ts = 0.0
        while time.time() < deadline and self.running:
            self._watchdog_ts = time.time()
            (dets, _, _), ts = self._det_buf.get()
            if ts <= last_ts:
                time.sleep(0.04)
                continue
            last_ts = ts
            for d in dets:
                if d['class_name'] != 'empty_ore_rock':
                    continue
                bx1, by1, bx2, by2 = d['box']
                cx = (bx1 + bx2) / 2 + window_region['left']
                cy = (by1 + by2) / 2 + window_region['top']
                if math.sqrt((cx - screen_x) ** 2 + (cy - screen_y) ** 2) < 55:
                    return True
        return False

    # ─────────────────────────────────────────────────────────────────────────

    def _type_ingame_message(self, text):
        """Focus the game window and type text + Enter (for chat messages).
        Typing speed is randomized per call — 60% fast typist, 40% hunt-and-peck,
        with occasional multi-char pauses for the slow style."""
        if not text:
            return
        try:
            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.25)
            # Pick a typing personality for this invocation
            _fast_typist = random.random() < 0.6
            if _fast_typist:
                _key_lo, _key_hi = 0.03, 0.08
                _gap_lo, _gap_hi = 0.01, 0.05
            else:
                _key_lo, _key_hi = 0.08, 0.22
                _gap_lo, _gap_hi = 0.05, 0.18
            _burst_count = 0
            _burst_max = random.randint(2, 5)
            for ch in text:
                vk = win32api.VkKeyScan(ch)
                if vk == -1:
                    continue
                shift = (vk >> 8) & 1
                code = vk & 0xFF
                if shift:
                    win32api.keybd_event(0x10, 0, 0, 0)       # Shift down
                win32api.keybd_event(code, 0, 0, 0)            # key down
                time.sleep(random.uniform(_key_lo, _key_hi))
                win32api.keybd_event(code, 0, win32con.KEYEVENTF_KEYUP, 0)
                if shift:
                    win32api.keybd_event(0x10, 0, win32con.KEYEVENTF_KEYUP, 0)
                _burst_count += 1
                # Hunt-and-peck: occasional thinking pause after a few chars
                if not _fast_typist and _burst_count >= _burst_max:
                    time.sleep(random.uniform(0.15, 0.45))
                    _burst_count = 0
                    _burst_max = random.randint(2, 5)
                else:
                    time.sleep(random.uniform(_gap_lo, _gap_hi))
            time.sleep(0.15)
            # Enter
            win32api.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(0x0D, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception as e:
            self._dbg(f'[CHAT] Type error: {e}')

    # ── Environment-change (teleport) detector ───────────────────────────────

    def _env_fingerprint(self, frame):
        """Downscale the central play area to a tiny grayscale fingerprint.
        Excludes top-left info panel and bottom chat ROI."""
        h, w = frame.shape[:2]
        y1 = int(h * 0.30)           # skip top info panel
        y2 = int(h * 0.70)           # skip bottom chat
        x1 = int(w * 0.20)           # skip left edge (inventory etc.)
        x2 = int(w * 0.95)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
        return small.astype(np.int16)

    def _pause_env_check(self, seconds=3.0, reset_baseline=False):
        """Pause the teleport detector for `seconds`.
        Pass reset_baseline=True only after camera rotations — this lets the
        detector rebuild from the new camera angle without a false positive.
        Do NOT reset after ore clicks: keeping the baseline means a terror
        teleport that happens during the click pause is still detectable."""
        self._env_pause_until = time.time() + seconds
        if reset_baseline:
            self._env_baseline = None

    def _detect_chat_text(self, frame):
        """OCR the chat area (bottom-left) and return the first user-configured
        phrase found in the text, or None. Throttled to once every 3s.
        Phrases are matched case-insensitively."""
        if not _HAVE_OCR:
            return None
        raw = self.config.get('chat_text_stop_phrases', []) or []
        phrases = [str(p).strip().lower() for p in raw if str(p).strip()]
        if not phrases:
            return None
        now = time.time()
        if now - getattr(self, '_chat_text_last_check', 0) < 3.0:
            return None
        self._chat_text_last_check = now
        try:
            global _ocr_reader
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)
            h, w = frame.shape[:2]
            roi = frame[int(h * 0.72):int(h * 0.98), 0:int(w * 0.55)]
            if roi.size == 0:
                return None
            results = _ocr_reader.readtext(roi, detail=0)
            text = " ".join(results).lower() if results else ""
            if not text:
                return None
            for p in phrases:
                if p and p in text:
                    return p
        except Exception:
            pass
        return None

    def _check_standing_here(self, frame):
        """OCR the chat area for 'standing here' anti-AFK message.
        On detection: beep once and nudge mouse 1px to reset the in-game timer.
        Throttled to 4s between checks, 15s lockout after a nudge."""
        if not _HAVE_OCR:
            return False
        now = time.time()
        if now - self._standing_last_check < 4.0:
            return False
        self._standing_last_check = now
        # Don't nudge again within 15s of the last one
        if now - self._standing_last_detected < 15.0:
            return False
        try:
            global _ocr_reader
            if _ocr_reader is None:
                _ocr_reader = easyocr.Reader(['en'], gpu=False)
            h, w = frame.shape[:2]
            roi = frame[int(h * 0.72):int(h * 0.98), 0:int(w * 0.55)]
            if roi.size == 0:
                return False
            results = _ocr_reader.readtext(roi, detail=0)
            text = ' '.join(results).lower() if results else ''
            if 'standing' in text:
                self._standing_last_detected = now
                self._dbg('[STANDING] "standing here" detected — beeping and nudging')
                try:
                    self.gui.log_debug('⚠ Standing here — nudging mouse to dismiss')
                except Exception:
                    pass
                try:
                    winsound.Beep(1000, 300)
                except Exception:
                    pass
                try:
                    x, y = win32api.GetCursorPos()
                    win32api.SetCursorPos((x + 1, y))
                    time.sleep(0.05)
                    win32api.SetCursorPos((x, y))
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return False

    def _detect_mod_crown(self, frame):
        """Detect mod/admin crown icons in the bottom-left chat area via
        OpenCV template matching against bundled gold/silver crown PNGs.
        Threshold = 0.70 normalized correlation. Throttled to 1.0s."""
        now = time.time()
        if now - getattr(self, '_crown_last_check', 0) < 1.0:
            return False
        self._crown_last_check = now

        # Lazy-load templates once.
        if not hasattr(self, '_crown_templates'):
            self._crown_templates = []
            tdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
            for name in ('goldcrown1.png', 'silvercrown.png'):
                p = os.path.join(tdir, name)
                if os.path.exists(p):
                    img = cv2.imread(p, cv2.IMREAD_COLOR)
                    if img is not None and img.size > 0:
                        self._crown_templates.append((name, img))
            if not self._crown_templates:
                self._dbg('[MOD-CROWN] no templates loaded; detector disabled')

        if not self._crown_templates:
            return False

        try:
            h, w = frame.shape[:2]
            roi = frame[int(h * 0.72):int(h * 0.99), 0:int(w * 0.20)]
            if roi.size == 0:
                return False
            threshold = 0.70
            for name, tpl in self._crown_templates:
                th, tw = tpl.shape[:2]
                if roi.shape[0] < th or roi.shape[1] < tw:
                    continue
                res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= threshold:
                    self._dbg(f'[MOD-CROWN] {name} matched score={max_val:.3f}')
                    return True
        except Exception as e:
            self._dbg(f'[MOD-CROWN] detect err: {e}')
        return False

    def _check_environment_change(self, frame):
        """Return True if the central scene differs drastically from baseline.
        Rebuilds baseline on every successful non-drastic check."""
        if not self.config.get('antiban_master_enabled', True):
            return False
        if not self.config.get('teleport_detection_enabled', True):
            return False
        now = time.time()
        if now < self._env_pause_until:
            # Keep baseline during click pauses so a terror teleport mid-pause
            # is still detectable. Baseline is only reset explicitly by
            # _pause_env_check(reset_baseline=True) after camera rotations.
            return False
        interval = float(self.config.get('teleport_check_interval_s', 4.0))
        if now - self._env_last_check < interval:
            return False
        self._env_last_check = now

        fp = self._env_fingerprint(frame)
        if fp is None:
            return False
        if self._env_baseline is None:
            self._env_baseline = fp
            return False

        diff = np.mean(np.abs(fp - self._env_baseline))
        threshold = float(self.config.get('teleport_threshold', 35.0))

        if diff >= threshold:
            self._env_trip_count += 1
            self._dbg(f'[ENV] Drastic change {diff:.1f} ≥ {threshold} '
                      f'(trip {self._env_trip_count}/2)')
            if self._env_trip_count >= 2:
                self._env_trip_count = 0
                return True
        else:
            self._env_trip_count = 0
            # slowly adapt baseline to natural drift
            self._env_baseline = ((self._env_baseline * 0.6) + (fp * 0.4)).astype(np.int16)
        return False

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self):
        self.running = False
        # Wait for detection thread to finish so its YOLO inference doesn't
        # overlap with a new bot instance's detection thread.
        t = getattr(self, '_detection_thread', None)
        if t is not None and t.is_alive():
            try: t.join(timeout=0.8)
            except Exception: pass
