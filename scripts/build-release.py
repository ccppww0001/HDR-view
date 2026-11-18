"""构建带原生编码组件与许可证文本的 Windows 单文件发行版。"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "hdrview"
NATIVE_BUILD = PACKAGE / "native" / "build"
BRIDGES = ("hdrview-ultrahdr.exe", "hdrview-jxr.exe")


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def collect_licenses(target: Path) -> None:
    copy(ROOT / "LICENSE", target / "HDR-view" / "LICENSE")
    copy(Path(sys.base_prefix) / "LICENSE.txt", target / "Python" / "LICENSE.txt")

    for name in ("numpy", "Pillow", "opencv-python-headless", "pyinstaller", "packaging"):
        distribution = importlib.metadata.distribution(name)
        for item in distribution.files or ():
            if not item.parts[0].endswith(".dist-info"):
                continue
            relative = Path(*item.parts[1:])
            if relative.parts[0] == "licenses" or relative.name.upper().startswith(("LICENSE", "NOTICE", "COPYING")):
                copy(distribution.locate_file(item), target / name / relative)

    cache = (NATIVE_BUILD / "CMakeCache.txt").read_text(encoding="utf-8")
    locations = {}
    for line in cache.splitlines():
        key, _, value = line.partition("=")
        variable = key.split(":", 1)[0]
        if variable in {"UHDR_SOURCE_DIR", "JPEG_SOURCE_DIR"} and value:
            locations[variable] = Path(value)

    for variable, directory, notices in (
        ("UHDR_SOURCE_DIR", "libultrahdr", ("LICENSE", "LICENSE-APACHE", "LICENSE-MIT")),
        ("JPEG_SOURCE_DIR", "libjpeg-turbo", ("LICENSE.md", "README.ijg")),
    ):
        for name in notices:
            copy(locations[variable] / name, target / directory / name)


def main() -> None:
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise SystemExit("发行版构建需要 64 位 Windows Python")
    encoders = [NATIVE_BUILD / "Release" / name for name in BRIDGES]
    if any(not encoder.is_file() for encoder in encoders):
        raise SystemExit("请先执行 src/hdrview/native/Build-Native.ps1 构建编码组件")

    with TemporaryDirectory(prefix="hdrview-release-") as directory:
        workspace = Path(directory)
        licenses = workspace / "licenses"
        collect_licenses(licenses)

        # 保留同版本源码供已安装 NVIDIA 运行库的独立 Python 解释器使用。
        source = workspace / "source" / "hdrview"
        for file in PACKAGE.rglob("*.py"):
            relative = file.relative_to(PACKAGE)
            if relative.parts[0] != "native":
                copy(file, source / relative)
        for encoder in encoders:
            copy(encoder, source / "native" / "build" / "Release" / encoder.name)

        command = [
            sys.executable, "-m", "PyInstaller", "--onefile", "--console", "--noupx",
            "--name", "HDR-view", "--paths", str(PACKAGE.parent),
            "--workpath", str(workspace / "work"), "--specpath", str(workspace),
            "--distpath", str(workspace / "dist"),
            "--add-data", f"{licenses}:licenses",
            "--add-data", f"{source.parent}:source",
            "--exclude-module", "torch", "--exclude-module", "nvvfx",
        ]
        for encoder in encoders:
            command += ["--add-binary", f"{encoder}:hdrview/native/build/Release"]
        command.append(str(PACKAGE / "release.py"))
        subprocess.run(command, cwd=ROOT, check=True)

        output = ROOT / "dist" / "HDR-view.exe"
        copy(workspace / "dist" / output.name, output)
    print(output)


if __name__ == "__main__":
    main()
