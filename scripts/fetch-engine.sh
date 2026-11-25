#!/usr/bin/env bash
# Downloads the OpenVPN engine (ics-openvpn based "vpnLib" module, with prebuilt
# native libraries for arm64-v8a / armeabi-v7a / x86 / x86_64) at a PINNED commit.
# No git submodules are involved. Build-time only: the finished APK is fully offline.
set -uo pipefail
COMMIT="ccd61bc39bcb5b03281615ce669d2109557f6bd1"
REPO="https://github.com/nizwar/openvpn_library.git"
DIR="engine"

if [ -d "$DIR/vpnLib/src" ]; then echo "[engine] already present"; exit 0; fi

for attempt in 1 2 3; do
  echo "[engine] download attempt $attempt"
  rm -rf "$DIR"; mkdir -p "$DIR"
  if git -C "$DIR" init -q \
     && git -C "$DIR" fetch -q --depth 1 "$REPO" "$COMMIT" \
     && git -C "$DIR" checkout -q FETCH_HEAD; then
    rm -rf "$DIR/.git"
    echo "[engine] ready at $DIR/vpnLib"
    exit 0
  fi
  sleep 5
done

echo "[engine] WARNING: GitHub download failed, Gradle will fall back to the JitPack build of the same commit."
rm -rf "$DIR"
exit 0
