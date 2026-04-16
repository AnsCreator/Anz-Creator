import os
import requests
from pathlib import Path
from typing import Callable, Optional

class ModelManager:
    # ... (init logic memuat config.yaml model) ...

    def list_variants(self, family: str) -> list[dict]:
        """Menghasilkan daftar {name, description, size_mb, downloaded} untuk UI."""
        try:
            opts = self._cfg.get("models", {}).get(family, {}).get("options", {})
        except (AttributeError, TypeError):
            return []
        
        out = []
        for name, info in opts.items():
            if not isinstance(info, dict):
                continue
            out.append({
                "name": name,
                "description": info.get("description", ""),
                "size_mb": info.get("size_mb", 0),
                "downloaded": self.is_downloaded(family, name),
            })
        return out

    def download(
        self,
        family: str,
        variant: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Mengunduh model dan melaporkan persentase via progress_callback."""
        dest = self.model_path(family, variant)
        url = self.get_url(family, variant)
        size_mb = self.get_size_mb(family, variant)

        # Jika sudah ada, langsung kembalikan 100%
        if self.is_downloaded(family, variant):
            if progress_callback:
                progress_callback(100, f"{variant} ready.")
            return dest

        with self._download_lock:
            Path(os.path.dirname(dest)).mkdir(parents=True, exist_ok=True)
            tmp = dest + ".part"
            
            if progress_callback:
                progress_callback(0, f"Downloading {variant}…")

            try:
                resp = requests.get(url, stream=True, timeout=(15, 30))
                resp.raise_for_status()

                total = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if cancel_flag and cancel_flag():
                            f.close()
                            if os.path.exists(tmp): os.remove(tmp)
                            return ""
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Hitung dan kirim persentase ke UI
                        if total > 0 and progress_callback:
                            pct = int(downloaded / total * 100)
                            progress_callback(
                                pct,
                                f"Downloading {variant}… {downloaded // 1048576}/{total // 1048576} MB",
                            )

                os.rename(tmp, dest)
                if progress_callback:
                    progress_callback(100, f"{variant} ready.")
                return dest

            except Exception as exc:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise
