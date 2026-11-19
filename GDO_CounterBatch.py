from gdo.base.GDO import GDO
from gdo.core.GDT_String import GDT_String


class GDO_CounterBatch(GDO):
    """Committed batch IDs prevent a replay from counting twice."""

    def gdo_cached(self):
        return False

    def gdo_columns(self):
        return [GDT_String('batch_id').ascii().maxlen(32).primary()]
