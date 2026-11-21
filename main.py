#!/usr/bin/env python3
"""RobRunAutoClicker - Windows auto-clicker configured for the game ROB RUN.

Hold physical Ctrl + left mouse button to emit synthetic left clicks.
Only the Windows input API is used: no game memory access, no DLL injection,
no network access and no external runtime dependencies.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import random
import sys
import threading
import time
from ctypes import wintypes

APP_NAME = "RobRunAutoClicker"
APP_TITLE = "ROB RUN AutoClicker"
CONFIG_FILENAME = "config.json"
LOG_FILENAME = "RobRunAutoClicker.log"
MUTEX_NAME = r"Local\RobRunAutoClicker_SingleInstance"

# Custom dwExtraInfo marker for every synthetic event we inject.
INPUT_MAGIC = 0x5255434C

CLICK_HOLD_SECONDS = 0.003
FOCUS_CACHE_SECONDS = 0.200
TRIGGER_POLL_SECONDS = 0.005
HOTKEY_POLL_SECONDS = 0.050

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002

VK_LBUTTON = 0x01
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LWIN = 0x5B
VK_RWIN = 0x5C

MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030
MB_ICONERROR = 0x00000010
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000

DEFAULT_CONFIG = {
    "interval_ms": 25,
    "jitter_ms": 5,
    "only_in_game": True,
    "exit_hotkey": "Ctrl+Alt+F8",
    "trigger_mode": "intercept",
    "game_process": "ROB RUN.exe",
    "debug_log": False,
}

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    winmm = ctypes.WinDLL("winmm")
except OSError:  # pragma: no cover - must exist on Windows, but never fatal
    winmm = None


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", _INPUTUNION)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def _configure_winapi() -> None:
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int,
        HOOKPROC,
        wintypes.HINSTANCE,
        wintypes.DWORD,
    ]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.CallNextHookEx.argtypes = [
        wintypes.HHOOK,
        ctypes.c_int,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.MessageBoxW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
    ]
    user32.MessageBoxW.restype = ctypes.c_int

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetConsoleWindow.argtypes = []
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    if winmm is not None:
        winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
        winmm.timeBeginPeriod.restype = wintypes.UINT
        winmm.timeEndPeriod.argtypes = [wintypes.UINT]
        winmm.timeEndPeriod.restype = wintypes.UINT


_configure_winapi()

# TR2: keep a module-level reference to the hook callback for the whole run.
_hook_proc_ref = None
_last_input_error = 0


def application_dir() -> str:
    """Directory that contains the .exe (or main.py when running from source)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def show_message(text: str, *, warning: bool = False, error: bool = False) -> None:
    icon = MB_ICONERROR if error else (MB_ICONWARNING if warning else MB_ICONINFORMATION)
    user32.MessageBoxW(None, text, APP_TITLE, MB_OK | icon | MB_SETFOREGROUND | MB_TOPMOST)


def _is_key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def ctrl_is_down() -> bool:
    return _is_key_down(VK_CONTROL) or _is_key_down(VK_LCONTROL) or _is_key_down(VK_RCONTROL)


def alt_is_down() -> bool:
    return _is_key_down(VK_MENU) or _is_key_down(VK_LMENU) or _is_key_down(VK_RMENU)


def shift_is_down() -> bool:
    return _is_key_down(VK_SHIFT) or _is_key_down(VK_LSHIFT) or _is_key_down(VK_RSHIFT)


def win_is_down() -> bool:
    return _is_key_down(VK_LWIN) or _is_key_down(VK_RWIN)


def foreground_process_name() -> str:
    """Return the executable basename of the foreground window, or ""."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD(0)
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value)
    finally:
        kernel32.CloseHandle(handle)
    return ""


class FocusChecker:
    """Foreground-process check with a cheap, window-aware 200 ms cache.

    GetForegroundWindow() is queried on every call (cheap). The process name
    behind the window is re-resolved immediately when the window changes and
    otherwise at most every FOCUS_CACHE_SECONDS, which keeps a 40 Hz click loop
    from opening a process handle every cycle.
    """

    def __init__(self, game_process: str) -> None:
        self._target = os.path.basename(game_process.strip()).lower()
        self._lock = threading.Lock()
        self._hwnd = None
        self._checked_at = 0.0
        self._cached_result = False

    @property
    def target(self) -> str:
        return self._target

    def is_game_foreground(self, force: bool = False) -> bool:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            with self._lock:
                self._hwnd = None
                self._checked_at = time.perf_counter()
                self._cached_result = False
            return False

        now = time.perf_counter()
        with self._lock:
            if (
                not force
                and hwnd == self._hwnd
                and (now - self._checked_at) < FOCUS_CACHE_SECONDS
            ):
                return self._cached_result

        name = foreground_process_name().lower()
        result = bool(name) and name == self._target
        with self._lock:
            self._hwnd = hwnd
            self._checked_at = time.perf_counter()
            self._cached_result = result
        return result


class Logger:
    """Console output when available, otherwise a file for debug_log builds."""

    def __init__(self, enabled: bool, base_dir: str) -> None:
        self.enabled = enabled
        # A console window means the user can actually see warnings. stdout may
        # be a pipe/file when launched from a script even without a console.
        self.console_available = bool(kernel32.GetConsoleWindow())
        self._stream = sys.stdout
        self._lock = threading.Lock()
        self._file = None
        if enabled and not self.console_available:
            try:
                self._file = open(
                    os.path.join(base_dir, LOG_FILENAME),
                    "a",
                    encoding="utf-8",
                    buffering=1,
                )
            except OSError:
                self._file = None

    def _write(self, level: str, message: str, args: tuple) -> None:
        if not self.enabled:
            return
        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                message = message + " " + repr(args)
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] [{level}] {message}"
        with self._lock:
            if self._stream is not None:
                try:
                    print(line, file=self._stream, flush=True)
                except (OSError, ValueError):
                    self._stream = None
            if self._file is not None:
                try:
                    self._file.write(line + "\n")
                    self._file.flush()
                except OSError:
                    pass

    def info(self, message: str, *args) -> None:
        self._write("INFO", message, args)

    def warn(self, message: str, *args) -> None:
        self._write("WARN", message, args)

    def error(self, message: str, *args) -> None:
        self._write("ERROR", message, args)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except OSError:
                    pass
                self._file = None


def _config_warning(messages: list[str], text: str) -> None:
    messages.append(text)


def _int_from_config(raw: dict, key: str, default: int, low: int, high: int, warnings: list[str]) -> int:
    if key not in raw:
        _config_warning(warnings, f"{key} lipsește; se folosește valoarea implicită {default}.")
        return default
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        _config_warning(warnings, f"{key} trebuie să fie un număr întreg; se folosește {default}.")
        return default
    if not low <= value <= high:
        _config_warning(
            warnings,
            f"{key}={value} este în afara intervalului {low}-{high}; se folosește {default}.",
        )
        return default
    return value


def _key_vk(name: str):
    name = name.strip().lower()
    if len(name) == 1 and name.isalpha():
        return ord(name.upper())
    if len(name) == 1 and name.isdigit():
        return ord(name)
    extra = {
        "esc": 0x1B,
        "escape": 0x1B,
        "space": 0x20,
        "tab": 0x09,
        "insert": 0x2D,
        "delete": 0x2E,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "up": 0x26,
        "down": 0x28,
        "left": 0x25,
        "right": 0x27,
    }
    if name in extra:
        return extra[name]
    if name.startswith("f") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    return None


def parse_hotkey(spec: str):
    """Parse e.g. 'Ctrl+Alt+F8' into (frozenset(modifiers), virtual_key)."""
    if not isinstance(spec, str) or not spec.strip():
        return None
    parts = [part.strip().lower() for part in spec.split("+")]
    if any(not part for part in parts):
        return None
    modifiers = set()
    key_vk = None
    for part in parts:
        if part in ("ctrl", "control"):
            modifiers.add("ctrl")
        elif part == "alt":
            modifiers.add("alt")
        elif part == "shift":
            modifiers.add("shift")
        elif part in ("win", "windows"):
            modifiers.add("win")
        else:
            if key_vk is not None:
                return None
            key_vk = _key_vk(part)
            if key_vk is None:
                return None
    if key_vk is None:
        return None
    return frozenset(modifiers), key_vk


def hotkey_is_down(hotkey) -> bool:
    modifiers, key_vk = hotkey
    if "ctrl" in modifiers and not ctrl_is_down():
        return False
    if "alt" in modifiers and not alt_is_down():
        return False
    if "shift" in modifiers and not shift_is_down():
        return False
    if "win" in modifiers and not win_is_down():
        return False
    return _is_key_down(key_vk)


def validate_config(raw) -> tuple[dict, list[str]]:
    """Return a fully validated config plus human-readable fallback warnings."""
    warnings: list[str] = []
    config = dict(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        _config_warning(warnings, "config.json trebuie să conțină un obiect JSON; se folosesc valorile implicite.")
        return config, warnings

    config["interval_ms"] = _int_from_config(raw, "interval_ms", 25, 5, 500, warnings)
    config["jitter_ms"] = _int_from_config(raw, "jitter_ms", 5, 0, 100, warnings)

    for key in ("only_in_game", "debug_log"):
        if key not in raw:
            _config_warning(warnings, f"{key} lipsește; se folosește valoarea implicită {DEFAULT_CONFIG[key]}.")
        elif not isinstance(raw[key], bool):
            _config_warning(warnings, f"{key} trebuie să fie true sau false; se folosește {DEFAULT_CONFIG[key]}.")
        else:
            config[key] = raw[key]

    mode = raw.get("trigger_mode")
    if mode is None:
        _config_warning(warnings, "trigger_mode lipsește; se folosește \"intercept\".")
    elif not isinstance(mode, str) or mode.strip().lower() not in ("intercept", "passthrough"):
        _config_warning(warnings, "trigger_mode trebuie să fie \"intercept\" sau \"passthrough\"; se folosește \"intercept\".")
    else:
        config["trigger_mode"] = mode.strip().lower()

    game_process = raw.get("game_process")
    if game_process is None:
        _config_warning(
            warnings,
            f'game_process lipsește; se folosește "{DEFAULT_CONFIG["game_process"]}".',
        )
    elif not isinstance(game_process, str) or not game_process.strip():
        _config_warning(
            warnings,
            f'game_process trebuie să fie un nume de proces nevid; se folosește "{DEFAULT_CONFIG["game_process"]}".',
        )
    else:
        config["game_process"] = game_process.strip()

    exit_hotkey = raw.get("exit_hotkey")
    if exit_hotkey is None:
        _config_warning(warnings, "exit_hotkey lipsește; se folosește \"Ctrl+Alt+F8\".")
    elif parse_hotkey(exit_hotkey) is None:
        _config_warning(
            warnings,
            "exit_hotkey nu este valid (exemplu: \"Ctrl+Alt+F8\"); se folosește valoarea implicită.",
        )
    else:
        config["exit_hotkey"] = exit_hotkey.strip()

    return config, warnings


def save_config(path: str, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


def load_config(path: str) -> tuple[dict, list[str]]:
    """Load and validate config; create it with defaults if it is missing."""
    if not os.path.isfile(path):
        try:
            save_config(path, DEFAULT_CONFIG)
        except OSError as exc:
            return dict(DEFAULT_CONFIG), [
                f"Nu am putut crea {CONFIG_FILENAME} ({exc}); se folosesc valorile implicite."
            ]
        return dict(DEFAULT_CONFIG), []

    try:
        # utf-8-sig also accepts files saved with a BOM by Windows tools.
        with open(path, "r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        return dict(DEFAULT_CONFIG), [
            f"Nu am putut citi {CONFIG_FILENAME} ({exc}); se folosesc valorile implicite."
        ]
    return validate_config(raw)


def send_mouse_event(flags: int) -> bool:
    """Inject one left mouse event carrying our dwExtraInfo magic."""
    global _last_input_error
    mouse = MOUSEINPUT(0, 0, 0, flags, 0, ULONG_PTR(INPUT_MAGIC))
    event = INPUT()
    event.type = INPUT_MOUSE
    event.data.mi = mouse
    sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        _last_input_error = ctypes.get_last_error()
        return False
    _last_input_error = 0
    return True


def send_left_down() -> bool:
    return send_mouse_event(MOUSEEVENTF_LEFTDOWN)


def send_left_up() -> bool:
    return send_mouse_event(MOUSEEVENTF_LEFTUP)


class SingleInstance:
    def __init__(self) -> None:
        self.handle = None
        self.already_running = False
        self.error = None

    def acquire(self) -> bool:
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            self.error = ctypes.get_last_error()
            return False
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            self.already_running = True
            return False
        self.handle = handle
        return True

    def release(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.armed = False
        self.activation_id = 0
        self.physical_lmb = False
        self.suppressed_down = False
        self.synthetic_left_down = False
        self.start_event = threading.Event()
        self.quit_event = threading.Event()
        self.fatal_message = None

    def activate(self, suppress: bool):
        with self.lock:
            if self.armed:
                return None
            self.activation_id += 1
            self.armed = True
            self.physical_lmb = True
            self.suppressed_down = suppress
            self.start_event.set()
            return self.activation_id

    def mark_physical_down(self) -> None:
        with self.lock:
            self.physical_lmb = True

    def on_physical_up(self) -> bool:
        with self.lock:
            was_suppressed = self.suppressed_down
            self.suppressed_down = False
            self.physical_lmb = False
            self.armed = False
            self.start_event.clear()
            return was_suppressed

    def is_suppressed(self) -> bool:
        with self.lock:
            return self.suppressed_down

    def disarm(self, activation_id: int) -> None:
        with self.lock:
            if self.activation_id == activation_id:
                self.armed = False


def release_pending_left_up(state: SharedState, logger: Logger) -> bool:
    """Safety net: never leave a synthetic left button down."""
    with state.lock:
        pending = state.synthetic_left_down
    if not pending:
        return True
    for _ in range(5):
        if send_left_up():
            with state.lock:
                state.synthetic_left_down = False
            logger.info("[SAFETY] sent final LEFTUP")
            return True
        time.sleep(0.003)
    logger.error("Could not release the synthetic left mouse button.")
    return False


class ClickWorker(threading.Thread):
    def __init__(
        self,
        state: SharedState,
        focus: FocusChecker,
        logger: Logger,
        config: dict,
    ) -> None:
        super().__init__(name="click-worker", daemon=True)
        self.state = state
        self.focus = focus
        self.logger = logger
        self.only_in_game = bool(config["only_in_game"])
        self.interval = int(config["interval_ms"]) / 1000.0
        self.jitter = int(config["jitter_ms"]) / 1000.0
        self.trigger_mode = config["trigger_mode"]
        self.fatal_message = None

    def _can_click(self, activation_id: int) -> tuple[bool, str]:
        if self.state.quit_event.is_set():
            return False, "shutdown"
        with self.state.lock:
            if not self.state.physical_lmb:
                return False, "LMB released"
            if not self.state.armed or self.state.activation_id != activation_id:
                return False, "disarmed"
        if not ctrl_is_down():
            return False, "Ctrl released"
        if self.only_in_game and not self.focus.is_game_foreground():
            return False, "focus left game"
        return True, ""

    def _wait_until(self, deadline: float, activation_id: int) -> tuple[bool, str]:
        while True:
            ok, reason = self._can_click(activation_id)
            if not ok:
                return False, reason
            remaining = deadline - time.perf_counter()
            if remaining <= 0.0:
                return True, ""
            # Short chunks: the configured interval may be as high as 500 ms,
            # but releasing Ctrl/LMB must always stop clicking within ~50 ms.
            time.sleep(min(remaining, TRIGGER_POLL_SECONDS))

    def run(self) -> None:
        while not self.state.quit_event.is_set():
            if not self.state.start_event.wait(0.1):
                continue
            with self.state.lock:
                self.state.start_event.clear()
                armed = self.state.armed
                activation_id = self.state.activation_id
            if armed:
                self._run_activation(activation_id)

    def _run_activation(self, activation_id: int) -> None:
        reason = "stopped"
        failures = 0
        timer_resolution = False
        self.logger.info(
            "[STATE] CLICKING interval=%sms jitter=%sms mode=%s",
            int(self.interval * 1000),
            int(self.jitter * 1000),
            self.trigger_mode,
        )
        if winmm is not None:
            try:
                if winmm.timeBeginPeriod(1) == 0:
                    timer_resolution = True
            except OSError:
                timer_resolution = False

        try:
            next_click = time.perf_counter()
            while True:
                ok, reason = self._can_click(activation_id)
                if not ok:
                    break
                ok, reason = self._wait_until(next_click, activation_id)
                if not ok:
                    break
                # Re-check immediately before injecting: focus may have changed
                # while waiting for the next click slot.
                ok, reason = self._can_click(activation_id)
                if not ok:
                    break

                cycle_start = time.perf_counter()
                with self.state.lock:
                    self.state.synthetic_left_down = True
                if not send_left_down():
                    with self.state.lock:
                        self.state.synthetic_left_down = False
                    failures += 1
                    self.logger.error(
                        "[STATE] SendInput LEFT DOWN failed (error=%s, attempt=%s)",
                        _last_input_error,
                        failures,
                    )
                    if failures >= 5:
                        reason = "SendInput LEFT DOWN failed repeatedly"
                        self.fatal_message = (
                            f"Injectarea click-urilor a eșuat. Rulează {APP_NAME} ca "
                            "Administrator (UIPI) și verifică antivirusul."
                        )
                        break
                    next_click = time.perf_counter() + 0.050
                    continue

                failures = 0
                time.sleep(CLICK_HOLD_SECONDS)
                if not send_left_up():
                    self.logger.error("[STATE] SendInput LEFT UP failed (error=%s)", _last_input_error)
                    reason = "SendInput LEFT UP failed"
                    self.fatal_message = (
                        f"Injectarea click-urilor a eșuat. Rulează {APP_NAME} ca "
                        "Administrator (UIPI) și verifică antivirusul."
                    )
                    break
                with self.state.lock:
                    self.state.synthetic_left_down = False

                jitter = random.uniform(-self.jitter, self.jitter)
                gap = max(0.001, self.interval + jitter)
                next_click = cycle_start + gap
                if next_click < time.perf_counter():
                    next_click = time.perf_counter() + 0.001
        finally:
            released = release_pending_left_up(self.state, self.logger)
            if not released:
                reason += " / final LEFTUP failed"
                if self.fatal_message is None:
                    self.fatal_message = (
                        "Butonul stâng al mouse-ului nu a putut fi eliberat. "
                        "Rulează ca Administrator și repornește aplicația."
                    )
            self.state.disarm(activation_id)
            if timer_resolution:
                try:
                    winmm.timeEndPeriod(1)
                except OSError:
                    pass
            self.logger.info("[STATE] STOPPED reason=%s", reason)
            if self.fatal_message is not None:
                self.state.fatal_message = self.fatal_message
                self.state.quit_event.set()


class MouseHook(threading.Thread):
    def __init__(
        self,
        state: SharedState,
        focus: FocusChecker,
        logger: Logger,
        config: dict,
    ) -> None:
        super().__init__(name="mouse-hook", daemon=True)
        self.state = state
        self.focus = focus
        self.logger = logger
        self.only_in_game = bool(config["only_in_game"])
        self.trigger_mode = config["trigger_mode"]
        self._ready = threading.Event()
        self._proc = HOOKPROC(self._callback)
        self._thread_id = None
        self._hook_handle = None
        self.error = None

    def start(self) -> None:
        global _hook_proc_ref
        _hook_proc_ref = self._proc
        super().start()

    def wait_ready(self, timeout: float = 2.0) -> bool:
        return self._ready.wait(timeout)

    def _call_next(self, n_code: int, w_param: int, l_param: int) -> int:
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _can_arm(self) -> bool:
        if self.state.quit_event.is_set() or not ctrl_is_down():
            return False
        if self.only_in_game and not self.focus.is_game_foreground(force=True):
            return False
        # Ctrl may have been released while the process lookup ran.
        return ctrl_is_down()

    def _on_left_down(self) -> bool:
        if self.trigger_mode == "intercept":
            with self.state.lock:
                already_down = self.state.physical_lmb or self.state.armed
            if already_down:
                return self.state.is_suppressed()
            if self._can_arm():
                activation_id = self.state.activate(suppress=True)
                if activation_id is not None:
                    self.logger.info(
                        "[STATE] ARMED id=%s mode=intercept game=%s",
                        activation_id,
                        self.focus.target if self.only_in_game else "any",
                    )
                    return True
            self.state.mark_physical_down()
            return False

        # Passthrough: the physical click always reaches the game; the worker
        # adds synthetic clicks on top of it.
        self.state.mark_physical_down()
        with self.state.lock:
            already_armed = self.state.armed
        if not already_armed and self._can_arm():
            activation_id = self.state.activate(suppress=False)
            if activation_id is not None:
                self.logger.info(
                    "[STATE] ARMED id=%s mode=passthrough game=%s",
                    activation_id,
                    self.focus.target if self.only_in_game else "any",
                )
        return False

    def _on_left_up(self) -> bool:
        was_suppressed = self.state.on_physical_up()
        return self.trigger_mode == "intercept" and was_suppressed

    def _handle_mouse_event(self, w_param: int, l_param: int) -> bool:
        info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        injected = info.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED)
        if injected or info.dwExtraInfo == INPUT_MAGIC:
            return False
        if w_param == WM_LBUTTONDOWN:
            return self._on_left_down()
        if w_param == WM_LBUTTONUP:
            return self._on_left_up()
        return False

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return self._call_next(n_code, w_param, l_param)
        try:
            if n_code == HC_ACTION and self._handle_mouse_event(w_param, l_param):
                return 1
        except Exception as exc:  # never let an exception break the hook chain
            self.logger.error("Mouse hook error: %s", exc)
        return self._call_next(n_code, w_param, l_param)

    def run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        module = kernel32.GetModuleHandleW(None)
        handle = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, module, 0)
        if not handle:
            self.error = ctypes.get_last_error()
            self.logger.error("[STATE] SetWindowsHookExW failed error=%s", self.error)
            self._ready.set()
            return
        self._hook_handle = handle
        self.logger.info("[STATE] HOOK installed")
        self._ready.set()

        message = wintypes.MSG()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if self._hook_handle:
                user32.UnhookWindowsHookEx(self._hook_handle)
                self._hook_handle = None
            self.logger.info("[STATE] HOOK removed")

    def stop(self) -> None:
        self._ready.wait(1.0)
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)


class HotkeyMonitor(threading.Thread):
    def __init__(self, state: SharedState, logger: Logger, hotkey_spec: str) -> None:
        super().__init__(name="hotkey-monitor", daemon=True)
        self.state = state
        self.logger = logger
        self.hotkey = parse_hotkey(hotkey_spec) or parse_hotkey(DEFAULT_CONFIG["exit_hotkey"])
        self.label = hotkey_spec

    def run(self) -> None:
        previous = False
        while not self.state.quit_event.is_set():
            active = hotkey_is_down(self.hotkey)
            if active and not previous:
                self.logger.info("[STATE] EXIT hotkey detected (%s)", self.label)
                self.state.quit_event.set()
                return
            previous = active
            self.state.quit_event.wait(HOTKEY_POLL_SECONDS)


class AutoClickerApp:
    def __init__(self, config: dict, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.state = SharedState()
        self.focus = FocusChecker(config["game_process"])
        self.worker = ClickWorker(self.state, self.focus, logger, config)
        self.hook = MouseHook(self.state, self.focus, logger, config)
        self.hotkey = HotkeyMonitor(self.state, logger, config["exit_hotkey"])
        self._cleanup_lock = threading.Lock()
        self._cleaned = False

    def run(self) -> None:
        self.logger.info(
            "[STATE] START mode=%s only_in_game=%s process=%s exit=%s",
            self.config["trigger_mode"],
            self.config["only_in_game"],
            self.config["game_process"],
            self.config["exit_hotkey"],
        )
        self.worker.start()
        self.hook.start()
        if not self.hook.wait_ready(2.0):
            raise RuntimeError("Thread-ul hooks nu a pornit în timp util.")
        if self.hook.error:
            raise RuntimeError(
                f"SetWindowsHookExW a eșuat (cod {self.hook.error}). "
                "Rulează ca Administrator dacă este necesar."
            )
        self.hotkey.start()
        self.logger.info("[STATE] RUNNING - hold Ctrl + LMB to click")
        try:
            while not self.state.quit_event.wait(0.2):
                pass
        except KeyboardInterrupt:
            self.logger.info("[STATE] Ctrl+C received")
            self.state.quit_event.set()
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        with self._cleanup_lock:
            if self._cleaned:
                return
            self._cleaned = True
        self.logger.info("[STATE] STOPPING")
        self.state.quit_event.set()
        self.hook.stop()
        self.worker.join(0.5)
        if self.worker.is_alive():
            self.logger.warn("Worker did not stop in time; forcing final LEFTUP.")
            release_pending_left_up(self.state, self.logger)
            self.worker.join(0.2)
        self.hook.join(0.5)
        self.hotkey.join(0.3)
        release_pending_left_up(self.state, self.logger)
        self.logger.info("[STATE] EXITED")


def _debug_enabled(config: dict) -> bool:
    if not getattr(sys, "frozen", False):
        return True
    if "debug" in os.path.basename(sys.executable).lower():
        return True
    if "--debug" in sys.argv:
        return True
    return bool(config["debug_log"])


def main() -> int:
    base_dir = application_dir()
    instance = SingleInstance()
    if not instance.acquire():
        if instance.already_running:
            show_message(
                f"{APP_NAME} rulează deja.\n\n"
                "Închide instanța existentă cu Ctrl+Alt+F8 înainte de a porni alta.",
                warning=True,
            )
        else:
            show_message(
                f"Nu am putut crea mutex-ul de instanță unică (cod {instance.error}).",
                error=True,
            )
        return 2

    logger = None
    app = None
    exit_code = 0
    try:
        config, warnings = load_config(os.path.join(base_dir, CONFIG_FILENAME))
        logger = Logger(_debug_enabled(config), base_dir)
        logger.info("[STATE] %s starting (dir=%s)", APP_NAME, base_dir)
        logger.info(
            "[STATE] config interval=%sms jitter=%sms only_in_game=%s trigger=%s game=%s hotkey=%s",
            config["interval_ms"],
            config["jitter_ms"],
            config["only_in_game"],
            config["trigger_mode"],
            config["game_process"],
            config["exit_hotkey"],
        )
        for warning in warnings:
            logger.warn(warning)
        if warnings and not logger.console_available:
            show_message(
                "Unele valori din config.json sunt invalide; se folosesc valorile implicite:\n\n"
                + "\n".join(warnings),
                warning=True,
            )

        app = AutoClickerApp(config, logger)
        atexit.register(app.cleanup)
        app.run()
    except Exception as exc:
        if logger is not None:
            logger.error("Fatal error: %s", exc)
        else:
            try:
                print(f"Fatal error: {exc}", file=sys.stderr)
            except (AttributeError, OSError):
                pass
        show_message(f"{APP_NAME} s-a oprit din cauza unei erori:\n\n{exc}", error=True)
        exit_code = 1
    finally:
        if app is not None:
            app.cleanup()
        instance.release()
        if logger is not None:
            logger.close()

    if (
        exit_code == 0
        and app is not None
        and app.state.fatal_message
        and (logger is None or not logger.console_available)
    ):
        show_message(app.state.fatal_message, error=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
