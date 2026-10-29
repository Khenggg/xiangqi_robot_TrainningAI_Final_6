"""Atomic durable rollback checkpoints; a corrupt journal locks recovery."""
import json
import os
from pathlib import Path
import tempfile


class JournalError(RuntimeError):
    pass


class RollbackJournal:
    def __init__(self, path):
        self.path = Path(path)

    def save(self, record):
        if not isinstance(record, dict):
            raise JournalError('Rollback journal must contain an object')
        temporary = None
        try:
            encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                    dir=self.path.parent, prefix=self.path.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            # POSIX directory fsync protects rename durability. Windows does not
            # expose opening directories through os.open; file fsync still applies.
            if os.name != 'nt':
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except (OSError, ValueError, TypeError) as exc:
            raise JournalError('Cannot persist rollback checkpoint') from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def load(self):
        try:
            with self.path.open(encoding='utf-8') as stream:
                record = json.load(stream)
            if not isinstance(record, dict):
                raise ValueError('Expected a JSON object')
            return record
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as exc:
            raise JournalError('Rollback journal unreadable; recovery required') from exc

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise JournalError('Cannot clear rollback checkpoint') from exc
