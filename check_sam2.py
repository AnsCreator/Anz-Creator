"""
check_sam2.py — diagnostic tool untuk cek status install SAM2.

Jalankan dari folder Anz-Creator:
    python check_sam2.py

Script ini akan memberi tahu:
- Apakah SAM2 terinstall sebagai paket pip
- Di path mana SAM2 terinstall
- Apakah bisa di-import dengan benar
- Apakah torch tersedia (SAM2 butuh torch)
"""

import os
import sys


def check():
    print("=" * 60)
    print("SAM2 Installation Diagnostic")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")
    print()

    # 1. Check if torch is available
    print("[1/4] Checking PyTorch...")
    try:
        import torch

        print(f"  ✓ torch {torch.__version__}")
        print(f"  CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  CUDA device: {torch.cuda.get_device_name(0)}")
    except ImportError as e:
        print(f"  ✗ torch NOT installed: {e}")
        print("  Install: pip install torch torchvision")
        print()
        return False
    print()

    # 2. Check pip install status
    print("[2/4] Checking pip install status...")
    try:
        import importlib.metadata as md
    except ImportError:
        import importlib_metadata as md  # type: ignore[import-not-found]

    found = False
    for name in ("SAM-2", "sam2", "segment-anything-2"):
        try:
            dist = md.distribution(name)
            print(f"  ✓ Distribution: {dist.name} v{dist.version}")
            try:
                loc = dist.locate_file("")
                print(f"    Location: {loc}")
            except Exception:
                pass
            found = True
            break
        except md.PackageNotFoundError:
            continue

    if not found:
        print("  ✗ SAM2 package NOT found via pip")
        print("  Install: pip install git+https://github.com/facebookresearch/sam2.git")
        print()
        return False
    print()

    # 3. Try importing sam2
    print("[3/4] Trying to import sam2...")
    try:
        import sam2

        print(f"  ✓ sam2 imported from: {os.path.dirname(sam2.__file__)}")
    except ImportError as e:
        print(f"  ✗ Cannot import sam2: {e}")
        print()
        return False
    print()

    # 4. Try importing sam2.build_sam
    print("[4/4] Trying to import sam2.build_sam...")
    try:
        import sam2.build_sam  # noqa: F401

        print("  ✓ sam2.build_sam import OK")
    except ImportError as e:
        print(f"  ✗ Cannot import sam2.build_sam: {e}")
        print()
        return False
    except Exception as e:
        print(f"  ✗ Error during import: {type(e).__name__}: {e}")
        print()
        return False
    print()

    print("=" * 60)
    print("✓ SAM2 is READY TO USE")
    print("=" * 60)
    return True


if __name__ == "__main__":
    ok = check()
    if os.name == "nt":
        input("\nTekan Enter untuk keluar...")
    sys.exit(0 if ok else 1)
