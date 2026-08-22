"""Cross-platform exclusive watch-loop lock.

Uses fcntl on POSIX and msvcrt on Windows to prevent two watch loops
(CLI or TUI) from running concurrently in the same project directory.
"""

import contextlib
import os
import sys
from typing import Optional


class WatchLockHeldError(RuntimeError):
    """Raised when another watch loop (CLI or TUI) already holds the lock."""


@contextlib.contextmanager
def acquire_watch_lock(lock_path: Optional[str] = None):
    """Exclusively claim the watch lock; fails fast if another watcher holds it.

    lock_path defaults to $FLOWJOB_WATCH_LOCK or ".flowjob-watch.lock". The
    lock is released automatically when the context exits or if the owning
    process dies.
    """
    if lock_path is None:
        lock_path = os.environ.get("FLOWJOB_WATCH_LOCK", ".flowjob-watch.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    _closed = False
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                os.close(fd)
                _closed = True
                raise WatchLockHeldError(
                    f"Watch lock held at {lock_path} — another watcher (CLI or TUI) is running."
                ) from None
            try:
                yield fd
            finally:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                _closed = True
                raise WatchLockHeldError(
                    f"Watch lock held at {lock_path} — another watcher (CLI or TUI) is running."
                ) from None
            yield fd
    finally:
        if not _closed:
            try:
                os.close(fd)
            except OSError:
                pass