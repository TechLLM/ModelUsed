#!/bin/bash
# ModelUsed.app 빌드 — collector 파이썬을 앱 번들 안에 포함
set -e
cd "$(dirname "$0")"
APP="ModelUsed.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/collector"

# Xcode 라이선스 미동의 시 xcode-select가 막히므로 CLT를 우선 사용
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Library/Developer/CommandLineTools}"
[ -d "$DEVELOPER_DIR" ] || unset DEVELOPER_DIR

swiftc -O -o "$APP/Contents/MacOS/ModelUsed" app/ModelUsed.swift \
    -target arm64-apple-macosx14.0

cp app/Info.plist "$APP/Contents/Info.plist"
cp icons/*.png "$APP/Contents/Resources/"
[ -f config.json ] || cp config.example.json config.json
cp collect.py news.py config.json "$APP/Contents/Resources/collector/"
cp -R providers "$APP/Contents/Resources/collector/"
find "$APP/Contents/Resources/collector" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# ad-hoc 서명 (로컬 실행용)
codesign --force --deep -s - "$APP" 2>/dev/null || true

echo "빌드 완료: $(pwd)/$APP"
