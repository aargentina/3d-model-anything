#!/usr/bin/env bash
# Build an iPhoneOS app. AltStore signs the resulting IPA on the owner's device.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ "$(uname -s)" != Darwin ]]; then
  echo 'This build needs the GitHub-hosted macOS runner.' >&2
  exit 1
fi
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_RUN_NUMBER:?GITHUB_RUN_NUMBER is required}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is required}"
: "${IOS_BUNDLE_ID:?IOS_BUNDLE_ID is required}"
if [[ ! "$IOS_BUNDLE_ID" =~ ^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$ ]]; then
  echo 'IOS_BUNDLE_ID is not valid.' >&2
  exit 1
fi
if [[ ! "$GITHUB_RUN_NUMBER" =~ ^[1-9][0-9]{0,3}$ || ! "$GITHUB_RUN_ATTEMPT" =~ ^[1-9][0-9]?$ ]]; then
  echo 'The run number or attempt is outside the supported bundle version range.' >&2
  exit 1
fi

work_dir="$RUNNER_TEMP/ios-altstore"
mkdir -p "$work_dir/output"
xcodebuild -version
export XCODE_VERSION="$(xcodebuild -version | head -n 1)"
if ! command -v xcodegen >/dev/null 2>&1; then
  brew install xcodegen
fi
xcodegen --version
(
  cd apps/house-capture
  xcodegen generate
)

# XcodeGen writes a literal build number. Update the actual source plist as well
# as the build setting so each new IPA identifies its run and retry.
build_number="$GITHUB_RUN_NUMBER.$GITHUB_RUN_ATTEMPT"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $build_number" apps/house-capture/HouseCapture/Info.plist

xcodebuild \
  -project apps/house-capture/HouseCapture.xcodeproj \
  -scheme HouseCapture \
  -configuration Release \
  -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$work_dir/DerivedData" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY= \
  PRODUCT_BUNDLE_IDENTIFIER="$IOS_BUNDLE_ID" \
  CURRENT_PROJECT_VERSION="$build_number" \
  build

app="$work_dir/DerivedData/Build/Products/Release-iphoneos/HouseCapture.app"
python3 tools/ios/package_ipa.py "$app" "$work_dir/output/RoomCapture.ipa" --bundle-id "$IOS_BUNDLE_ID"
cp docs/ios-altstore.md "$work_dir/output/INSTALL.md"
