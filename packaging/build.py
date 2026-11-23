"""Tests and builds a Sebayt Labs tool, with its settings in packaging/app.json.

  python packaging/build.py --tests    run the app's tests
  python packaging/build.py --deps     install what the build needs (PyInstaller, Pillow, the app's packages)
  python packaging/build.py            build the download for this system into dist/, then smoke-test it

The download is a Windows installer (.exe), a Mac disk image (.dmg) or a Linux AppImage, depending on the system it
runs on. PyInstaller can only build for the system it's on, so CI runs this on all three.
Shared by the Sebayt Labs tools: edit it in learning-kit, then run tools/sync_shared.sh there.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "packaging" / "app.json").read_text(encoding="utf-8"))
NAME = CFG["name"]
EXE = NAME.replace(" ", "")
SYSTEM = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")
ARCH = "ARM64" if platform.machine().lower() in ("arm64", "aarch64") else "X64"
VERSION = os.environ.get("APP_VERSION", "dev").lstrip("v")
BUILD, DIST = ROOT / "build", ROOT / "dist"
APPIMAGETOOL = ("1.9.1", "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0")


def run(cmd, **kw):
    print("+", cmd if isinstance(cmd, str) else " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def tests():
    for t in CFG.get("tests", []):
        t = {"cmd": t} if isinstance(t, str) else t
        if SYSTEM in t.get("os", [SYSTEM]):
            run(t["cmd"].replace("{python}", f'"{sys.executable}"'), shell=True)


def deps():
    run([sys.executable, "-m", "pip", "install", "-q", "pyinstaller>=6.11", "pillow", *CFG.get("pip", [])])


def built_program():
    if SYSTEM == "mac":
        return DIST / f"{EXE}.app" / "Contents" / "MacOS" / EXE
    return DIST / EXE / (EXE + (".exe" if SYSTEM == "windows" else ""))


def pyinstaller():
    sep = ";" if SYSTEM == "windows" else ":"
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", EXE,
            "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
            "--icon", str(ROOT / "icon.png"), "--osx-bundle-identifier", f"com.sebaytlabs.{CFG['id']}"]
    for item in ["icon.png", *CFG.get("data", [])]:
        src = ROOT / item
        dest = item if src.is_dir() else (str(Path(item).parent) if "/" in item else ".")
        args += ["--add-data", f"{src}{sep}{dest}"]
    for module in CFG.get("hidden", []):
        args += ["--hidden-import", module]
    for package in CFG.get("collect", []):
        args += ["--collect-all", package]
    run(args + [str(ROOT / CFG["entry"])])


def smoke():
    out = subprocess.run([str(built_program()), "--check", *CFG.get("check", [])], capture_output=True, text=True,
                         timeout=300)
    print(out.stdout, out.stderr)
    if out.returncode != 0 or "ok" not in out.stdout:
        sys.exit("the built program failed its --check")


def windows_installer():
    from PIL import Image
    Image.open(ROOT / "icon.png").save(BUILD / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    app_id = uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/sebaytlabs/{CFG['id']}")
    (BUILD / "setup.iss").write_text(f"""[Setup]
AppId={{{{{app_id}}}
AppName={NAME}
AppVersion={VERSION}
AppPublisher=Sebayt Labs
AppPublisherURL=https://sebaytlabs.com
DefaultDirName={{localappdata}}\\Programs\\{NAME}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={DIST}
OutputBaseFilename={EXE}-{VERSION}-windows-setup
SetupIconFile={BUILD / 'icon.ico'}
UninstallDisplayIcon={{app}}\\{EXE}.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked

[Files]
Source: "{DIST / EXE}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{{autoprograms}}\\{NAME}"; Filename: "{{app}}\\{EXE}.exe"
Name: "{{autodesktop}}\\{NAME}"; Filename: "{{app}}\\{EXE}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{EXE}.exe"; Description: "Open {NAME}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: filesandordirs; Name: "{{app}}\\_internal"
""", encoding="utf-8")
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not Path(iscc).exists():
        run(["choco", "install", "innosetup", "-y", "--no-progress"])
    run([iscc, str(BUILD / "setup.iss")])


def mac_disk_image():
    app = DIST / f"{EXE}.app"
    run(["codesign", "--force", "--deep", "--sign", "-", str(app)])
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    run(["cp", "-R", str(app), str(stage)])
    (stage / "Applications").symlink_to("/Applications")
    run(["hdiutil", "create", "-volname", NAME, "-srcfolder", str(stage), "-ov", "-format", "UDZO",
         str(DIST / f"{EXE}-{VERSION}-mac-{ARCH}.dmg")])


def linux_appimage():
    appdir = BUILD / f"{EXE}.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(DIST / EXE, appdir / EXE)
    shutil.copy(ROOT / "icon.png", appdir / f"{CFG['id']}.png")
    (appdir / f"{CFG['id']}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName={NAME}\nComment={CFG.get('comment', NAME)}\n"
        f"Exec={EXE}\nIcon={CFG['id']}\nCategories={CFG.get('categories', 'Utility;')}\nTerminal=false\n"
        f"StartupWMClass={EXE}\n", encoding="utf-8")
    apprun = appdir / "AppRun"
    apprun.write_text(f'#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/{EXE}/{EXE}" "$@"\n')
    apprun.chmod(0o755)
    version, sha = APPIMAGETOOL
    tool = BUILD / f"appimagetool-{version}-x86_64.AppImage"
    if not tool.exists():
        urllib.request.urlretrieve("https://github.com/AppImage/appimagetool/releases/download/"
                                   f"{version}/appimagetool-x86_64.AppImage", tool)
    if hashlib.sha256(tool.read_bytes()).hexdigest() != sha:  # a moved or tampered download never ships
        tool.unlink()
        sys.exit("appimagetool checksum mismatch")
    tool.chmod(0o755)
    run([str(tool), "--appimage-extract-and-run", str(appdir), str(DIST / f"{EXE}-{VERSION}-x86_64.AppImage")],
        env={**os.environ, "ARCH": "x86_64"})


def main():
    if "--tests" in sys.argv:
        return tests()
    if "--deps" in sys.argv:
        return deps()
    if SYSTEM not in CFG.get("downloads", []):
        print(f"{NAME} has no {SYSTEM} download; nothing to build.")
        return
    BUILD.mkdir(exist_ok=True)
    pyinstaller()
    smoke()
    {"windows": windows_installer, "mac": mac_disk_image, "linux": linux_appimage}[SYSTEM]()
    print("built:", *sorted(p.name for p in DIST.iterdir() if p.is_file()))


if __name__ == "__main__":
    main()
