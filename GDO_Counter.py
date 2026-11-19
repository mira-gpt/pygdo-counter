from gdo.base.GDO import GDO
from gdo.core.GDT_Int import GDT_Int
from gdo.core.GDT_String import GDT_String


class GDO_Counter(GDO):
    def gdo_cached(self):
        return False

    def gdo_columns(self):
        return [GDT_String('counter_name').ascii().maxlen(64).primary(),
                GDT_Int('counter_value').bytes(8).not_null().initial('0')]
