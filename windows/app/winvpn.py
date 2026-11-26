"""Windows VPN-list integration ("Moonlight VPN" in Settings > Network > VPN and the Quick Settings VPN tile).

How it works (be honest about the limits):
  * We add a normal Windows VPN entry called "Moonlight VPN" (a placeholder profile).
  * A scheduled task watches the Windows RasClient log. When you press Connect on that entry, Windows logs
    an event naming the connection; the task then starts Moonlight VPN, which connects a random server.
  * Windows itself still thinks its placeholder entry failed to connect - only the real OpenVPN tunnel,
    started by Moonlight VPN, protects you. Showing a genuine "Connected" state there would require a
    Microsoft Store VPN plug-in app, which is a separate project.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Tuple

PROFILE_NAME = "Moonlight VPN"
TASK_TRAY = "MoonlightVPN-Tray"
TASK_EVENT = "MoonlightVPN-WindowsVpnButton"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(args, timeout=60) -> Tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def _ps(script: str) -> Tuple[int, str]:
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])


def exe_path() -> str:
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])


# ------------------------------------------------------------------ the VPN-list entry

def add_profile() -> Tuple[bool, str]:
    code, out = _ps(
        f"$n='{PROFILE_NAME}'; "
        "if (-not (Get-VpnConnection -Name $n -ErrorAction SilentlyContinue)) { "
        "Add-VpnConnection -Name $n -ServerAddress '127.0.0.1' -TunnelType Ikev2 "
        "-AuthenticationMethod MachineCertificate -EncryptionLevel Required -Force }")
    return code == 0, out


def remove_profile() -> Tuple[bool, str]:
    code, out = _ps(f"Remove-VpnConnection -Name '{PROFILE_NAME}' -Force -ErrorAction SilentlyContinue")
    return code == 0, out

# ------------------------------------------------------------------ scheduled tasks

def _task_xml(trigger_xml: str, arguments: str, parallel: bool) -> str:
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    policy = "Parallel" if parallel else "IgnoreNew"
    exe = exe_path().replace("&", "&amp;")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>{trigger_xml.replace('@@USER@@', user)}</Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>{policy}</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{exe}</Command><Arguments>{arguments}</Arguments></Exec>
  </Actions>
</Task>
"""


_LOGON = "<LogonTrigger><Enabled>true</Enabled><UserId>@@USER@@</UserId></LogonTrigger>"
_RAS_EVENT = (
    "<EventTrigger><Enabled>true</Enabled><Subscription>"
    "&lt;QueryList&gt;&lt;Query Id=\"0\" Path=\"System\"&gt;"
    "&lt;Select Path=\"System\"&gt;*[System[Provider[@Name='RasClient']]]&lt;/Select&gt;"
    "&lt;/Query&gt;&lt;/QueryList&gt;</Subscription></EventTrigger>")


def _create_task(name: str, xml: str) -> Tuple[bool, str]:
    path = os.path.join(tempfile.gettempdir(), f"{name}.xml")
    with open(path, "w", encoding="utf-16") as f:
        f.write(xml)
    code, out = _run(["schtasks", "/Create", "/TN", name, "/XML", path, "/F"])
    try:
        os.remove(path)
    except OSError:
        pass
    return code == 0, out


def install_integration() -> Tuple[bool, str]:
    """Adds the 'Moonlight VPN' entry to the Windows VPN list + the two scheduled tasks."""
    msgs, ok_all = [], True
    for step, result in (
        ("VPN entry", add_profile()),
        ("start-with-Windows task", _create_task(TASK_TRAY, _task_xml(_LOGON, "--tray", False))),
        ("Windows VPN button task", _create_task(TASK_EVENT, _task_xml(_RAS_EVENT, "--ras-event", True))),
    ):
        ok, out = result
        ok_all &= ok
        msgs.append(f"{step}: {'OK' if ok else 'FAILED ' + out[:160]}")
    return ok_all, "\n".join(msgs)


def remove_integration() -> Tuple[bool, str]:
    _run(["schtasks", "/Delete", "/TN", TASK_TRAY, "/F"])
    _run(["schtasks", "/Delete", "/TN", TASK_EVENT, "/F"])
    return remove_profile()

# ------------------------------------------------------------------ "was Connect pressed in Windows?"

def recent_ras_event(max_age_seconds: int = 45, retries: int = 3) -> bool:
    """True if Windows logged a RasClient event for the 'Moonlight VPN' entry in the last seconds."""
    for attempt in range(retries):
        code, out = _run(["wevtutil", "qe", "System", "/q:*[System[Provider[@Name='RasClient']]]",
                          "/c:20", "/rd:true", "/f:xml"], timeout=20)
        if code == 0 and _has_recent(out, max_age_seconds):
            return True
        time.sleep(1.5)  # the event can land a moment after the task fires
    return False


def _has_recent(xml: str, max_age_seconds: int) -> bool:
    now = datetime.now(timezone.utc)
    for ev in xml.split("<Event ")[1:]:
        if PROFILE_NAME not in ev:
            continue
        m = re.search(r"SystemTime='([0-9T:\-]{19})", ev) or re.search(r'SystemTime="([0-9T:\-]{19})', ev)
        if not m:
            continue
        t = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        if abs((now - t).total_seconds()) <= max_age_seconds:
            return True
    return False
