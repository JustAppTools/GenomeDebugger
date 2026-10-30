"""Process-lifetime ownership of one resolved database, independent of port."""
import os
from pathlib import Path


class WorkspaceInUseError(ValueError):
    pass


class WorkspaceLock:
    def __init__(self, database: Path):
        self.path = Path(str(database.resolve()) + '.lock')
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        try:
            if self.path.stat().st_size == 0:
                self.file.write(b'\0')
                self.file.flush()
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise WorkspaceInUseError('Workspace is in use. Stop every GenomeDebugger instance using this database before restoring or starting another server.') from exc
        return self

    def __exit__(self, *_):
        if self.file is not None:
            # Closing releases the operating-system lock, including after crashes.
            # Keep the lock file: unlinking it can let another process lock a
            # different file while an existing owner still holds the old one.
            self.file.close()
            self.file = None
