"""
install_sam2.py — helper script untuk install SAM2 package.

SAM2 tidak tersedia di PyPI. Script ini install dari GitHub repo resmi
facebookresearch/sam2.

Jalankan dari folder Anz-Creator:
    python install_sam2.py

Atau double-click file ini di Windows Explorer.
"""

import os
import subprocess
import sys

SAM2_REPO_URL = "git+https://github.com/facebookresearch/sam2.git"


def _is_installed() -> bool:
    try:
        import sam2  # noqa: F401
        import sam2.build_sam  # noqa: F401
        return True
    except ImportError:
        return False


def _has_git() -> bool:
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.check_call(
            ["git", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def install_sam2() -> bool:
    """Install SAM2 from GitHub. Returns True on success."""
    if _is_installed():
        print("✓ SAM2 sudah terinstall.")
        return True

    if not _has_git():
        print("✗ Git tidak ditemukan di PATH.")
        print("  Install git dari: https://git-scm.com/download/win")
        return False

    if not _has_torch():
        print("✗ PyTorch belum terinstall.")
        print("  Install dulu PyTorch dari: https://pytorch.org/get-started/locally/")
        print("  Contoh (CUDA 12.1):")
        print("    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        return False

    print(f"Installing SAM2 dari {SAM2_REPO_URL} ...")
    print("(Ini butuh beberapa menit karena compile extension CUDA)")
    try:
        cmd = [sys.executable, "-m", "pip", "install", "--no-build-isolation", SAM2_REPO_URL]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.check_call(cmd, creationflags=creationflags)
        print("✓ SAM2 berhasil diinstall.")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"✗ Install gagal (exit code {exc.returncode})")
        print("  Coba manual:")
        print(f"    pip install {SAM2_REPO_URL}")
        return False


if __name__ == "__main__":
    ok = install_sam2()
    if os.name == "nt":
        input("\nTekan Enter untuk keluar...")
    sys.exit(0 if ok else 1)
