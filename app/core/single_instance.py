from pathlib import Path
from PyQt6.QtCore import QLockFile, QDir

_lock = None

def acquire(app_name, lock_dir):
    global _lock
    p = Path(lock_dir) / f"{app_name}.lock"
    QDir(str(p.parent)).mkpath(".")
    lock = QLockFile(str(p))
    lock.setStaleLockTime(0)

    if not lock.tryLock(0):
        return False

    _lock = lock
    return True