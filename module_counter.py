import asyncio

from gdo.base.Application import Application
from gdo.base.Database import Database
from gdo.base.GDO_Module import GDO_Module
from gdo.base.Logger import Logger
from gdo.base.Trans import t
from gdo.counter.GDO_Counter import GDO_Counter
from gdo.counter.GDO_CounterBatch import GDO_CounterBatch
from gdo.core.GDT_Enum import GDT_Enum
from gdo.message.GDT_HTML import GDT_HTML


class module_counter(GDO_Module):
    PAGE_BARS = {
        'title': '_title_bar', 'top': '_top_bar', 'left': '_left_bar',
        'right': '_right_bar', 'bottom': '_bottom_bar',
    }

    def __init__(self):
        super().__init__()
        self._priority = 100

    def gdo_classes(self):
        return [GDO_Counter, GDO_CounterBatch]

    def gdo_module_config(self):
        return [GDT_Enum('counter_pagecount').choices({
            name: name.title() for name in self.PAGE_BARS
        })]

    def count_up(self, name: str, step: int = 1) -> int:
        """Buffer an integer step and return the current pending-file value."""
        from gdo.counter.Counter import Counter
        return Counter().increment(name, step)

    def gdo_subscribe_events(self):
        Application.EVENTS.subscribe('user_request', self.on_user_request)
        Application.EVENTS.subscribe('http_response_headers', self.on_response_headers)
        Application.EVENTS.add_timer_async(300, self.flush_timer, Application.EVENTS.FOREVER)

    def on_user_request(self, _user):
        self.count_page_request()

    def on_response_headers(self):
        self.count_page_request()

    def count_page_request(self):
        if not Application.IS_HTTP or not self.get_config_val('counter_pagecount'):
            return
        if Application.get_request_method() != 'GET':
            return
        environ = Application.storage('environ')
        if environ is None or environ.get('pygdo.counter.pagecount.counted'):
            return
        # A failed atomic write can have an uncertain outcome; do not retry it
        # later in this same request and risk counting it twice.
        environ['pygdo.counter.pagecount.counted'] = True
        try:
            self.count_up('pagecount')
        except Exception as error:
            Logger.exception(error, 'Pagecount increment failed')

    def gdo_init_sidebar(self, page):
        position = self.get_config_val('counter_pagecount')
        if position not in self.PAGE_BARS:
            return
        self.count_page_request()
        try:
            from gdo.counter.Counter import Counter
            total = Counter().get('pagecount')
            getattr(page, self.PAGE_BARS[position]).add_field(
                GDT_HTML().text(t('counter_pagecount_display', (total,))))
        except Exception as error:
            Logger.exception(error, 'Pagecount display failed')

    async def flush_timer(self):
        if Application.IS_DOG:
            try:
                await asyncio.to_thread(self.flush_worker)
            except Exception as error:
                Logger.exception(error, 'Counter flush failed; pending files retained')

    @staticmethod
    def flush_worker():
        from gdo.counter.Counter import Counter
        config = Application.CONFIG['db']
        db = Database(config['host'], config['name'], config['user'], config['pass'])
        try:
            return Counter(db=db).flush()
        finally:
            if db.link is not None:
                db.link.close()
                db.link = None
