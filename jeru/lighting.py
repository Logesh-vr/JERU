"""Lenovo white keyboard backlight, with reversible listening indication.

Only documented white-light interfaces are used. No Fn-key simulation, fan,
power, firmware, or RGB ownership changes. Hardware reference links are in README.
"""
from __future__ import annotations

import ctypes
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from multiprocessing.connection import Client, Listener
from pathlib import Path

from .config import app_root


class LenovoLighting:
    def __init__(self):
        self.instance = None
        self.driver = None
        self.backend = ""

    def connect(self) -> int:
        # Modern dedicated keyboard lighting interface first.
        try:
            import win32com.client
            service = win32com.client.GetObject(r"winmgmts:{impersonationLevel=impersonate}!\\.\root\WMI")
            instances = list(service.ExecQuery("SELECT * FROM LENOVO_LIGHTING_METHOD"))
            if not instances:
                raise OSError("Lenovo lighting interface is not available")
            self.instance = instances[0]
            self.backend = "Lenovo lighting WMI"
            return self.get()
        except Exception as wmi_error:
            self.instance = None
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            handle = kernel.CreateFileW(r"\\.\EnergyDrv", 3, 3, None, 3, 0x80, None)
            if handle in {None, ctypes.c_void_p(-1).value}:
                raise PermissionError("Lenovo backlight access is unavailable. Enable the optional keyboard-light helper in Settings.") from wmi_error
            self.driver = handle
            self.backend = "Lenovo Energy driver"
            try:
                if self._ioctl(0x1) >> 1 != 2:
                    raise OSError("This keyboard does not expose the supported white backlight")
                return self.get()
            except Exception:
                self.close()
                raise

    def _wmi(self, method: str, **values):
        inputs = self.instance.Methods_(method).InParameters.SpawnInstance_()
        for name, value in values.items():
            inputs.Properties_(name).Value = value
        return self.instance.ExecMethod_(method, inputs)

    def _ioctl(self, value: int) -> int:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        source, result, returned = ctypes.c_uint32(value), ctypes.c_uint32(), wintypes.DWORD()
        if not kernel.DeviceIoControl(self.driver, 0x83102144, ctypes.byref(source), 4, ctypes.byref(result), 4, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return result.value

    def get(self) -> int:
        if self.instance:
            result = self._wmi("Get_Lighting_Current_Status", Lighting_ID=0)
            state = int(result.Properties_("Current_State_Type").Value)
            level = int(result.Properties_("Current_Brightness_Level").Value)
            if state != 0 or level not in {1, 2, 3}:
                raise OSError("Unsupported Lenovo lighting mode; no settings were changed")
            return level - 1
        if self.driver:
            value = self._ioctl(0x22)
            if value not in {1, 3, 5}:
                raise OSError("Unknown Lenovo keyboard brightness")
            return {1: 0, 3: 1, 5: 2}[value]
        raise OSError("Keyboard light is not connected")

    def set(self, level: int) -> None:
        if type(level) is not int or level not in {0, 1, 2}:
            raise ValueError("Keyboard brightness must be 0, 1, or 2")
        if self.instance:
            self._wmi("Set_Lighting_Current_Status", Lighting_ID=0, Current_State_Type=0, Current_Brightness_Level=level + 1)
        elif self.driver:
            self._ioctl({0: 0x23, 1: 0x10023, 2: 0x20023}[level])
        else:
            raise OSError("Keyboard light is not connected")
        if self.get() != level:
            raise OSError("Keyboard did not confirm the requested brightness")

    def close(self):
        if self.driver:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(self.driver)
            self.driver = None
        self.instance = None


class Indicator:
    """Captures before changing and restores after listening, including failures."""
    def __init__(self, backend):
        self.backend = backend
        self.previous: int | None = None

    def listening(self, enabled: bool, level: int = 2):
        if enabled:
            if self.previous is None:
                self.previous = self.backend.get()
            try:
                self.backend.set(level)
            except Exception:
                self.restore()
                raise
        else:
            self.restore()

    def restore(self):
        if self.previous is not None:
            original = self.previous
            self.backend.set(original)
            self.previous = None


class LightingController(threading.Thread):
    def __init__(self, on_status):
        super().__init__(daemon=True, name="jeru-keyboard-light")
        self.on_status = on_status
        self.messages = queue.Queue()
        self._helper = None
        self.start()

    def listening(self, enabled: bool, level: int = 2):
        self.messages.put(("listen", enabled, level))

    def enable_helper(self):
        self.messages.put(("helper", False, 2))

    def stop(self):
        self.messages.put(("quit", False, 2))

    def _start_helper(self):
        name, secret = "jeru-light-" + secrets.token_hex(16), secrets.token_hex(32)
        pipe = "\\\\.\\pipe\\" + name
        exe = sys.executable
        args = ["--light-helper", name, secret, str(os.getpid())]
        if not getattr(sys, "frozen", False):
            exe = str(Path(exe).with_name("pythonw.exe"))
            args = ["-m", "jeru", *args]
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, subprocess.list2cmdline(args), str(app_root()), 0)
        if result <= 32:
            raise PermissionError("Keyboard helper permission was not granted")
        self.on_status("Waiting for Windows permission for keyboard lighting…")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                self._helper = Client(pipe, family="AF_PIPE", authkey=bytes.fromhex(secret))
                self._helper.send_bytes(b'{"command":"status"}')
                if not self._helper.poll(5):
                    raise TimeoutError("Keyboard helper did not respond")
                response = json.loads(self._helper.recv_bytes(4096))
                if not response.get("ok"):
                    raise OSError(response.get("message", "Keyboard unsupported"))
                self.on_status("Keyboard light ready · privileged helper")
                return
            except FileNotFoundError:
                time.sleep(0.2)
        raise TimeoutError("Keyboard helper was not started. You can try again in Settings.")

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        backend, indicator, tried = LenovoLighting(), None, False
        try:
            while True:
                try:
                    command, enabled, level = self.messages.get(timeout=20)
                except queue.Empty:
                    if self._helper:
                        try:
                            self._helper.send_bytes(b'{"command":"status"}')
                            if self._helper.poll(3):
                                self._helper.recv_bytes(4096)
                        except (OSError, EOFError):
                            self._helper.close()
                            self._helper = None
                    continue
                try:
                    if command == "helper":
                        if indicator:
                            indicator.restore()
                        if self._helper:
                            self._helper.send_bytes(b'{"command":"quit"}')
                            self._helper.close()
                            self._helper = None
                        self._start_helper()
                        continue
                    if self._helper:
                        self._helper.send_bytes(json.dumps({"command": "quit" if command == "quit" else "on" if enabled else "off", "level": level}).encode())
                        if not self._helper.poll(5):
                            raise TimeoutError("Keyboard helper timed out")
                        response = json.loads(self._helper.recv_bytes(4096))
                        if not response.get("ok"):
                            raise OSError(response.get("message", "Keyboard control failed"))
                        self.on_status("Keyboard light on · listening" if enabled else "Keyboard brightness restored")
                    elif command != "quit":
                        if not tried:
                            tried = True
                            backend.connect()
                            indicator = Indicator(backend)
                            self.on_status("Keyboard light ready · " + backend.backend)
                        if indicator:
                            indicator.listening(enabled, level)
                            self.on_status("Keyboard light on · listening" if enabled else "Keyboard brightness restored")
                    if command == "quit":
                        break
                except Exception as exc:
                    self.on_status(str(exc))
                    if self._helper:
                        self._helper.close()
                        self._helper = None
                    if command == "quit":
                        break
        finally:
            if indicator:
                try:
                    indicator.restore()
                except Exception as exc:
                    self.on_status("Could not restore keyboard brightness: " + str(exc))
            backend.close()
            pythoncom.CoUninitialize()


def helper_main(name: str, secret: str, parent_pid: int):
    """Optional elevated companion. Only status/on/off/quit are accepted."""
    import pythoncom
    import psutil
    import re
    if not re.fullmatch(r"jeru-light-[a-f0-9]{32}", name) or not re.fullmatch(r"[a-f0-9]{64}", secret):
        raise ValueError("Invalid helper arguments")
    parent = psutil.Process(parent_pid)
    started = parent.create_time()
    pythoncom.CoInitialize()
    backend = LenovoLighting()
    indicator = Indicator(backend)
    shutdown = threading.Event()
    last_request = [time.monotonic()]

    def watchdog():
        while not shutdown.wait(1):
            alive = False
            try:
                alive = parent.is_running() and parent.create_time() == started
            except psutil.Error:
                pass
            # If the parent dies, hardware restoration happens in this COM thread.
            if not alive or time.monotonic() - last_request[0] > 90:
                pythoncom.CoInitialize()
                try:
                    emergency = LenovoLighting()
                    emergency.connect()
                    if indicator.previous is not None:
                        emergency.set(indicator.previous)
                    emergency.close()
                except Exception:
                    pass
                finally:
                    os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        error = None
        try:
            backend.connect()
        except Exception as exc:
            error = str(exc)
        with Listener("\\\\.\\pipe\\" + name, family="AF_PIPE", authkey=bytes.fromhex(secret)) as listener:
            with listener.accept() as connection:
                while True:
                    if not connection.poll(1):
                        continue
                    last_request[0] = time.monotonic()
                    request = json.loads(connection.recv_bytes(4096))
                    command = request.get("command")
                    try:
                        if error:
                            raise OSError(error)
                        if command == "on":
                            indicator.listening(True, request.get("level", 2))
                        elif command in {"off", "quit"}:
                            indicator.restore()
                        elif command != "status":
                            raise ValueError("Unsupported light command")
                        connection.send_bytes(json.dumps({"ok": True, "level": backend.get()}).encode())
                    except Exception as exc:
                        connection.send_bytes(json.dumps({"ok": False, "message": str(exc)[:300]}).encode())
                    if command == "quit" or error:
                        break
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        shutdown.set()
        try:
            indicator.restore()
        finally:
            backend.close()
            pythoncom.CoUninitialize()
