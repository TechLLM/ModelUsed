#!/bin/bash
# ModelUsed 설치: 빌드 → ~/Applications 복사 → 로그인 자동실행(LaunchAgent) → 실행
set -e
cd "$(dirname "$0")"

./build.sh

DEST="$HOME/Applications"
mkdir -p "$DEST"
rm -rf "$DEST/ModelUsed.app"
cp -R "ModelUsed.app" "$DEST/"

PLIST="$HOME/Library/LaunchAgents/com.modelused.widget.plist"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.modelused.widget</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DEST/ModelUsed.app/Contents/MacOS/ModelUsed</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST" 2>/dev/null || true

open "$DEST/ModelUsed.app"
echo "설치 완료 — $DEST/ModelUsed.app (로그인 시 자동 실행)"
