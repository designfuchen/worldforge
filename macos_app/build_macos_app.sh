#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_NAME="WorldForge"
EXEC_NAME="WorldForge"
BUNDLE_DIR="${PROJECT_ROOT}/${APP_NAME}.app"
DESKTOP_BUNDLE_DIR="${HOME}/Desktop/${APP_NAME}.app"
CONTENTS_DIR="${BUNDLE_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"

# 1. Copy AppIcon.icns if available
if [ -f "${SCRIPT_DIR}/Resources/AppIcon.icns" ]; then
    cp -f "${SCRIPT_DIR}/Resources/AppIcon.icns" "${RESOURCES_DIR}/AppIcon.icns"
fi

# 2. Generate Info.plist
cat > "${CONTENTS_DIR}/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDisplayName</key>
    <string>WorldForge 世界工坊</string>
    <key>CFBundleExecutable</key>
    <string>${EXEC_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>ai.worldforge.studio.macos</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>WorldForge 世界工坊</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0.0</string>
    <key>CFBundleVersion</key>
    <string>200</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
</dict>
</plist>
EOF

# 3. Compile modular Swift sources with Whole-Module Optimization (-O -whole-module-optimization)
SWIFT_SOURCES=(
    "${SCRIPT_DIR}/Sources/Models.swift"
    "${SCRIPT_DIR}/Sources/AsyncMediaEngine.swift"
    "${SCRIPT_DIR}/Sources/ForgeClient.swift"
    "${SCRIPT_DIR}/Sources/Stores.swift"
    "${SCRIPT_DIR}/Sources/Views/TelemetrySparklineView.swift"
    "${SCRIPT_DIR}/Sources/Views/Trajectory3DCanvasView.swift"
    "${SCRIPT_DIR}/Sources/Views/ABComparePlayerView.swift"
    "${SCRIPT_DIR}/Sources/Views/GalleryMasonryView.swift"
    "${SCRIPT_DIR}/Sources/Views/MainStudioWindow.swift"
    "${SCRIPT_DIR}/Sources/WorldForgeApp.swift"
)

echo "▶ Compiling WorldForge Native macOS Studio (arm64-apple-macos14.0, -O -whole-module-optimization)..."
START_TS=$(python3 -c 'import time; print(time.time())')

swiftc \
    -O \
    -whole-module-optimization \
    -target arm64-apple-macos14.0 \
    -parse-as-library \
    -framework SwiftUI \
    -framework AppKit \
    -framework AVKit \
    -framework AVFoundation \
    -framework CoreGraphics \
    -framework ImageIO \
    -framework Quartz \
    -framework WebKit \
    -framework UniformTypeIdentifiers \
    "${SWIFT_SOURCES[@]}" \
    -o "${MACOS_DIR}/${EXEC_NAME}"

END_TS=$(python3 -c 'import time; print(time.time())')
ELAPSED=$(python3 -c "print(f'{${END_TS} - ${START_TS}:.2f}s')")

chmod +x "${MACOS_DIR}/${EXEC_NAME}"

# 4. Ad-hoc sign the app bundle
xattr -cr "${BUNDLE_DIR}" 2>/dev/null || true
codesign --force --deep --sign - "${BUNDLE_DIR}"

# 5. Sync to dist/WorldForge.app and ~/Desktop/WorldForge.app
DIST_DIR="${PROJECT_ROOT}/dist"
DIST_BUNDLE_DIR="${DIST_DIR}/${APP_NAME}.app"
mkdir -p "${DIST_DIR}"
rm -rf "${DIST_BUNDLE_DIR}"
cp -R "${BUNDLE_DIR}" "${DIST_BUNDLE_DIR}"
xattr -cr "${DIST_BUNDLE_DIR}" 2>/dev/null || true
codesign --force --deep --sign - "${DIST_BUNDLE_DIR}"

rm -rf "${DESKTOP_BUNDLE_DIR}"
cp -R "${BUNDLE_DIR}" "${DESKTOP_BUNDLE_DIR}"
xattr -cr "${DESKTOP_BUNDLE_DIR}" 2>/dev/null || true
codesign --force --deep --sign - "${DESKTOP_BUNDLE_DIR}"

BIN_SIZE=$(ls -lh "${MACOS_DIR}/${EXEC_NAME}" | awk '{print $5}')
echo "✓ Built ${BUNDLE_DIR}, ${DIST_BUNDLE_DIR}, and ${DESKTOP_BUNDLE_DIR} in ${ELAPSED} (Binary: ${BIN_SIZE})"
