import tempfile
import threading
import unittest
import multiprocessing
from pathlib import Path
from unittest.mock import patch

from gdo.counter.Counter import Counter


def count_in_process(directory, count):
    counter = Counter(directory)
    for _ in range(count):
        counter.increment('hits')


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self.result = None

    def execute(self, sql, args):
        c = self.connection
        if sql.startswith('INSERT IGNORE'):
            batch = args[0]
            self.rowcount = int(batch not in c.batches)
            c.batches.add(batch)
        elif sql.startswith('INSERT INTO gdo_counter '):
            if c.fail_update:
                raise RuntimeError('database unavailable')
            key, delta = args
            c.values[key] = c.values.get(key, 0) + delta
        elif sql.startswith('SELECT counter_value'):
            value = c.values.get(args[0])
            self.result = (value,) if value is not None else None
        elif sql.startswith('SELECT 1'):
            self.result = (1,) if args[0] in c.batches else None
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.result

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.values = {}
        self.batches = set()
        self.in_transaction = False
        self.fail_update = False

    def cursor(self):
        return FakeCursor(self)

    def start_transaction(self):
        self.snapshot = self.values.copy(), self.batches.copy()
        self.in_transaction = True

    def commit(self):
        self.in_transaction = False

    def rollback(self):
        self.values, self.batches = self.snapshot
        self.in_transaction = False

    def get_link(self):
        return self


class CounterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = FakeConnection()
        self.counter = Counter(self.temp.name, self.db)

    def test_counts_and_flushes_signed_steps(self):
        self.counter.increment('visits', 5)
        self.counter.increment('visits', -2)
        self.assertEqual(3, self.counter.get('visits'))
        self.assertEqual(1, self.counter.flush())
        self.assertEqual(3, self.db.values['visits'])
        self.assertEqual(3, self.counter.get('visits'))
        self.assertEqual(0, self.counter.flush())

    def test_pending_and_lock_files_allow_shared_group_access(self):
        self.counter.increment('hits')
        self.assertEqual(0o660, (Path(self.temp.name) / 'hits.dat').stat().st_mode & 0o777)
        self.assertEqual(0o660, (Path(self.temp.name) / '.lock').stat().st_mode & 0o777)

    def test_failed_database_write_retains_batch_for_retry(self):
        self.counter.increment('hits', 7)
        self.db.fail_update = True
        with self.assertRaises(RuntimeError):
            self.counter.flush()
        self.assertEqual(7, self.counter.get('hits'))
        self.db.fail_update = False
        self.counter.flush()
        self.assertEqual(7, self.counter.get('hits'))

    def test_crash_after_commit_does_not_double_count(self):
        self.counter.increment('hits', 4)
        with patch.object(Path, 'unlink', side_effect=OSError('simulated crash')):
            with self.assertRaises(OSError):
                self.counter.flush()
        self.assertEqual(4, self.counter.get('hits'))
        self.counter.flush()
        self.assertEqual(4, self.db.values['hits'])

    def test_concurrent_increments_do_not_get_lost(self):
        threads = [threading.Thread(target=lambda: [self.counter.increment('hits') for _ in range(20)]) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(80, self.counter.get('hits'))

    def test_separate_processes_share_the_lock(self):
        processes = [multiprocessing.Process(target=count_in_process, args=(self.temp.name, 20)) for _ in range(3)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(0, process.exitcode)
        self.assertEqual(60, self.counter.get('hits'))

    def test_corrupt_data_is_not_discarded(self):
        path = Path(self.temp.name) / 'hits.dat'
        path.write_text('not a count', encoding='ascii')
        with self.assertRaises(ValueError):
            self.counter.flush()
        self.assertTrue(path.is_file())

    def test_invalid_name_and_step_are_rejected(self):
        for key in ('../escape', 'A', '', 'has space'):
            with self.assertRaises(ValueError):
                self.counter.increment(key)
        for value in (True, 1.5, 2 ** 63):
            with self.assertRaises(ValueError):
                self.counter.increment('valid', value)
