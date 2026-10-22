#!/usr/bin/env python3
"""Package an unsigned iPhone app for local signing with AltStore Classic."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import struct
import sys
import tempfile
import zipfile


class PackageError(ValueError):
    """The app cannot be packaged."""


def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def arm64_executable(path):
    """Accept a thin arm64 executable or a universal file with an arm64 slice."""
    with path.open("rb") as stream:
        head = stream.read(8)
        if len(head) != 8:
            return False
        if head[:4] in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
            endian = "<" if head[:4] == b"\xcf\xfa\xed\xfe" else ">"
            tail = stream.read(24)
            return (len(tail) == 24
                    and struct.unpack(endian + "I", head[4:])[0] == 0x0100000C
                    and struct.unpack(endian + "I", tail[4:8])[0] == 2)
        formats = {b"\xca\xfe\xba\xbe": (">", 20),
                   b"\xbe\xba\xfe\xca": ("<", 20),
                   b"\xca\xfe\xba\xbf": (">", 32),
                   b"\xbf\xba\xfe\xca": ("<", 32)}
        if head[:4] not in formats:
            return False
        endian, width = formats[head[:4]]
        count = struct.unpack(endian + "I", head[4:])[0]
        if not 1 <= count <= 32:
            return False
        for _ in range(count):
            record = stream.read(width)
            if len(record) != width:
                return False
            cpu = struct.unpack(endian + "I", record[:4])[0]
            if cpu == 0x0100000C:
                offset = struct.unpack(endian + ("I" if width == 20 else "Q"),
                                       record[8:12] if width == 20 else record[8:16])[0]
                position = stream.tell()
                stream.seek(offset)
                thin = stream.read(32)
                stream.seek(position)
                if (len(thin) == 32 and thin[:4] == b"\xcf\xfa\xed\xfe"
                        and struct.unpack("<I", thin[4:8])[0] == 0x0100000C
                        and struct.unpack("<I", thin[12:16])[0] == 2):
                    return True
        return False


def inspect_app(app, bundle_id):
    app = Path(app).absolute()
    if app.is_symlink() or not app.is_dir() or app.suffix != ".app":
        raise PackageError("Use a real .app folder.")
    root = app.resolve()
    entries = []
    for folder, directories, files in os.walk(app, followlinks=False):
        for name in sorted(directories + files):
            path = Path(folder) / name
            relative = path.relative_to(app)
            if "\\" in str(relative.as_posix()):
                raise PackageError("A bundle path contains a backslash.")
            if name.lower() == "embedded.mobileprovision":
                raise PackageError("Remove the provisioning profile before this build step.")
            if path.is_symlink():
                try:
                    target = path.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise PackageError("A bundle link has no valid target.") from exc
                if not inside(target, root):
                    raise PackageError("A bundle link leaves the app folder.")
                if os.path.isabs(os.readlink(path)):
                    raise PackageError("A bundle link uses an absolute target.")
            elif not path.is_dir() and not path.is_file():
                raise PackageError("The app contains a special file.")
            entries.append(path)
    try:
        with (app / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        raise PackageError("The app Info.plist cannot be read.") from exc
    if not isinstance(info, dict) or info.get("CFBundleIdentifier") != bundle_id:
        raise PackageError("The app bundle ID does not match --bundle-id.")
    if (info.get("CFBundleSupportedPlatforms") != ["iPhoneOS"]
            or info.get("DTPlatformName", "iphoneos") != "iphoneos"):
        raise PackageError("Use an iPhoneOS app. A simulator app cannot be installed.")
    version = info.get("CFBundleVersion")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", version):
        raise PackageError("The app has no valid CFBundleVersion.")
    parts = [int(part) for part in version.split(".")]
    if not 1 <= parts[0] <= 9999 or any(part > 99 for part in parts[1:]):
        raise PackageError("The app build number exceeds Apple's limits.")
    executable = info.get("CFBundleExecutable")
    if (not isinstance(executable, str) or not executable
            or executable in (".", "..") or "/" in executable or "\\" in executable):
        raise PackageError("The app has no valid executable name.")
    binary = app / executable
    if not binary.is_file() or not arm64_executable(binary):
        raise PackageError("The app needs an arm64 Mach-O executable.")
    if os.name != "nt" and not binary.stat().st_mode & 0o111:
        raise PackageError("The app executable has no execute permission.")
    return app, info, sorted(entries, key=lambda item: item.relative_to(app).as_posix())


def package(app, output, bundle_id, environment=None):
    app, info, entries = inspect_app(app, bundle_id)
    output = Path(output).absolute()
    if output.suffix.lower() != ".ipa":
        raise PackageError("The output name must end with .ipa.")
    if inside(output.resolve(), app.resolve()):
        raise PackageError("Write the IPA outside the app folder.")
    output.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ if environment is None else environment
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".ipa.tmp", delete=False) as temp:
            temp_path = Path(temp.name)
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in [app] + entries:
                relative = path.relative_to(app)
                name = "Payload/HouseCapture.app"
                if relative.parts:
                    name += "/" + relative.as_posix()
                mode = path.lstat().st_mode
                # Windows does not store Unix execute bits. Restore them for the
                # executable that Info.plist identifies. macOS modes stay intact.
                if os.name == "nt" and path == app / info["CFBundleExecutable"]:
                    mode |= 0o111
                directory = stat.S_ISDIR(mode)
                item = zipfile.ZipInfo(name + ("/" if directory else ""))
                item.create_system = 3
                item.external_attr = (mode & 0xFFFF) << 16
                if directory:
                    item.external_attr |= 0x10
                    data = b""
                elif path.is_symlink():
                    data = os.fsencode(os.readlink(path))
                else:
                    data = path.read_bytes()
                item.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(item, data)
        with temp_path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        record = {
            "ipa": output.name,
            "sha256": checksum,
            "bundle_id": info["CFBundleIdentifier"],
            "build_version": info["CFBundleVersion"],
            "marketing_version": info.get("CFBundleShortVersionString"),
            "minimum_ios_version": info.get("MinimumOSVersion"),
            "source_commit": env.get("GITHUB_SHA"),
            "github_run_id": env.get("GITHUB_RUN_ID"),
            "xcode_version": env.get("XCODE_VERSION"),
            "signing": "Requires local signing before installation",
        }
        os.replace(temp_path, output)
        temp_path = None
        output.with_suffix(output.suffix + ".sha256").write_text(
            f"{checksum}  {output.name}\n", encoding="utf-8")
        (output.parent / "build-info.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bundle-id", required=True)
    args = parser.parse_args()
    try:
        record = package(args.app, args.output, args.bundle_id)
    except (PackageError, OSError) as exc:
        print(f"Package failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
