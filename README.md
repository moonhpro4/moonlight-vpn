# Moonlight VPN

Native Android (Kotlin) VPN client. Open source VPN made with OpenVPN, made by moonhpro4.

**Fully on-device:** the 43 community `.ovpn` profiles live in `app/src/main/assets/vpns/` and are read
from inside the APK. There is no server API and nothing is stored or fetched from the cloud. Country
flags are emoji rendered by the phone itself. The only network traffic is the VPN tunnel you start.

## Get the APK
1. Push this repo to GitHub (branch `main` or `master`).
2. Open the **Actions** tab -> **Build Moonlight VPN APK** -> latest run.
3. Download **MoonlightVPN-debug-apk** from *Artifacts*, unzip it and install `app-debug.apk`.

You can also start the build by hand with **Run workflow**.

## Layout
```
.github/workflows/build.yml     CI: Java 17, Android SDK, NDK 27.2.12479018, CMake 3.22.1, assembleDebug
scripts/fetch-engine.sh         downloads the OpenVPN engine (pinned commit, no git submodules)
app/src/main/assets/vpns/       the 43 bundled .ovpn files
app/src/main/java/.../          MainActivity, ServerListActivity, VpnManager, ServerRepository, NetworkUtils
```

## Build locally
```
bash scripts/fetch-engine.sh
gradle wrapper --gradle-version 8.9   # once, if there is no ./gradlew yet
./gradlew assembleDebug
```

## Engine
Servers: when a country has several bundled servers (USA, Russia) the app times them on the phone and connects to the fastest.

Uses the `vpnLib` module of https://github.com/nizwar/openvpn_library (ics-openvpn based, OpenVPN 2.7,
prebuilt native libraries for arm64-v8a, armeabi-v7a, x86, x86_64) at commit `ccd61bc`. The engine is GPLv2
(ics-openvpn / OpenVPN); keep that in mind if you redistribute the APK.
