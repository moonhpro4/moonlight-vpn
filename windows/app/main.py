"""Moonlight VPN for Windows - entry point.

  MoonlightVPN.exe                     open the window
  MoonlightVPN.exe --tray              start hidden in the system tray (used at Windows start-up)
  MoonlightVPN.exe --ras-event         started by Windows when 'Moonlight VPN' is pressed in the VPN list
  MoonlightVPN.exe --install-integration / --remove-integration   (used by the installer)
"""
import sys
import tkinter as tk
from tkinter import messagebox

import core
import ipc

OFFLINE_MSG = ("Sorry, you are not connected to the internet. "
               "A VPN needs internet to connect to the global servers.")


def main() -> int:
    args = sys.argv[1:]

    if "--install-integration" in args or "--remove-integration" in args:
        import winvpn
        ok, msg = winvpn.install_integration() if "--install-integration" in args else winvpn.remove_integration()
        return 0 if ok else 1

    ras_event, tray_mode = "--ras-event" in args, "--tray" in args

    if ras_event:
        import winvpn
        if not winvpn.recent_ras_event():
            return 0                      # some other VPN fired the event, not ours
        message = "CONNECT_RANDOM"
    else:
        message = None if tray_mode else "SHOW"

    listener = ipc.Listener()
    if not listener.start():              # already running: just talk to the running copy
        if message:
            ipc.send(message)
        return 0

    # 1) Internet check on a normal launch. Skipped for the silent start-up copy,
    #    because the network may not be up yet when Windows has only just logged in.
    if not tray_mode and not ras_event and not core.is_online():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Moonlight VPN", OFFLINE_MSG)   # OK (or X) closes the app
        return 0

    from ui import App
    app = App(listener.queue, start_hidden=tray_mode, connect_random=ras_event)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
