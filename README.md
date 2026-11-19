# PyGDO Counter

Count named values in signed 64-bit integer steps. Increments are buffered in
`files/counter/<name>.dat` (under the configured `dir.files`), then persisted
in `GDO_Counter` by Dog every 300 seconds. This module does not use Redis.

Install the module with the PyGDO module installer. In Python:

```python
from gdo.counter.Counter import Counter

counter = Counter()
counter.increment('page-visits')       # add one
counter.increment('page-visits', 5)    # signed integer steps also supported
total = counter.get('page-visits')      # database plus unflushed increments
counter.flush()                        # optional explicit synchronous flush
```

Names contain 1–64 lowercase ASCII letters, digits, underscores or hyphens,
starting with a letter or digit. Names are not private; do not put secrets or
personal data in them. The module exposes no public increment endpoint.

An OS lock serializes local writers, readers and flushes. Increment files are
atomically replaced and synced; flushes rename them to uniquely identified
batches. A database transaction records each batch ID and applies its delta
once, so retry after a crash or uncertain database commit cannot double-count.
The batch ledger grows over time and must not be cleared while any batch files
or backups might be replayed. Failed flushes leave batches on disk for retry.

All writers must share the same local filesystem and database, with working
flock, rename and fsync semantics. Web and Dog users must share the owning
group and have access to the configured files directory; the newly created
counter directory uses its creator's group and setgid, and files are
group-writable. Restrict that group to trusted local processes.
Do not use per-host directories in a
multi-host deployment. Back up the counter directory and database together;
deleting files or restoring inconsistent snapshots can lose or replay data.
Increments require disk access and can fail; a filesystem failure after a
rename may leave the operation's outcome uncertain. A database outage prevents
reads and flushes but does not prevent buffering new increments. The five-minute
schedule requires Dog to be running; no service is started by installation.
