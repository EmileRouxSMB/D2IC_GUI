"""Tests for the standalone CPU GUI launcher."""

import os
import subprocess
import socket
import sys
from pathlib import Path
import types


def _desktop_module():
    import importlib
    sys.modules.pop("D2IC_GUI.desktop", None)
    return importlib.import_module("D2IC_GUI.desktop")


def test_cpu_environment_is_set_on_import():
    previous = {key: os.environ.get(key) for key in ("JAX_PLATFORMS", "JAX_PLATFORM_NAME")}
    try:
        os.environ["JAX_PLATFORMS"] = "cuda"
        os.environ["JAX_PLATFORM_NAME"] = "cuda"
        env = os.environ.copy()
        check = subprocess.run(
            [sys.executable, "-c", "import os, sys; import D2IC_GUI.desktop; "
             "assert os.environ['JAX_PLATFORMS'] == 'cpu'; "
             "assert os.environ['JAX_PLATFORM_NAME'] == 'cpu'; assert 'jax' not in sys.modules"],
            cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True,
        )
        assert check.returncode == 0, check.stderr
        desktop = _desktop_module()
        assert os.environ["JAX_PLATFORMS"] == "cpu"
        assert os.environ["JAX_PLATFORM_NAME"] == "cpu"
        args = desktop._arguments(["study", "--port", "8123", "--no-browser"])
        assert (args.study_folder, args.port, args.no_browser) == ("study", 8123, True)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.modules.pop("D2IC_GUI.desktop", None)


def test_port_zero_binds_an_available_loopback_port():
    desktop = _desktop_module()
    sock = desktop._bind_loopback(0)
    try:
        assert sock.getsockname()[0] == "127.0.0.1"
        assert sock.getsockname()[1] > 0
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
    finally:
        sock.close()


def test_main_passes_the_bound_socket_and_study_folder(monkeypatch, capsys):
    import types
    desktop = _desktop_module()
    captured = {}

    class FakeConfig:
        def __init__(self, app, **kwargs):
            captured["app"] = app
            captured["config"] = kwargs

    class FakeServer:
        def __init__(self, config):
            captured["server_config"] = config

        def run(self, sockets):
            captured["sockets"] = sockets

    fake_uvicorn = types.SimpleNamespace(Config=FakeConfig, Server=FakeServer)
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    app = object()
    def create_app(folder):
        captured["folder"] = folder
        return app
    monkeypatch.setattr("D2IC_GUI.server.create_app", create_app)
    monkeypatch.setattr(desktop, "_bind_loopback", lambda port: _fake_bound_socket())
    desktop.main(["/tmp/study", "--no-browser"])
    assert captured["folder"] == "/tmp/study"
    assert captured["config"]["port"] == 54321
    assert captured["sockets"][0].getsockname()[1] == 54321
    assert "127.0.0.1:54321" in capsys.readouterr().out


def _fake_bound_socket():
    class FakeSocket:
        closed = False

        def getsockname(self):
            return "127.0.0.1", 54321

        def close(self):
            self.closed = True

    return FakeSocket()


def test_browser_opens_only_after_readiness(monkeypatch):
    import threading
    desktop = _desktop_module()
    events = []
    attempts = iter((OSError("not ready"), None))

    def response(url, timeout):
        event = next(attempts)
        if event:
            raise event
        return _Response()

    monkeypatch.setattr(desktop.urllib.request, "urlopen", response)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: events.append(url))
    stopped = threading.Event()
    desktop._open_browser_when_ready("http://127.0.0.1:4321/", stopped, timeout=1)
    assert events == ["http://127.0.0.1:4321/"]


def test_windows_worker_liveness_queries_exit_code_and_closes_handle(monkeypatch):
    import ctypes
    import ctypes.wintypes as wintypes
    import D2IC_GUI.dic_run as dic_run

    calls = []

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    kernel32 = types.SimpleNamespace(
        OpenProcess=Function(lambda access, inherit, pid: calls.append(("open", pid)) or 17),
        GetExitCodeProcess=Function(lambda handle, pointer: setattr(
            ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents, "value", 259) or 1),
        CloseHandle=Function(lambda handle: calls.append(("close", handle)) or 1),
    )
    monkeypatch.setattr(dic_run, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel32, raising=False)
    assert dic_run.worker_alive(42)
    assert calls == [("open", 42), ("close", 17)]


def test_windows_worker_stop_uses_taskkill_tree(monkeypatch):
    import D2IC_GUI.dic_run as dic_run
    captured = {}
    monkeypatch.setattr(dic_run, "os", types.SimpleNamespace(name="nt"))
    def run(argv, **kwargs):
        captured["argv"] = argv
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(dic_run.subprocess, "run", run)
    assert dic_run.stop_worker(42)
    assert captured["argv"] == ["taskkill", "/PID", "42", "/T", "/F"]


def test_finished_posix_child_is_reaped_without_proc(monkeypatch):
    import D2IC_GUI.dic_run as dic_run
    calls = []
    monkeypatch.setattr(dic_run, 'os', types.SimpleNamespace(
        name='posix', WNOHANG=1, kill=lambda pid, sig: None,
        waitpid=lambda pid, flags: calls.append((pid, flags)) or (pid, 0)))
    assert not dic_run.worker_alive(42)
    assert calls == [(42, 1)]


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
