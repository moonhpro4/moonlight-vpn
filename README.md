# Moonlight VPN

Open source VPN made with OpenVPN, made by moonhpro4. One repo, two apps:

| App | Folder | Built by | Output |
|---|---|---|---|
| Android (Kotlin) | `app/` | `.github/workflows/build.yml` | `MoonlightVPN-debug-apk` -> `app-debug.apk` |
| Windows (Python) | `windows/` | `.github/workflows/build-windows.yml` | `MoonlightVPN-Windows-Setup` -> `MoonlightVPN-Setup.exe` (+ portable zip) |

**Fully on-device.** The 50 community `.ovpn` profiles live in `app/src/main/assets/vpns/` and are read from
inside the app. No server API, nothing stored or fetched from the cloud. The only network traffic is the VPN tunnel.
(The Windows build copies the same folder, so there is a single source of truth.)

## Get the apps
1. Push to GitHub (`main` or `master`). Both workflows start by themselves (or use **Run workflow**).
2. Actions tab -> open the run -> download the artifact.

## Server list
* 46 countries with flags (Android: emoji flags; Windows: bundled flag images, MIT licensed `flag-icons`).
* When a country has several servers (Russia, Ukraine, Romania) the app times them on the device and connects
  to the fastest. **Auto Server** picks a random server.
* **Game Mode** = USA. **Movie Mode** = pick USA (Best for streaming), Spain, Switzerland, Russia or Ukraine
  (Best for regional content). A country only appears if a file for it is bundled - there is no Switzerland
  file yet: add e.g. `switzerland-1.2.3.4-tcp443.ovpn` to `app/src/main/assets/vpns/` and it shows up.
* File names must look like `country-IP-tcp1234.ovpn` / `country-IP-udp1234.ovpn`.

## Windows app notes
* Needs the free **OpenVPN for Windows** engine. The installer bundles it (or installs it with winget).
* Runs as Administrator (needed to create the VPN adapter). Closing the window keeps it in the tray.
* **Windows VPN list:** the installer adds a "Moonlight VPN" entry (Settings > Network > VPN / Quick Settings) and a
  scheduled task. Pressing Connect there opens Moonlight VPN and connects a random server. Windows itself will still
  report its own placeholder entry as "can't connect" - the real tunnel is the one Moonlight VPN starts.
  Add/remove it any time from the app's Settings tab.

## Run the Windows app from source
```
pip install -r windows/requirements.txt
mkdir windows\assets\vpns & copy app\src\main\assets\vpns\*.ovpn windows\assets\vpns
python windows\app\main.py
```

## Engines / licenses
* Android: `vpnLib` of https://github.com/nizwar/openvpn_library (ics-openvpn based) at commit `ccd61bc`,
  fetched at build time by `scripts/fetch-engine.sh` (no git submodules).
* Windows: OpenVPN community edition (`openvpn.exe`).
* OpenVPN / ics-openvpn are GPLv2 - keep that in mind if you redistribute the apps.
