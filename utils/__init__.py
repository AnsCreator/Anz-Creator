from .logger import log  # noqa: F401


def pip_install(package: str, quiet: bool = True) -> bool:
    """Install a pip package programmatically."""
    import os
    import subprocess
    import sys

    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if quiet:
            cmd.append("-q")
        cmd.append(package)

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.check_call(cmd, creationflags=creationflags)
        return True
    except Exception:
        return False
