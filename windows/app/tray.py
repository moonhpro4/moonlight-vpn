"""System-tray icon (optional: the app still works without pystray)."""
import os

import core


def start_tray(push):
    """push(cmd) is called from the tray thread with 'open' | 'connect' | 'disconnect' | 'exit'."""
    try:
        import pystray
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(os.path.join(core.assets_dir(), "logo.png")).convert("RGBA").resize((64, 64))
        menu = pystray.Menu(
            pystray.MenuItem("Open Moonlight VPN", lambda icon, item: push("open"), default=True),
            pystray.MenuItem("Connect (random server)", lambda icon, item: push("connect")),
            pystray.MenuItem("Disconnect", lambda icon, item: push("disconnect")),
            pystray.MenuItem("Exit", lambda icon, item: push("exit")),
        )
        icon = pystray.Icon("MoonlightVPN", image, "Moonlight VPN", menu)
        icon.run_detached()
        return icon
    except Exception:
        return None
