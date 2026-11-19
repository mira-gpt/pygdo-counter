"""Opt-in integration test using connection-local temporary tables only."""
import os
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('PYGDO_COUNTER_DB_TEST') == '1', 'isolated database test is opt-in')
class CounterDatabaseTest(unittest.TestCase):
    def test_real_mariadb_flush_and_retry(self):
        from gdo.base.Application import Application
        from gdo.counter.Counter import Counter

        Application.init('/home/gizmore/www/pygdo', 'protected/pygdo_tes.toml')
        db = Application.db()
        self.assertEqual('pygdo_tes', db.db_name)
        connection = db.get_link()
        cursor = connection.cursor()
        cursor.execute('CREATE TEMPORARY TABLE gdo_counter (counter_name VARCHAR(64) PRIMARY KEY, counter_value BIGINT NOT NULL) ENGINE=InnoDB')
        cursor.execute('CREATE TEMPORARY TABLE gdo_counterbatch (batch_id VARCHAR(32) PRIMARY KEY) ENGINE=InnoDB')
        cursor.close()
        with tempfile.TemporaryDirectory() as directory:
            counter = Counter(directory, db)
            counter.increment('views', 3)
            self.assertEqual(3, counter.get('views'))
            self.assertEqual(1, counter.flush())
            counter.increment('views', -1)
            self.assertEqual(2, counter.get('views'))
            self.assertEqual(1, counter.flush())
            self.assertEqual(2, counter.get('views'))
