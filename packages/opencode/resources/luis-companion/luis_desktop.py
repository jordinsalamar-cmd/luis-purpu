import argparse
import ctypes
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import webbrowser
import winreg
from pathlib import Path


if os.name != "nt":
    raise RuntimeError("La herramienta desktop de Luis solo está disponible en Windows.")


user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120
APP_EXTENSIONS = {".exe", ".lnk", ".url", ".bat", ".cmd"}
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def plain_name(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def app_roots():
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    roaming = Path(os.environ.get("APPDATA", local / "Roaming"))
    program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
    return [
        roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop",
        local / "Programs",
        program_files,
        program_files_x86,
    ]


def discover_apps(query=None):
    entries = {}

    def add_entry(name, path, kind):
        key = f"{kind}:{path}".lower()
        if key not in entries:
            entries[key] = {"name": str(name), "path": str(path), "kind": kind}

    def add(path):
        path = Path(path)
        if path.suffix.lower() not in APP_EXTENSIONS or not path.exists():
            return
        add_entry(path.stem, path, path.suffix.lower()[1:])

    def registry_executable(values):
        """Resolve a registered application's launchable executable, if it has one."""
        for value in values:
            raw = os.path.expandvars(str(value or "")).strip()
            if not raw:
                continue
            quoted = re.match(r'^"([^"]+)"', raw)
            candidate_text = quoted.group(1) if quoted else raw.split(",", 1)[0].split(" /", 1)[0].strip()
            candidate = Path(candidate_text)
            if candidate.is_file() and candidate.suffix.lower() == ".exe":
                return candidate
            if candidate.is_dir():
                try:
                    for child in sorted(candidate.glob("*.exe")):
                        if child.is_file():
                            return child
                except OSError:
                    pass
        return None

    for item in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(item.strip('"'))
        if directory.exists():
            for path in directory.glob("*.exe"):
                add(path)

    for root in app_roots():
        if not root.exists():
            continue
        try:
            for current, directories, files in os.walk(root):
                depth = len(Path(current).relative_to(root).parts)
                if depth >= 4:
                    directories[:] = []
                for filename in files:
                    if Path(filename).suffix.lower() in APP_EXTENSIONS:
                        add(Path(current) / filename)
        except (OSError, ValueError):
            continue

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for uninstall_key in (
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ):
            try:
                with winreg.OpenKey(hive, uninstall_key) as root_key:
                    for index in range(winreg.QueryInfoKey(root_key)[0]):
                        try:
                            sub_name = winreg.EnumKey(root_key, index)
                            with winreg.OpenKey(root_key, sub_name) as app_key:
                                display_name = winreg.QueryValueEx(app_key, "DisplayName")[0]
                                launch_values = []
                                for value_name in ("DisplayIcon", "InstallLocation"):
                                    try:
                                        launch_values.append(winreg.QueryValueEx(app_key, value_name)[0])
                                    except OSError:
                                        continue
                                executable = registry_executable(launch_values)
                                if display_name and executable:
                                    add_entry(display_name, executable, "exe")
                        except (OSError, TypeError):
                            continue
            except OSError:
                continue

    try:
        powershell = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False,
        )
        start_apps = json.loads(powershell.stdout or "[]")
        if isinstance(start_apps, dict):
            start_apps = [start_apps]
        for app in start_apps:
            if app.get("Name") and app.get("AppID"):
                add_entry(app["Name"], app["AppID"], "appx")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass

    result = list(entries.values())
    if query:
        needle = plain_name(query)
        ranked = []
        for entry in result:
            name = plain_name(entry["name"])
            score = 0
            if name == needle:
                score = 100
            elif needle and needle in name:
                score = 80
            else:
                score = int(difflib.SequenceMatcher(None, needle, name).ratio() * 60)
            if score >= 45:
                ranked.append((score, entry))
        result = [entry for _, entry in sorted(ranked, key=lambda item: (-item[0], item[1]["name"].lower()))]
    return sorted(result, key=lambda item: item["name"].lower())


def open_application(target):
    target = str(target or "").strip()
    if not target:
        raise ValueError("Falta el nombre de la aplicación")
    if target.startswith(("http://", "https://")):
        webbrowser.open(target, new=0)
        return {"name": target, "path": target, "kind": "url"}
    direct = Path(target).expanduser()
    if direct.exists():
        selected = {"name": direct.stem, "path": str(direct), "kind": direct.suffix.lower()[1:]}
    else:
        matches = discover_apps(target)
        if not matches:
            raise ValueError(f"No encontré una aplicación llamada '{target}'. Usa app_list para consultar las disponibles.")
        selected = matches[0]
    detached = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if selected["kind"] == "appx":
        app_uri = f"shell:AppsFolder\\{selected['path']}"
        try:
            # ShellExecute hands the Store app directly to Windows, so its lifetime
            # is independent from the short-lived desktop helper process.
            os.startfile(app_uri)
        except OSError:
            subprocess.Popen(
                ["explorer.exe", app_uri],
                creationflags=detached | getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
    elif selected["kind"] in {"lnk", "url", "bat", "cmd", "registry"}:
        os.startfile(selected["path"])
    else:
        subprocess.Popen(
            [selected["path"]],
            cwd=str(Path(selected["path"]).parent),
            creationflags=detached | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    return selected


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUTUNION)]


VK = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "escape": 0x1B,
    "space": 0x20,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def result(action, **extra):
    print(json.dumps({"ok": True, "action": action, **extra}, ensure_ascii=False))


def key_code(value):
    name = str(value or "").strip().lower()
    if len(name) == 1:
        return ord(name.upper())
    if name.startswith("key_") and len(name) == 5:
        return ord(name[-1].upper())
    if name in VK:
        return VK[name]
    raise ValueError(f"Tecla no reconocida: {value}")


def key_event(code, flags=0):
    user32.keybd_event(code, 0, flags, 0)


def press(value, modifiers=None):
    raw = str(value or "").replace(" ", "")
    pieces = [piece for piece in raw.replace("+", "+").split("+") if piece]
    if not pieces:
        raise ValueError("Falta la tecla")
    modifiers = list(modifiers or []) + pieces[:-1]
    modifier_codes = [key_code(item) for item in modifiers]
    code = key_code(pieces[-1])
    for item in modifier_codes:
        key_event(item)
    key_event(code)
    key_event(code, KEYEVENTF_KEYUP)
    for item in reversed(modifier_codes):
        key_event(item, KEYEVENTF_KEYUP)


def type_text(value):
    for char in str(value or ""):
        if char == "\n":
            press("enter")
            continue
        scan = ord(char)
        down = INPUT(type=1, ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, None))
        up = INPUT(type=1, ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))
        user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))


def paste_text(value):
    text = str(value or "")
    encoded = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not handle:
        raise OSError("No se pudo reservar memoria para el portapapeles")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise OSError("No se pudo preparar el portapapeles")
    try:
        ctypes.memmove(pointer, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise OSError("No se pudo abrir el portapapeles")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise OSError("No se pudo copiar el texto al portapapeles")
        handle = None
    finally:
        user32.CloseClipboard()
    press("ctrl+v")


def click(x, y, button="left", count=1):
    user32.SetCursorPos(int(x), int(y))
    events = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }
    if button not in events:
        raise ValueError(f"Botón no reconocido: {button}")
    down, up = events[button]
    for _ in range(max(1, int(count))):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        if count > 1:
            time.sleep(0.05)


def screenshot():
    from PIL import ImageGrab

    path = Path(tempfile.gettempdir()) / f"luis-desktop-{os.getpid()}-{int(time.time() * 1000)}.png"
    image = ImageGrab.grab(all_screens=True)
    image.save(path, "PNG")
    return str(path)


def latest_vision():
    source = Path(tempfile.gettempdir()) / "luis-vision-latest.png"
    if source.exists():
        path = Path(tempfile.gettempdir()) / f"luis-vision-request-{os.getpid()}-{int(time.time() * 1000)}.png"
        try:
            shutil.copyfile(source, path)
            return str(path)
        except OSError:
            pass
    return screenshot()


def windows():
    entries = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if title:
            entries.append({"hwnd": int(hwnd), "title": title})
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return entries


def focus(title):
    needle = str(title or "").lower()
    candidates = windows()
    ranked = sorted(
        (entry for entry in candidates if needle in entry["title"].lower()),
        key=lambda entry: (entry["title"].lower() != needle, len(entry["title"])),
    )
    if ranked:
        entry = ranked[0]
        user32.ShowWindow(entry["hwnd"], 5)
        user32.SetForegroundWindow(entry["hwnd"])
        return entry
    raise ValueError(f"No encontré una ventana con: {title}")


def wait_for_window(title, timeout=8.0):
    needle = plain_name(title)
    deadline = time.time() + max(0.0, float(timeout))
    current = windows()
    while time.time() < deadline:
        for entry in current:
            if needle and needle in plain_name(entry["title"]):
                return current
        time.sleep(0.25)
        current = windows()
    return current


def run(request):
    action = str(request.get("action") or "").lower()
    if action == "app_list":
        return {"applications": discover_apps(request.get("target"))}
    if action == "open_app":
        selected = open_application(request.get("target"))
        current = wait_for_window(selected["name"], request.get("wait", 8.0))
        return {"application": selected, "windows": current}
    if action == "screenshot":
        return {"screenshot": screenshot()}
    if action == "vision":
        return {"screenshot": latest_vision()}
    if action == "window_list":
        return {"windows": windows()}
    if action == "focus":
        return {"window": focus(request.get("target"))}
    if action == "paste":
        paste_text(request.get("text"))
        return {"pasted": True}
    if action == "open":
        target = str(request.get("target") or "").strip()
        if not target:
            raise ValueError("Falta target para abrir")
        if target.startswith(("http://", "https://")):
            webbrowser.open(target, new=0)
        else:
            os.startfile(target)
        time.sleep(0.8)
    elif action == "move":
        user32.SetCursorPos(int(request["x"]), int(request["y"]))
    elif action in {"click", "double_click"}:
        click(request["x"], request["y"], request.get("button", "left"), 2 if action == "double_click" else 1)
    elif action == "type":
        type_text(request.get("text", ""))
    elif action == "key":
        press(request.get("key"), request.get("modifiers"))
    elif action == "scroll":
        amount = int(request.get("amount", 0))
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, amount * WHEEL_DELTA, 0)
    else:
        raise ValueError(f"Acción desktop no reconocida: {action}")

    time.sleep(float(request.get("wait", 0.4)))
    return {"screenshot": screenshot()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request)
        payload = run(request)
        result(request.get("action", ""), **payload)
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
