#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(sed -nE '1 s/^[^(]*\(([^)]+)\).*/\1/p' "$ROOT/debian/changelog")
[ -n "$VERSION" ] || { echo "could not parse version from debian/changelog" >&2; exit 1; }

PKG_DIR="$ROOT/dist/local-jev_${VERSION}_all"
DEB_OUT="$ROOT/dist/local-jev_${VERSION}_all.deb"

rm -rf "$PKG_DIR" "$DEB_OUT"
mkdir -p "$PKG_DIR/DEBIAN" \
         "$PKG_DIR/usr/bin" \
         "$PKG_DIR/usr/lib/local-jev" \
         "$PKG_DIR/usr/share/doc/local-jev" \
         "$PKG_DIR/usr/share/doc/local-jev/html"

install -m 0755 "$ROOT/bin/local-jev"                         "$PKG_DIR/usr/bin/local-jev"
install -m 0644 "$ROOT/lib/local-jev/local_jev_runtime.py"    "$PKG_DIR/usr/lib/local-jev/local_jev_runtime.py"
install -m 0644 "$ROOT/README.md"                             "$PKG_DIR/usr/share/doc/local-jev/README.md"
install -m 0644 "$ROOT/LICENSE"                               "$PKG_DIR/usr/share/doc/local-jev/copyright"
install -m 0644 "$ROOT/docs/index.html"                       "$PKG_DIR/usr/share/doc/local-jev/html/index.html"
install -m 0755 "$ROOT/debian/postinst"                       "$PKG_DIR/DEBIAN/postinst"
install -m 0755 "$ROOT/debian/postrm"                         "$PKG_DIR/DEBIAN/postrm"

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: local-jev
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: bash (>= 4.0), python3 (>= 3.10), python3-venv, python3-pip, python3-dev, build-essential, cmake, ca-certificates
Maintainer: Ramazan Yavuz <yavuzramazan1994@gmail.com>
Homepage: https://github.com/ra-yavuz/local-jev
Description: local Jev-shaped decision API over GGUF models
 local-jev runs a small local HTTP service for typed decisions: yes or no,
 multiple choice, and ordered ratings. It creates an isolated Python runtime
 under the user's home directory, downloads a selected GGUF model, and serves
 a Kev-style /v1/systemone API on localhost.
 .
 The package does not include model weights. Run local-jev setup after
 installing to download the default model and runtime dependencies.
 .
 DISCLAIMER: local-jev downloads and runs third-party model files and uses
 model output to score decisions. It is provided AS IS, WITHOUT WARRANTY OF
 ANY KIND. The author is not liable for any harm, data loss, security
 incident, model output, model download, classification result, or other
 damages. By installing or running it you accept full responsibility.
EOF

dpkg-deb --build --root-owner-group "$PKG_DIR" "$DEB_OUT"
echo
echo "Built: $DEB_OUT"
ls -la "$DEB_OUT"
