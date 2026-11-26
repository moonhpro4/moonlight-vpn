"""Moonlight VPN for Windows - main window (tkinter)."""
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox

from PIL import Image, ImageTk

import core
import engine
import settings
import tray
import winvpn

BG, SURFACE, STROKE = "#14063A", "#21104F", "#3B2A7A"
PRIMARY, LAVENDER, MUTED, WHITE = "#8B5CF6", "#C4B5FD", "#9A8FC4", "#FFFFFF"
GREEN, AMBER = "#10B981", "#F59E0B"
FONT = "Segoe UI"

BRAND_TITLE = "Moonlight VPN"
BRAND_SUB = "moonlight VPN \u00a9 open source VPN made with open VPN and made by moonhpro4"
OFFLINE_MSG = ("Sorry, you are not connected to the internet. "
               "A VPN needs internet to connect to the global servers.")
COMMUNITY_MSG = ("All of these VPN servers are community servers. NOT OFFICIAL. "
                 "Speeds may be slow depending on who hosted this VPN server.")
JOIN_TEXT = "Want to join us? Make your old device a VPN node. Download our hosting software here."
JOIN_URL = "https://moonlight7.lovable.app/vpn"
AUTO_KEY = "__auto__"


class FlagStore:
    def __init__(self) -> None:
        self._cache = {}

    def get(self, code: str, width: int = 40):
        key = (code, width)
        if key in self._cache:
            return self._cache[key]
        path = os.path.join(core.flags_dir(), f"{code.lower()}.png") if code else ""
        globe = not code or not os.path.exists(path)
        if globe:
            path = os.path.join(core.assets_dir(), "globe.png")
        height = width if globe else int(width * 3 / 4)
        img = Image.open(path).convert("RGBA").resize((width, height), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self._cache[key] = photo
        return photo


class ScrollFrame(tk.Frame):
    def __init__(self, parent) -> None:
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        self.bind("<Destroy>", self._on_destroy)

    def _wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120) * 2, "units")

    def _on_destroy(self, _e) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.unbind_all(seq)
            except tk.TclError:
                pass

    def clear(self) -> None:
        for w in self.inner.winfo_children():
            w.destroy()


def make_row(parent, photo, title, sub, selected, on_click, sub_color=MUTED):
    f = tk.Frame(parent, bg=SURFACE, cursor="hand2", highlightthickness=2 if selected else 1,
                 highlightbackground=PRIMARY if selected else STROKE)
    f.pack(fill="x", padx=12, pady=4)
    img = tk.Label(f, image=photo, bg=SURFACE)
    img.image = photo
    img.pack(side="left", padx=(12, 10), pady=10)
    box = tk.Frame(f, bg=SURFACE)
    box.pack(side="left", fill="x", expand=True)
    t = tk.Label(box, text=title, bg=SURFACE, fg=WHITE, font=(FONT, 12, "bold"), anchor="w")
    t.pack(fill="x")
    s = tk.Label(box, text=sub, bg=SURFACE, fg=sub_color, font=(FONT, 9), anchor="w")
    s.pack(fill="x")
    c = tk.Label(f, text="\u2713" if selected else "", bg=SURFACE, fg=GREEN, font=(FONT, 14, "bold"), width=2)
    c.pack(side="right", padx=8)
    for w in (f, img, box, t, s, c):
        w.bind("<Button-1>", lambda _e: on_click())
    return f


def big_button(parent, text, command):
    return tk.Button(parent, text=text, command=command, bg=PRIMARY, fg=WHITE, activebackground=PRIMARY,
                     activeforeground=WHITE, relief="flat", bd=0, cursor="hand2", pady=16,
                     font=(FONT, 14, "bold"))


class ServerListWindow(tk.Toplevel):
    """Urban-VPN style list: search bar + every bundled country with its flag."""

    def __init__(self, app: "App", selected_key: str, on_pick) -> None:
        super().__init__(app)
        self.app, self.selected_key, self.on_pick = app, selected_key, on_pick
        self.title("All Servers")
        self.configure(bg=BG)
        self.geometry("420x640")
        self.transient(app)
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(top, text="All Servers", bg=BG, fg=WHITE, font=(FONT, 16, "bold")).pack(side="left")
        close = tk.Label(top, text="Close", bg=BG, fg=LAVENDER, font=(FONT, 11), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.destroy())
        tk.Label(self, text="Search countries\u2026", bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=18)
        self.q = tk.StringVar()
        entry = tk.Entry(self, textvariable=self.q, bg=SURFACE, fg=WHITE, insertbackground=WHITE, relief="flat",
                         font=(FONT, 12), highlightthickness=1, highlightbackground=STROKE,
                         highlightcolor=PRIMARY)
        entry.pack(fill="x", padx=16, pady=(2, 8), ipady=8)
        self.sf = ScrollFrame(self)
        self.sf.pack(fill="both", expand=True, pady=(4, 8))
        self.q.trace_add("write", lambda *_: self.refresh())
        self.refresh()
        entry.focus_set()

    def refresh(self) -> None:
        query = self.q.get().strip().lower()
        self.sf.clear()
        rows = []
        if not query or any(w.startswith(query) or query in w for w in ("auto server random fast best".split())):
            rows.append((AUTO_KEY, "", "Auto Server", "Automatically picks a server for you"))
        for c in core.countries():
            if not query or query in c.search_text():
                rows.append((c.key, c.code, c.name, c.subtitle()))
        if not rows:
            tk.Label(self.sf.inner, text="No countries found", bg=BG, fg=MUTED, font=(FONT, 11)).pack(pady=40)
            return
        for key, code, name, sub in rows:
            make_row(self.sf.inner, self.app.flags.get(code, 40), name, sub, key == self.selected_key,
                     lambda k=key: self._pick(k))

    def _pick(self, key: str) -> None:
        self.on_pick(key)
        self.destroy()


class App(tk.Tk):
    def __init__(self, ipc_queue: "queue.Queue[str]", start_hidden: bool = False, connect_random: bool = False):
        super().__init__()
        self.ipc_queue = ipc_queue
        self.tray_queue: "queue.Queue[str]" = queue.Queue()
        self.engine = engine.Engine()
        self.flags = FlagStore()
        self.selected_country = None          # None = Auto Server
        self.selected_movie = core.STREAMING_COUNTRY
        self._seen_version = -1
        self._quitting = False

        self.title(BRAND_TITLE)
        self.configure(bg=BG)
        self.geometry("420x740")
        self.minsize(400, 700)
        icon = os.path.join(core.assets_dir(), "icon.ico")
        if os.path.exists(icon) and os.name == "nt":
            try:
                self.iconbitmap(icon)
            except tk.TclError:
                pass

        self._build_header()
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True)
        self.pages = {
            "home": self._build_home(),
            "game": self._build_game(),
            "movie": self._build_movie(),
            "settings": self._build_settings(),
        }
        self._build_tabs()
        self.show_page("home")
        self.render()

        self.tray_icon = tray.start_tray(self.tray_queue.put)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if start_hidden and self.tray_icon:
            self.withdraw()
        if connect_random:
            self.after(400, self.connect_random)
        self.after(250, self._poll)

    # ------------------------------------------------------------------ layout

    def _build_header(self) -> None:
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=16, pady=14)
        logo = Image.open(os.path.join(core.assets_dir(), "logo.png")).convert("RGBA").resize((56, 56), Image.LANCZOS)
        self._logo = ImageTk.PhotoImage(logo)
        tk.Label(head, image=self._logo, bg=BG).pack(side="left")
        box = tk.Frame(head, bg=BG)
        box.pack(side="left", padx=12, fill="x", expand=True)
        tk.Label(box, text=BRAND_TITLE, bg=BG, fg=WHITE, font=(FONT, 20, "bold"), anchor="w").pack(fill="x")
        tk.Label(box, text=BRAND_SUB, bg=BG, fg=MUTED, font=(FONT, 8), anchor="w", justify="left",
                 wraplength=300).pack(fill="x")

    def _build_tabs(self) -> None:
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill="x", side="bottom")
        self.tab_buttons = {}
        for key, text in (("home", "Normal"), ("game", "Game"), ("movie", "Movie"), ("settings", "Settings")):
            b = tk.Button(bar, text=text, relief="flat", bd=0, bg=SURFACE, fg=MUTED, activebackground=SURFACE,
                          activeforeground=LAVENDER, font=(FONT, 11, "bold"), pady=12, cursor="hand2",
                          command=lambda k=key: self.show_page(k))
            b.pack(side="left", fill="x", expand=True)
            self.tab_buttons[key] = b

    def show_page(self, key: str) -> None:
        for k, frame in self.pages.items():
            frame.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self.tab_buttons.items():
            b.configure(fg=LAVENDER if k == key else MUTED)

    def _panel(self, parent):
        btn = big_button(parent, "Connect", lambda: None)
        status = tk.Label(parent, text="Not connected", bg=BG, fg=LAVENDER, font=(FONT, 11), wraplength=360)
        return btn, status

    def _build_home(self):
        f = tk.Frame(self.content, bg=BG)
        tk.Label(f, text="Selected server", bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor="w", padx=16)
        self.sel_card = tk.Frame(f, bg=BG)
        self.sel_card.pack(fill="x", pady=(4, 0))
        tk.Button(f, text="Show All", command=self.open_server_list, bg=BG, fg=LAVENDER, activebackground=BG,
                  activeforeground=WHITE, relief="flat", cursor="hand2", font=(FONT, 12, "bold"), pady=10,
                  highlightthickness=1, highlightbackground=PRIMARY).pack(fill="x", padx=16, pady=(8, 0))
        self.btn_home, self.status_home = self._panel(f)
        self.btn_home.configure(command=lambda: self.on_connect(
            lambda: self.selected_country.name if self.selected_country else "Auto Server",
            lambda: self.selected_country.servers if self.selected_country else core.servers(),
            lambda: self.selected_country is not None))
        self.btn_home.pack(fill="x", padx=16, pady=(40, 0))
        self.status_home.pack(pady=10)
        stats = tk.Frame(f, bg=SURFACE, highlightthickness=1, highlightbackground=STROKE)
        stats.pack(fill="x", padx=16, pady=14)
        self.lbl_time = tk.Label(stats, text="\u23f1 00:00:00", bg=SURFACE, fg=WHITE, font=(FONT, 10))
        self.lbl_time.pack(side="left", expand=True, pady=10)
        self.lbl_server = tk.Label(stats, text="\u2013", bg=SURFACE, fg=WHITE, font=(FONT, 10))
        self.lbl_server.pack(side="left", expand=True, pady=10)
        self.render_selection()
        return f

    def _build_game(self):
        f = tk.Frame(self.content, bg=BG)
        tk.Label(f, image=self.flags.get("us", 120), bg=BG).pack(pady=(40, 8))
        tk.Label(f, text="Game Mode", bg=BG, fg=WHITE, font=(FONT, 20, "bold")).pack()
        tk.Label(f, text="Connects automatically to a USA server for online gaming.", bg=BG, fg=MUTED,
                 font=(FONT, 10), wraplength=340).pack(pady=6)
        self.btn_game, self.status_game = self._panel(f)
        self.btn_game.configure(command=lambda: self.on_connect(
            lambda: "Game Mode", lambda: core.by_country(core.GAME_COUNTRY), lambda: True))
        self.btn_game.pack(fill="x", padx=16, pady=(30, 0))
        self.status_game.pack(pady=10)
        return f

    def _build_movie(self):
        f = tk.Frame(self.content, bg=BG)
        tk.Label(f, text="Movie Mode", bg=BG, fg=WHITE, font=(FONT, 20, "bold")).pack(anchor="w", padx=16)
        tk.Label(f, text="Pick a country, then connect.", bg=BG, fg=MUTED, font=(FONT, 10)).pack(
            anchor="w", padx=16, pady=(2, 8))
        self.movie_box = tk.Frame(f, bg=BG)
        self.movie_box.pack(fill="x")
        self.btn_movie, self.status_movie = self._panel(f)
        self.btn_movie.configure(command=lambda: self.on_connect(
            lambda: "Movie Mode", lambda: core.by_country(self.selected_movie), lambda: True))
        self.btn_movie.pack(fill="x", padx=16, pady=(14, 0))
        self.status_movie.pack(pady=10)
        self.render_movie()
        return f

    def _build_settings(self):
        f = tk.Frame(self.content, bg=BG)
        tk.Label(f, text="Settings", bg=BG, fg=WHITE, font=(FONT, 20, "bold")).pack(anchor="w", padx=16, pady=(4, 10))
        tk.Button(f, text=JOIN_TEXT, command=lambda: webbrowser.open(JOIN_URL), bg=PRIMARY, fg=WHITE,
                  activebackground=PRIMARY, activeforeground=WHITE, relief="flat", cursor="hand2",
                  font=(FONT, 11), wraplength=340, pady=12).pack(fill="x", padx=16)
        tk.Label(f, text="Windows VPN list", bg=BG, fg=WHITE, font=(FONT, 12, "bold")).pack(anchor="w", padx=16, pady=(22, 2))
        tk.Label(f, text=("Adds a \"Moonlight VPN\" entry to Windows Settings > Network > VPN and the Quick "
                          "Settings VPN tile. Pressing Connect there opens this app and connects a random "
                          "server. Windows will still say its own entry could not connect - the real tunnel "
                          "is the one Moonlight VPN starts."),
                 bg=BG, fg=MUTED, font=(FONT, 9), wraplength=370, justify="left").pack(anchor="w", padx=16)
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=16, pady=8)
        for text, cmd in (("Add to Windows VPN list", self.add_integration), ("Remove", self.remove_integration)):
            tk.Button(row, text=text, command=cmd, bg=SURFACE, fg=LAVENDER, activebackground=SURFACE,
                      activeforeground=WHITE, relief="flat", cursor="hand2", font=(FONT, 10, "bold"), pady=8,
                      padx=10).pack(side="left", padx=(0, 8))
        tk.Label(f, text=("All server profiles (.ovpn files) are stored inside this app on your PC. There is no "
                          "server API and nothing is downloaded or saved in the cloud."),
                 bg=BG, fg=MUTED, font=(FONT, 9), wraplength=370, justify="left").pack(anchor="w", padx=16, pady=14)
        return f

    # ------------------------------------------------------------------ selection rendering

    def render_selection(self) -> None:
        for w in self.sel_card.winfo_children():
            w.destroy()
        c = self.selected_country
        if c is None:
            make_row(self.sel_card, self.flags.get("", 44), "Auto Server", "Automatically picks a server for you",
                     False, self.open_server_list)
        else:
            make_row(self.sel_card, self.flags.get(c.code, 44), c.name, c.subtitle(), False, self.open_server_list)

    def render_movie(self) -> None:
        for w in self.movie_box.winfo_children():
            w.destroy()
        options = core.movie_countries()
        if options and not any(c.key == self.selected_movie for c in options):
            self.selected_movie = options[0].key
        for c in options:
            streaming = c.key == core.STREAMING_COUNTRY
            make_row(self.movie_box, self.flags.get(c.code, 44), c.name,
                     core.TAG_STREAMING if streaming else core.TAG_OTHER, c.key == self.selected_movie,
                     lambda k=c.key: self.pick_movie(k), sub_color=LAVENDER)

    def pick_movie(self, key: str) -> None:
        self.selected_movie = key
        self.render_movie()

    def open_server_list(self) -> None:
        current = self.selected_country.key if self.selected_country else AUTO_KEY
        ServerListWindow(self, current, self._on_country_picked)

    def _on_country_picked(self, key: str) -> None:
        self.selected_country = None if key == AUTO_KEY else next((c for c in core.countries() if c.key == key), None)
        self.render_selection()

    # ------------------------------------------------------------------ connecting

    def on_connect(self, label_fn, pool_fn, fastest_fn) -> None:
        if self.engine.state in (engine.CONNECTING, engine.CONNECTED):
            self.engine.disconnect()
            return
        if not core.is_online():
            messagebox.showinfo(BRAND_TITLE, "No internet connection.", parent=self)
            return
        if not engine.find_openvpn():
            self.offer_openvpn_install()
            return

        def go() -> None:
            self.engine.connect(label_fn(), pool_fn(), fastest_fn())

        if settings.get("skip_community_warning", False):
            go()
        else:
            self.community_dialog(go)

    def connect_random(self) -> None:
        self.show_window()
        if self.engine.state in (engine.CONNECTING, engine.CONNECTED):
            return
        self.on_connect(lambda: "Auto Server", core.servers, lambda: False)

    def community_dialog(self, on_ok) -> None:
        d = tk.Toplevel(self)
        d.title("Community servers")
        d.configure(bg=SURFACE)
        d.transient(self)
        d.resizable(False, False)
        tk.Label(d, text=COMMUNITY_MSG, bg=SURFACE, fg=WHITE, font=(FONT, 11), wraplength=340,
                 justify="left").pack(padx=24, pady=(22, 10))
        var = tk.BooleanVar(value=False)
        tk.Checkbutton(d, text="Don't remind me again", variable=var, bg=SURFACE, fg=WHITE, selectcolor=BG,
                       activebackground=SURFACE, activeforeground=WHITE, font=(FONT, 10)).pack(anchor="w", padx=24)

        def ok() -> None:
            if var.get():
                settings.set("skip_community_warning", True)
            d.destroy()
            on_ok()

        tk.Button(d, text="OK", command=ok, bg=PRIMARY, fg=WHITE, activebackground=PRIMARY, activeforeground=WHITE,
                  relief="flat", cursor="hand2", font=(FONT, 11, "bold"), padx=28, pady=6).pack(pady=18)
        d.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - d.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - d.winfo_height()) // 3
        d.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        d.grab_set()

    def offer_openvpn_install(self) -> None:
        if not messagebox.askyesno(BRAND_TITLE, "Moonlight VPN needs the free OpenVPN for Windows engine, which "
                                   "is not installed yet.\n\nInstall it now? (needs internet once)", parent=self):
            return
        self.status_home.configure(text="Installing OpenVPN\u2026 this can take a minute.")

        def work() -> None:
            ok, msg = engine.install_openvpn_with_winget()
            self.tray_queue.put("openvpn_ok" if ok else "openvpn_fail:" + msg)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ windows integration

    def add_integration(self) -> None:
        ok, msg = winvpn.install_integration()
        (messagebox.showinfo if ok else messagebox.showwarning)(
            BRAND_TITLE, ("\"Moonlight VPN\" was added to the Windows VPN list.\n\n" if ok else
                          "Some steps failed (this needs to run as Administrator):\n\n") + msg, parent=self)

    def remove_integration(self) -> None:
        winvpn.remove_integration()
        messagebox.showinfo(BRAND_TITLE, "Removed from the Windows VPN list.", parent=self)

    # ------------------------------------------------------------------ rendering

    def render(self) -> None:
        st, eng = self.engine.state, self.engine
        where = eng.current.country_name if eng.current else eng.label
        if st == engine.CONNECTED:
            text, color, status = "Disconnect", GREEN, f"Connected to {where}"
        elif st == engine.CONNECTING:
            text, color, status = "Connecting\u2026 click to cancel", AMBER, f"Connecting to {where}\u2026"
        elif st == engine.FAILED:
            text, color = "Connect", PRIMARY
            status = eng.error or "Couldn't connect. Please try again or pick another server."
        else:
            text, color, status = "Connect", PRIMARY, "Not connected"
        for btn, lbl in ((self.btn_home, self.status_home), (self.btn_game, self.status_game),
                         (self.btn_movie, self.status_movie)):
            btn.configure(text=text, bg=color, activebackground=color)
            lbl.configure(text=status)
        self.lbl_server.configure(text=(eng.current.host if st == engine.CONNECTED and eng.current else "\u2013"))
        self._seen_version = eng.version

    def _tick_time(self) -> None:
        if self.engine.state == engine.CONNECTED and self.engine.connected_at:
            s = int(time.time() - self.engine.connected_at)
            self.lbl_time.configure(text=f"\u23f1 {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}")
        else:
            self.lbl_time.configure(text="\u23f1 00:00:00")

    # ------------------------------------------------------------------ window / tray / ipc

    def show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self) -> None:
        if self.tray_icon:
            self.withdraw()          # keep running in the tray so Windows' Connect button works
        else:
            self.quit_app()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.engine.shutdown()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()

    def _poll(self) -> None:
        for q in (self.ipc_queue, self.tray_queue):
            while True:
                try:
                    msg = q.get_nowait()
                except queue.Empty:
                    break
                self._handle(msg)
        if self.engine.version != self._seen_version:
            self.render()
        self._tick_time()
        if not self._quitting:
            self.after(250, self._poll)

    def _handle(self, msg: str) -> None:
        if msg in ("SHOW", "open"):
            self.show_window()
        elif msg in ("CONNECT_RANDOM", "connect"):
            self.connect_random()
        elif msg == "disconnect":
            self.engine.disconnect()
        elif msg == "exit":
            self.quit_app()
        elif msg == "openvpn_ok":
            messagebox.showinfo(BRAND_TITLE, "OpenVPN was installed. You can connect now.", parent=self)
            self.render()
        elif msg.startswith("openvpn_fail"):
            if messagebox.askyesno(BRAND_TITLE, "Automatic install failed.\n\nOpen the OpenVPN download page?",
                                   parent=self):
                webbrowser.open("https://openvpn.net/community-downloads/")
            self.render()
