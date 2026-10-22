"""Tests for the unsigned IPA package helper."""

import hashlib
import json
from pathlib import Path
import plistlib
import stat
import struct
import tempfile
import unittest
import zipfile

from package_ipa import PackageError, package


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "HouseCapture.app"
        self.app.mkdir()
        self.output = self.root / "out" / "HouseCapture.ipa"
        self.info = {
            "CFBundleIdentifier": "com.aargentina.roomcapture",
            "CFBundleExecutable": "HouseCapture",
            "CFBundleVersion": "12.1",
            "CFBundleShortVersionString": "1.0",
            "CFBundleSupportedPlatforms": ["iPhoneOS"],
            "DTPlatformName": "iphoneos",
            "MinimumOSVersion": "17.0",
        }
        self.save_info()
        self.binary = self.app / "HouseCapture"
        self.binary.write_bytes(struct.pack("<8I", 0xfeedfacf, 0x0100000C, 0, 2, 0, 0, 0, 0))
        self.binary.chmod(0o755)

    def save_info(self):
        with (self.app / "Info.plist").open("wb") as stream:
            plistlib.dump(self.info, stream)

    def build(self):
        return package(self.app, self.output, "com.aargentina.roomcapture", {
            "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123", "XCODE_VERSION": "26.6"})

    def test_package_checksum_permissions_and_source(self):
        before = {p.relative_to(self.app): (p.read_bytes(), p.stat().st_mode)
                  for p in self.app.rglob("*") if p.is_file()}
        result = self.build()
        with zipfile.ZipFile(self.output) as archive:
            item = archive.getinfo("Payload/HouseCapture.app/HouseCapture")
            self.assertEqual(item.create_system, 3)
            self.assertTrue((item.external_attr >> 16) & stat.S_IXUSR)
            self.assertTrue(stat.S_ISREG(item.external_attr >> 16))
            info = plistlib.loads(archive.read("Payload/HouseCapture.app/Info.plist"))
            self.assertEqual(info["CFBundleVersion"], "12.1")
        expected = hashlib.sha256(self.output.read_bytes()).hexdigest()
        self.assertEqual(result["sha256"], expected)
        self.assertEqual(self.output.with_suffix(".ipa.sha256").read_text(),
                         expected + "  HouseCapture.ipa\n")
        record = json.loads((self.output.parent / "build-info.json").read_text())
        self.assertEqual(record["minimum_ios_version"], "17.0")
        self.assertEqual(record["source_commit"], "a" * 40)
        self.assertEqual(before, {p.relative_to(self.app): (p.read_bytes(), p.stat().st_mode)
                                 for p in self.app.rglob("*") if p.is_file()})

    def test_simulator_is_rejected(self):
        self.info["CFBundleSupportedPlatforms"] = ["iPhoneSimulator"]
        self.info["DTPlatformName"] = "iphonesimulator"
        self.save_info()
        with self.assertRaises(PackageError):
            self.build()

    def test_wrong_bundle_is_rejected(self):
        self.info["CFBundleIdentifier"] = "com.wesbos.housecapture"
        self.save_info()
        with self.assertRaises(PackageError):
            self.build()

    def test_executable_path_escape_is_rejected(self):
        self.info["CFBundleExecutable"] = "../outside"
        self.save_info()
        with self.assertRaises(PackageError):
            self.build()

    def test_profile_is_rejected_in_nested_folder(self):
        child = self.app / "nested"
        child.mkdir()
        (child / "embedded.mobileprovision").write_bytes(b"private")
        with self.assertRaises(PackageError):
            self.build()
        self.assertTrue((child / "embedded.mobileprovision").is_file())

    def test_non_macho_binary_is_rejected(self):
        self.binary.write_bytes(b"not a Mach-O executable")
        with self.assertRaises(PackageError):
            self.build()

    def test_invalid_build_numbers_are_rejected(self):
        for version in ["", "1.bad", "10000.1", "1.100", "0.1", 1]:
            with self.subTest(version=version):
                self.info["CFBundleVersion"] = version
                self.save_info()
                with self.assertRaises(PackageError):
                    self.build()

    def test_output_cannot_change_source(self):
        self.output = self.app / "overwrite.ipa"
        with self.assertRaises(PackageError):
            self.build()

    def make_link(self, target, link):
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("This host cannot create symbolic links.")

    def test_external_symlink_is_rejected(self):
        outside = self.root / "private.txt"
        outside.write_text("private")
        self.make_link(outside, self.app / "escape")
        with self.assertRaises(PackageError):
            self.build()

    def test_internal_symlink_is_preserved(self):
        self.make_link("HouseCapture", self.app / "local-link")
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            item = archive.getinfo("Payload/HouseCapture.app/local-link")
            self.assertTrue(stat.S_ISLNK(item.external_attr >> 16))
            self.assertEqual(archive.read(item), b"HouseCapture")


if __name__ == "__main__":
    unittest.main()
