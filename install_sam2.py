"""
install_sam2.py — helper script untuk install SAM2 package.

Script ini install SAM2 dari PyPI (cepat, tidak perlu git clone atau compile).
Variabel env SAM2_BUILD_CUDA=0 dipakai untuk skip build CUDA extension
(post-processing opsional yang butuh CUDA Toolkit + MSVC Build Tools dan bisa
bikin install hang berjam-jam di Windows). SAM2 tetap berfungsi penuh tanpa
extension ini — hanya optimasi post-processing saja yang di-skip.

Jalankan dari folder Anz-Creator:
    python install_sam2.py

Atau double-click file ini di Windows Explorer.
"""

import os
import subprocess
import sys


def _is_installed() -> bool:
    try:
        import sam2  # noqa: F401
        import sam2.build_sam  # noqa: F401

        return True
    except ImportError:
        return False


def _has_torch() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def install_sam2() -> bool:
    """Install SAM2 from PyPI. Returns True on success."""
    if _is_installed():
        print("✓ SAM2 sudah terinstall.")
        return True

    if not _has_torch():
        print("✗ PyTorch belum terinstall.")
        print("  Install dulu PyTorch dari: https://pytorch.org/get-started/locally/")
        print("  Contoh (CUDA 12.1):")
        print("    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        print("  Contoh (CPU-only):")
        print("    pip install torch torchvision")
        return False

    print("Installing SAM2 dari PyPI (1-3 menit)…")
    print("(SAM2_BUILD_CUDA=0 — skip build CUDA extension opsional)")

    env = os.environ.copy()
    env["SAM2_BUILD_CUDA"] = "0"
    env["SAM2_BUILD_ALLOW_ERRORS"] = "1"

    try:
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--no-build-isolation",
            "sam2",
        ]
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        subprocess.check_call(cmd, creationflags=creationflags, env=env)
        print("✓ SAM2 berhasil diinstall.")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"✗ Install gagal (exit code {exc.returncode})")
        print("  Coba manual:")
        print("    pip install sam2")
        print("  Atau dari GitHub (lebih lama):")
        print("    pip install git+https://github.com/facebookresearch/sam2.git")
        return False


if __name__ == "__main__":
    ok = install_sam2()
    if os.name == "nt":
        input("\nTekan Enter untuk keluar...")
    sys.exit(0 if ok else 1)
