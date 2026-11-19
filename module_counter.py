import asyncio

from gdo.base.Application import Application
from gdo.base.Database import Database
from gdo.base.GDO_Module import GDO_Module
from gdo.base.Logger import Logger
from gdo.counter.GDO_Counter import GDO_Counter
from gdo.counter.GDO_CounterBatch import GDO_CounterBatch


class module_counter(GDO_Module):
    def gdo_classes(self):
        return [GDO_Counter, GDO_CounterBatch]

    def gdo_subscribe_events(self):
        Application.EVENTS.add_timer_async(300, self.flush_timer, Application.EVENTS.FOREVER)

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
