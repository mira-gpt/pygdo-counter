"""File-buffered counters, serialized across local processes with flock."""

import fcntl
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from gdo.base.Application import Application

KEY = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}\Z')
BATCH = re.compile(r'([0-9a-f]{32})--([a-z0-9][a-z0-9_-]{0,63})\.batch\Z')
MIN_INT = -(2 ** 63)
MAX_INT = 2 ** 63 - 1


class Counter:
    def __init__(self, directory=None, db=None):
        self.directory = Path(directory if directory is not None else Application.files_path('counter'))
        self.db = db

    @staticmethod
    def validate_key(key):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise ValueError('Counter name must be lowercase ASCII letters, digits, underscore or hyphen (1-64 characters)')
        return key

    @staticmethod
    def validate_int(value):
        if type(value) is not int or not MIN_INT <= value <= MAX_INT:
            raise ValueError('Counter step must be a signed 64-bit integer')
        return value

    @contextmanager
    def locked(self):
        try:
            self.directory.mkdir(mode=0o770, parents=True)
            os.chmod(self.directory, 0o2770)
        except FileExistsError:
            if not self.directory.is_dir():
                raise
        lock_path = self.directory / '.lock'
        try:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o660)
            os.fchmod(descriptor, 0o660)
        except FileExistsError:
            descriptor = os.open(lock_path, os.O_RDWR)
        with os.fdopen(descriptor, 'a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def sync_directory(self):
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def read_delta(self, path):
        try:
            text = path.read_text(encoding='ascii').strip()
        except FileNotFoundError:
            return 0
        if not re.fullmatch(r'-?(0|[1-9][0-9]*)', text):
            raise ValueError(f'Invalid counter file: {path.name}')
        return self.validate_int(int(text))

    def increment(self, key, step=1):
        key = self.validate_key(key)
        self.validate_int(step)
        with self.locked():
            path = self.directory / (key + '.dat')
            value = self.validate_int(self.read_delta(path) + step)
            fd, temporary = tempfile.mkstemp(prefix='.counter-', dir=self.directory)
            try:
                os.fchmod(fd, 0o660)
                with os.fdopen(fd, 'w', encoding='ascii') as output:
                    output.write(str(value) + '\n')
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
                self.sync_directory()
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return value

    def connection(self):
        return (self.db or Application.db()).get_link()

    def flush(self):
        """Commit staged files once; retain each one until commit succeeds."""
        with self.locked():
            for path in sorted(self.directory.glob('*.dat')):
                key = self.validate_key(path.name[:-4])
                self.read_delta(path)  # Refuse to move corrupt data silently.
                os.replace(path, self.directory / f'{uuid.uuid4().hex}--{key}.batch')
                self.sync_directory()
            batches = sorted(self.directory.glob('*.batch'))
            if not batches:
                return 0
            connection = self.connection()
            if connection.in_transaction:
                raise RuntimeError('Counter flush needs its own database transaction')
            count = 0
            for path in batches:
                match = BATCH.fullmatch(path.name)
                if not match:
                    raise ValueError(f'Invalid counter batch filename: {path.name}')
                batch_id, key = match.groups()
                delta = self.read_delta(path)
                cursor = connection.cursor()
                try:
                    connection.start_transaction()
                    cursor.execute('INSERT IGNORE INTO gdo_counterbatch (batch_id) VALUES (%s)', (batch_id,))
                    if cursor.rowcount:
                        cursor.execute('INSERT INTO gdo_counter (counter_name, counter_value) VALUES (%s, %s) '
                                       'ON DUPLICATE KEY UPDATE counter_value=counter_value+VALUES(counter_value)',
                                       (key, delta))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    cursor.close()
                path.unlink()
                self.sync_directory()
                count += 1
            return count

    def get(self, key):
        """Read committed plus pending increments consistently with local flushes."""
        key = self.validate_key(key)
        with self.locked():
            cursor = self.connection().cursor()
            try:
                cursor.execute('SELECT counter_value FROM gdo_counter WHERE counter_name=%s', (key,))
                row = cursor.fetchone()
                total = int(row[0]) if row else 0
                total += self.read_delta(self.directory / (key + '.dat'))
                for path in self.directory.glob('*.batch'):
                    match = BATCH.fullmatch(path.name)
                    if not match:
                        raise ValueError(f'Invalid counter batch filename: {path.name}')
                    if match.group(2) == key:
                        cursor.execute('SELECT 1 FROM gdo_counterbatch WHERE batch_id=%s', (match.group(1),))
                        if not cursor.fetchone():
                            total += self.read_delta(path)
                return self.validate_int(total)
            finally:
                cursor.close()
