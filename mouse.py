import win32api
import win32con
import time
import random
import math

class HumanMouse:
    def __init__(self, settings):
        self.settings = settings
        self.min_delay = settings["min_delay_ms"] / 1000.0
        self.max_delay = settings["max_delay_ms"] / 1000.0
        self.curve_strength = settings["human_curve_strength"]
        self._apply_profile(settings.get("mouse_seed", None))

    def _apply_profile(self, seed=None):
        """Generate a randomized mouse personality from a seed."""
        rng = random.Random(seed)  # seeded RNG — reproducible per session
        # Overshoot: how far past the target the mouse goes (5–30%)
        self.overshoot_min = rng.uniform(1.03, 1.10)
        self.overshoot_max = rng.uniform(1.12, 1.30)
        # Speed: step size divisor (smaller = more steps = slower)
        self.step_divisor = rng.uniform(7, 14)
        # Jitter: probability and magnitude of mid-movement wobble
        self.jitter_prob = rng.uniform(0.15, 0.45)
        self.jitter_mag = rng.uniform(1.0, 3.5)
        # Hesitation: pause probability mid-movement
        self.hesitation_prob = rng.uniform(0.05, 0.25)
        # Correction: steps to snap back from overshoot
        self.correction_min = rng.randint(2, 5)
        self.correction_max = rng.randint(6, 12)
        # Click hold duration range
        self.click_hold_min = rng.uniform(0.04, 0.08)
        self.click_hold_max = rng.uniform(0.09, 0.18)
        # Post-target hesitation before click
        self.pre_click_pause_min = rng.uniform(0.03, 0.06)
        self.pre_click_pause_max = rng.uniform(0.07, 0.15)
    
    def move_mouse(self, target_x, target_y):
        """
        Move mouse with realistic human behavior:
        - Overshoots target then corrects
        - Small jerky movements
        - Non-linear acceleration
        - Random pauses and hesitations
        """
        current_x, current_y = win32api.GetCursorPos()
        
        # Calculate distance
        dx = target_x - current_x
        dy = target_y - current_y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance < 1:
            return
        
        # Phase 1: Move toward overshoot point along a slight Bezier curve
        overshoot_factor = random.uniform(self.overshoot_min, self.overshoot_max)
        overshoot_x = target_x + (dx * (overshoot_factor - 1))
        overshoot_y = target_y + (dy * (overshoot_factor - 1))

        # Bezier control point — pulls path slightly off-axis (human hand drift)
        perp_x = -dy / max(distance, 1)
        perp_y =  dx / max(distance, 1)
        drift = random.uniform(-0.25, 0.25) * distance * self.curve_strength
        ctrl_x = current_x + dx * 0.5 + perp_x * drift
        ctrl_y = current_y + dy * 0.5 + perp_y * drift

        steps = max(int(distance / self.step_divisor), 5)

        for i in range(steps):
            t = i / max(steps - 1, 1)
            t_eased = self._ease_in_out_cubic(t)

            # Hesitation pause (profile-driven probability)
            if random.random() < self.hesitation_prob:
                time.sleep(random.uniform(0.01, 0.03))

            # Quadratic Bezier interpolation: start → control → overshoot
            bx = (1 - t_eased)**2 * current_x + 2*(1 - t_eased)*t_eased * ctrl_x + t_eased**2 * overshoot_x
            by = (1 - t_eased)**2 * current_y + 2*(1 - t_eased)*t_eased * ctrl_y + t_eased**2 * overshoot_y

            # Profile-driven jitter layered on top of the curve
            noise_x = random.uniform(-self.jitter_mag, self.jitter_mag) if random.random() < self.jitter_prob else 0
            noise_y = random.uniform(-self.jitter_mag, self.jitter_mag) if random.random() < self.jitter_prob else 0

            win32api.SetCursorPos((int(bx + noise_x), int(by + noise_y)))

            # Slower at start/end, faster in middle (matches ease-in-out feel)
            if t < 0.2 or t > 0.8:
                time.sleep(random.uniform(0.002, 0.006))
            else:
                time.sleep(random.uniform(0.0005, 0.003))

        # Phase 2: Land on overshoot point, brief pause
        win32api.SetCursorPos((int(overshoot_x), int(overshoot_y)))
        time.sleep(random.uniform(0.04, 0.12))

        # Phase 3: Deliberate correction back to target with tiny residual jitter
        correction_steps = random.randint(self.correction_min, self.correction_max)
        for i in range(correction_steps):
            t = i / max(correction_steps - 1, 1)
            x = overshoot_x + (target_x - overshoot_x) * t
            y = overshoot_y + (target_y - overshoot_y) * t
            # Small residual wobble — hand still settling
            x += random.uniform(-0.8, 0.8)
            y += random.uniform(-0.8, 0.8)
            win32api.SetCursorPos((int(x), int(y)))
            time.sleep(random.uniform(0.003, 0.009))

        # Final position — land exactly on target
        win32api.SetCursorPos((int(target_x), int(target_y)))

        # Human hesitation before clicking
        time.sleep(random.uniform(0.04, 0.11))
    
    @staticmethod
    def _ease_in_out_cubic(t):
        """Smooth easing function for more natural acceleration"""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2
    
    def click(self):
        """Human-like click with realistic timing"""
        # Small random jitter before click (aiming)
        current_x, current_y = win32api.GetCursorPos()
        jitter_x = current_x + random.randint(-1, 1)
        jitter_y = current_y + random.randint(-1, 1)
        win32api.SetCursorPos((jitter_x, jitter_y))
        
        # Slight pause before pressing
        time.sleep(random.uniform(self.pre_click_pause_min, self.pre_click_pause_max))

        # Mouse down (variable press time)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        press_duration = random.uniform(self.click_hold_min, self.click_hold_max)
        time.sleep(press_duration)
        
        # Mouse up
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    
    def move_and_click(self, target_pos):
        """Move to target and click with human-like behavior and post-click wait"""
        self.move_mouse(target_pos[0], target_pos[1])
        self.click()
        post_click_delay = random.uniform(0.15, 0.35)
        time.sleep(post_click_delay)