"""Drives the real OpenVPN for Windows (openvpn.exe). Mirrors the Android VpnManager."""
import os
import shutil
import socket
import subprocess
import threading
import time
from typing import List, Optional, Tuple

import core

DISCONNECTED, CONNECTING, CONNECTED, FAILED = "DISCONNECTED", "CONNECTING", "CONNECTED", "FAILED"

MAX_ATTEMPTS = 3
CONNECT_TIMEOUT = 35.0
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_openvpn() -> Optional[str]:
    env = os.environ.get("MOONLIGHT_OPENVPN")
    if env and os.path.exists(env):
        return env
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        root = os.environ.get(var)
        if root:
            p = os.path.join(root, "OpenVPN", "bin", "openvpn.exe")
            if os.path.exists(p):
                return p
    return shutil.which("openvpn")


def install_openvpn_with_winget() -> Tuple[bool, str]:
    """Installs OpenVPN for Windows (the engine) using winget. Needs internet once."""
    try:
        r = subprocess.run(
            ["winget", "install", "-e", "--id", "OpenVPNTechnologies.OpenVPN", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=900)
        ok = r.returncode == 0 and find_openvpn() is not None
        return ok, (r.stdout + r.stderr).strip()[-400:]
    except Exception as e:  # winget missing, timeout ...
        return False, str(e)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Engine:
    def __init__(self) -> None:
        self.state = DISCONNECTED
        self.label = ""
        self.current: Optional[core.VpnServer] = None
        self.connected_at: Optional[float] = None
        self.error = ""
        self.version = 0          # bumped on every change; the UI polls it
        self._gen = 0
        self._proc: Optional[subprocess.Popen] = None
        self._mgmt_port = 0
        self._killers: List[threading.Thread] = []

    # ------------------------------------------------------------ public API

    def connect(self, label: str, pool: List[core.VpnServer], fastest: bool = True) -> None:
        self._release_process()
        self._gen += 1
        gen = self._gen
        self.label, self.current, self.connected_at, self.error = label, None, None, ""
        self._set(CONNECTING)
        threading.Thread(target=self._run, args=(gen, pool, fastest), daemon=True).start()

    def disconnect(self) -> None:
        self._gen += 1
        self._release_process()
        self.connected_at = None
        self._set(DISCONNECTED)

    def shutdown(self) -> None:
        """Disconnect and wait (max ~8 s) until openvpn.exe has really exited."""
        self.disconnect()
        for t in list(self._killers):
            t.join(8)

    # ------------------------------------------------------------ internals

    def _set(self, state: str) -> None:
        self.state = state
        self.version += 1

    def _release_process(self) -> None:
        proc, port = self._proc, self._mgmt_port
        self._proc = None
        if proc is not None and proc.poll() is None:
            t = threading.Thread(target=self._kill, args=(proc, port), daemon=True)
            self._killers.append(t)
            t.start()

    @staticmethod
    def _kill(proc: subprocess.Popen, port: int) -> None:
        try:  # graceful: lets OpenVPN remove its routes and adapter
            with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
                s.sendall(b"signal SIGTERM\n")
        except OSError:
            pass
        try:
            proc.wait(6)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _run(self, gen: int, pool: List[core.VpnServer], fastest: bool) -> None:
        exe = find_openvpn()
        if not exe:
            self.error = "OpenVPN is not installed."
            self._set(FAILED)
            return
        for t in list(self._killers):  # previous tunnel must be gone first
            t.join(8)
        if len(pool) > 1:
            ordered = core.fastest_first(pool) if fastest else core.random_order(pool)
        else:
            ordered = list(pool)
        if gen != self._gen:
            return
        for server in ordered[:MAX_ATTEMPTS]:
            if gen != self._gen:
                return
            if self._try_server(gen, exe, server):
                return
        if gen == self._gen:
            self.error = "No server answered."
            self._set(FAILED)

    def _try_server(self, gen: int, exe: str, server: core.VpnServer) -> bool:
        """Returns True when the session is finished (connected-then-ended, or cancelled)."""
        run_dir = os.path.join(core.data_dir(), "run")
        os.makedirs(run_dir, exist_ok=True)
        cfg_path = os.path.join(run_dir, "current.ovpn")
        with open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(core.prepare_config(core.read_config(server)))
            if _wants_auth(server):
                # later option wins: feed the public login so OpenVPN never prompts
                f.write('\nauth-user-pass "' + _auth_file(run_dir).replace("\\", "/") + '"\n')
        self._mgmt_port = _free_port()
        args = [exe, "--config", cfg_path, "--management", "127.0.0.1", str(self._mgmt_port),
                "--verb", "3"]
        self.current = server
        self._set(CONNECTING)
        try:
            proc = subprocess.Popen(args, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True, bufsize=1, errors="replace",
                                    creationflags=NO_WINDOW)
        except OSError as e:
            self.error = str(e)
            return False
        self._proc = proc
        started = time.time()
        connected = [False]

        def watchdog() -> None:
            while proc.poll() is None and gen == self._gen:
                if not connected[0] and time.time() - started > CONNECT_TIMEOUT:
                    proc.kill()  # this server did not answer, move on
                    return
                time.sleep(0.5)

        threading.Thread(target=watchdog, daemon=True).start()
        assert proc.stdout is not None
        for line in proc.stdout:
            if gen != self._gen:
                break
            if "Initialization Sequence Completed" in line:
                connected[0] = True
                self.connected_at = time.time()
                self._set(CONNECTED)
            elif "AUTH_FAILED" in line or "Exiting due to fatal error" in line:
                break
        if proc.poll() is None:
            self._kill(proc, self._mgmt_port)
        proc.wait()
        if gen != self._gen:
            return True
        if connected[0]:  # the tunnel was up and then dropped
            self.connected_at = None
            self._set(DISCONNECTED)
            return True
        return False


def _wants_auth(server: core.VpnServer) -> bool:
    try:
        return "auth-user-pass" in core.read_config(server).replace("auth-user-pass-verify", "")
    except OSError:
        return False


def _auth_file(run_dir: str) -> str:
    """Community (VPN Gate style) servers use the public login vpn / vpn."""
    path = os.path.join(run_dir, "auth.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("vpn\nvpn\n")
    return path
