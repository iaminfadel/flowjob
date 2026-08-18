import os
import contextlib
import fcntl


class WatchLockHeldError(RuntimeError):
    """Raised when another watch loop (CLI or TUI) already holds the lock."""


@contextlib.contextmanager
def acquire_watch_lock(lock_path: str = ".flowjob-watch.lock"):
    """Exclusively claim the watch lock; fails fast if another watcher holds it.

    The lock is released automatically if the owning process dies.
    """
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise WatchLockHeldError(
                f"Watch lock held at {lock_path} — another watcher (CLI or TUI) is running."
            ) from None
        yield fd
    finally:
        os.close(fd)