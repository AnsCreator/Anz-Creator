"""
clean_partial_downloads.py — hapus file download yang gagal/tidak lengkap.

Kalau sebelumnya Anda pernah error download model (misal 401 Unauthorized
dari HuggingFace), mungkin ada file .part yang tersisa di folder model.
Script ini hapus semua file .part di direktori model Anz-Creator.

Jalankan dengan:
    python clean_partial_downloads.py
"""

import os
import sys


def clean_partial_files():
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    models_dir = os.path.join(appdata, "Anz-Creator", "models")

    if not os.path.isdir(models_dir):
        print(f"Direktori model tidak ditemukan: {models_dir}")
        return 0

    removed = 0
    for root, _, files in os.walk(models_dir):
        for fn in files:
            if fn.endswith(".part"):
                path = os.path.join(root, fn)
                try:
                    size = os.path.getsize(path)
                    os.remove(path)
                    print(f"Dihapus: {path} ({size:,} bytes)")
                    removed += 1
                except OSError as exc:
                    print(f"Gagal hapus {path}: {exc}")
    if removed == 0:
        print(f"Tidak ada file .part di {models_dir}")
    else:
        print(f"\nTotal {removed} file .part dihapus.")
    return removed


if __name__ == "__main__":
    clean_partial_files()
    if os.name == "nt":
        input("\nTekan Enter untuk keluar...")
    sys.exit(0)
