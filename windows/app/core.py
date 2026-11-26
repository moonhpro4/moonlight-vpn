"""Core data layer for Moonlight VPN (PC). 100 percent offline: reads the bundled .ovpn files."""
import os
import random
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

GLOBE = "\U0001F310"

# ------------------------------------------------------------------ paths

def base_dir() -> str:
    """Folder that contains the 'assets' directory (works for source runs and PyInstaller)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def assets_dir() -> str:
    env = os.environ.get("MOONLIGHT_ASSETS")
    if env:
        return env
    return os.path.join(base_dir(), "assets")


def vpns_dir() -> str:
    return os.path.join(assets_dir(), "vpns")


def flags_dir() -> str:
    return os.path.join(assets_dir(), "flags")


def data_dir() -> str:
    """Per-user writable folder (settings, temp config). Local to this PC only."""
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(root, "MoonlightVPN")
    os.makedirs(path, exist_ok=True)
    return path

# ------------------------------------------------------------------ metadata

# file-name prefix -> (display name, ISO 3166 code)
META: Dict[str, tuple] = {
    "argentina": ("Argentina", "AR"),
    "australia": ("Australia", "AU"),
    "bangladesh": ("Bangladesh", "BD"),
    "belarus": ("Belarus", "BY"),
    "brazil": ("Brazil", "BR"),
    "bulgaria": ("Bulgaria", "BG"),
    "canada": ("Canada", "CA"),
    "costa-rica": ("Costa Rica", "CR"),
    "croatia-hrvatska": ("Croatia", "HR"),
    "czech-republic": ("Czech Republic", "CZ"),
    "ecuador": ("Ecuador", "EC"),
    "finland": ("Finland", "FI"),
    "france": ("France", "FR"),
    "georgia": ("Georgia", "GE"),
    "germany": ("Germany", "DE"),
    "grenada": ("Grenada", "GD"),
    "hong-kong": ("Hong Kong", "HK"),
    "hungary": ("Hungary", "HU"),
    "india": ("India", "IN"),
    "indonesia": ("Indonesia", "ID"),
    "iran-islamic-republic-of": ("Iran", "IR"),
    "italy": ("Italy", "IT"),
    "japan": ("Japan", "JP"),
    "lithuania": ("Lithuania", "LT"),
    "mexico": ("Mexico", "MX"),
    "moldova": ("Moldova", "MD"),
    "myanmar": ("Myanmar", "MM"),
    "netherlands": ("Netherlands", "NL"),
    "new-zealand": ("New Zealand", "NZ"),
    "peru": ("Peru", "PE"),
    "portugal": ("Portugal", "PT"),
    "romania": ("Romania", "RO"),
    "russia": ("Russia", "RU"),
    "saudi-arabia": ("Saudi Arabia", "SA"),
    "singapore": ("Singapore", "SG"),
    "south-africa": ("South Africa", "ZA"),
    "south-korea": ("South Korea", "KR"),
    "spain": ("Spain", "ES"),
    "sweden": ("Sweden", "SE"),
    "switzerland": ("Switzerland", "CH"),
    "thailand": ("Thailand", "TH"),
    "uk": ("United Kingdom", "GB"),
    "united-arab-emirates": ("United Arab Emirates", "AE"),
    "ukraine": ("Ukraine", "UA"),
    "usa": ("United States", "US"),
    "vietnam": ("Vietnam", "VN"),
    "yemen": ("Yemen", "YE"),
}

ALIASES = {
    "usa": "usa us america united states",
    "uk": "uk gb britain england united kingdom",
    "united-arab-emirates": "uae emirates dubai",
    "saudi-arabia": "ksa saudi",
    "south-korea": "korea",
    "czech-republic": "czechia",
    "iran-islamic-republic-of": "iran persia",
    "croatia-hrvatska": "croatia hrvatska",
}

GAME_COUNTRY = "usa"
STREAMING_COUNTRY = "usa"  # tagged "Best for streaming"; the others "Best for regional content"
MOVIE_COUNTRIES = ["usa", "spain", "switzerland", "russia", "ukraine"]
TAG_STREAMING = "Best for streaming"
TAG_OTHER = "Best for regional content"

FILE_RE = re.compile(r"^(.+?)-+(\d{1,3}(?:\.\d{1,3}){3})-(tcp|udp)(\d+)\.ovpn$", re.IGNORECASE)

# ------------------------------------------------------------------ model

@dataclass(frozen=True)
class VpnServer:
    file_name: str
    country_key: str
    country_name: str
    country_code: str
    host: str
    protocol: str
    port: int

    @property
    def path(self) -> str:
        return os.path.join(vpns_dir(), self.file_name)


@dataclass
class Country:
    key: str
    name: str
    code: str
    servers: List[VpnServer] = field(default_factory=list)

    def search_text(self) -> str:
        return f"{self.name} {self.key.replace('-', ' ')} {self.code} {ALIASES.get(self.key, '')}".lower()

    def subtitle(self) -> str:
        n = len(self.servers)
        return f"Fastest of {n} servers is picked automatically" if n > 1 else "1 server"


def _parse(file_name: str) -> Optional[VpnServer]:
    m = FILE_RE.match(file_name)
    if not m:
        return None
    key = m.group(1).strip("-").lower()
    name, code = META.get(key, (" ".join(w.capitalize() for w in key.split("-")), ""))
    return VpnServer(file_name, key, name, code, m.group(2), m.group(3).lower(), int(m.group(4)))


_servers_cache: Optional[List[VpnServer]] = None


def servers() -> List[VpnServer]:
    global _servers_cache
    if _servers_cache is None:
        try:
            files = sorted(os.listdir(vpns_dir()))
        except OSError:
            files = []
        _servers_cache = [s for s in (_parse(f) for f in files) if s]
    return _servers_cache


def countries() -> List[Country]:
    by_key: Dict[str, Country] = {}
    for s in servers():
        c = by_key.setdefault(s.country_key, Country(s.country_key, s.country_name, s.country_code))
        c.servers.append(s)
    return sorted(by_key.values(), key=lambda c: c.name)


def by_country(key: str) -> List[VpnServer]:
    return [s for s in servers() if s.country_key == key]


def movie_countries() -> List[Country]:
    all_c = {c.key: c for c in countries()}
    return [all_c[k] for k in MOVIE_COUNTRIES if k in all_c]


def read_config(server: VpnServer) -> str:
    with open(server.path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def prepare_config(raw: str) -> str:
    """OpenVPN 2.6+ wants an explicit fallback for the legacy 'cipher' option."""
    cfg = raw.replace("\r\n", "\n")
    m = re.search(r"(?m)^cipher\s+(\S+)", cfg)
    if m and "data-ciphers-fallback" not in cfg:
        cfg = re.sub(r"(?m)^cipher\s+\S+",
                     lambda _m: f"cipher {m.group(1)}\ndata-ciphers-fallback {m.group(1)}", cfg, count=1)
    return cfg

# ------------------------------------------------------------------ fastest server (on-device timing)

_UNREACHABLE = float("inf")
_UNMEASURABLE = 1e12  # UDP servers cannot be timed with a TCP connect


def _measure(server: VpnServer, timeout: float) -> float:
    if server.protocol != "tcp":
        return _UNMEASURABLE
    best = _UNREACHABLE
    for _ in range(2):  # two tries, keep the better one
        t0 = time.perf_counter()
        try:
            with socket.create_connection((server.host, server.port), timeout=timeout):
                pass
            best = min(best, time.perf_counter() - t0)
        except OSError:
            pass
    return best


def fastest_first(pool: List[VpnServer], timeout: float = 3.0) -> List[VpnServer]:
    """Times every server of the pool in parallel and returns them fastest first (background thread only)."""
    if len(pool) < 2:
        return list(pool)
    times = [_UNREACHABLE] * len(pool)

    def work(i: int, s: VpnServer) -> None:
        times[i] = _measure(s, timeout)

    threads = [threading.Thread(target=work, args=(i, s), daemon=True) for i, s in enumerate(pool)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout * 2 + 1)
    order = sorted(range(len(pool)), key=lambda i: times[i])
    return [pool[i] for i in order]


def random_order(pool: List[VpnServer]) -> List[VpnServer]:
    p = list(pool)
    random.shuffle(p)
    return p


def is_online(timeout: float = 2.0) -> bool:
    """True if this PC can open an outgoing connection (no data is sent or fetched)."""
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443)):
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False
