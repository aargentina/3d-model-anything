# Install with AltStore Classic from Windows

This route uses a free Apple Account. It does not use TestFlight or require paid
Apple Developer Program membership. GitHub builds the app on a hosted Mac.
AltStore Classic signs and installs the IPA with your account.

## Get the IPA

1. Open this repository's Actions tab.
2. Select **Build iPhone app for AltStore**, then **Run workflow** on `main`.
3. Wait for a green result. Open the run and download its build artifact.
4. Extract the ZIP. Keep `RoomCapture.ipa` intact. The IPA is itself an archive;
   do not extract it before installation.

The artifact also contains a SHA-256 checksum, `build-info.json`, and this guide.
It is kept for seven days. Download it before it expires. A new manual run makes
a new copy. Standard GitHub-hosted runners are free for public repositories.
Private repositories can have Actions and storage charges after their allowance.

## Set up AltStore Classic

Use the official [Windows installation guide](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows).
Get AltServer from [altstore.io](https://altstore.io/). Use **Classic** for this
workflow. Follow its current iTunes and iCloud requirements. Do not replace or
remove an existing Apple installation without checking the guide first.

1. Install the required Apple components and AltServer on Windows.
2. Connect the unlocked iPhone with a USB cable. Accept Trust on the phone.
3. Follow the guide to enable Wi-Fi sync and install AltStore Classic.
4. Enter your Apple Account and any sign-in code directly in the install app.
   Do not put your password, codes, or signing files in this repository.
5. Complete developer trust and Developer Mode on the iPhone when asked.
6. Keep AltServer running while the phone is connected by USB or on the same Wi-Fi.

## Install this app

1. Transfer `RoomCapture.ipa` to Files on the iPhone. You can instead download the
   GitHub artifact in Safari while signed in to GitHub, then extract the outer ZIP.
2. In AltStore Classic, open **My Apps** and use **+** to select the IPA.
3. Allow AltStore to sign and install the app. It appears as **3D Model Anything**.
4. Allow Camera when you start a scan. Scanning needs a LiDAR device with
   iOS/iPadOS 17 or later. Other supported devices can import and review scans.

The standard iPhone 16 has no LiDAR. The iPhone 16 Pro and 16 Pro Max have LiDAR.
Check the exact model before you plan to scan a room.

## Renew the install

Free signing lasts seven days. In AltStore Classic, select **Refresh All** before
the app expires. Background refresh can help when AltServer is available. Keep
the same Apple Account and app identity for updates. Do not delete the scanner
to refresh it. Export important scans to a separate location before an update.

Apple permits three active apps per device with a free account. AltStore uses
one slot. Review AltStore's [renewal limits](https://faq.altstore.io/altstore-classic/your-altstore)
and [connection requirements](https://faq.altstore.io/altstore-classic/altserver).

## What the build proves

The workflow compiles a Release app for a physical iPhone and checks the IPA
layout, executable, platform, bundle ID, version, and checksum. It has no Apple
account secrets. It cannot check installation, camera permissions, LiDAR capture,
or AltStore compatibility with a particular iOS update. Confirm those on the phone.

The source review found a malformed-scan crash risk. Use your own exports for
the first test. Fix input validation before accepting files from other people.

## Build settings

- Runner: `macos-26`, with Xcode 26.6.
- Scheme: `HouseCapture`; Release build for `iphoneos`.
- Bundle ID: `com.aargentina.roomcapture` before AltStore applies your account.
- Build number: GitHub run number and attempt, for example `1.1`.
- Trigger: manual only, with one build at a time and a 30-minute limit.
- Output: unsigned IPA. AltStore performs signing during install.

Xcode does not need to match the phone's OS version for an ordinary App Store
style app launch. This app targets iOS 17 or later. Device installation and
operation on a newer OS still need to be checked on the device.

## Setup checks

The setup was reviewed on 22 October 2026. The workflow passed Actionlint and
the build script passed Bash syntax checks. Eight package tests passed on
Windows; two link tests need macOS and are included in the workflow. The first
hosted run must confirm the Swift build and all ten package tests. After that,
the owner must confirm installation and operation on the physical iPhone.
