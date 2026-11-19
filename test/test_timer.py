import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from gdo.base.Application import Application
from gdo.counter.module_counter import module_counter


class CounterTimerTest(unittest.IsolatedAsyncioTestCase):
    def test_module_count_up_delegates_to_counter(self):
        with patch('gdo.counter.Counter.Counter') as factory:
            factory.return_value.increment.return_value = 8
            self.assertEqual(8, module_counter().count_up('pagecount', 3))
            factory.return_value.increment.assert_called_once_with('pagecount', 3)

    def test_module_count_up_defaults_to_one(self):
        with patch('gdo.counter.Counter.Counter') as factory:
            module_counter().count_up('pagecount')
            factory.return_value.increment.assert_called_once_with('pagecount', 1)

    def test_timer_interval(self):
        events = MagicMock()
        events.FOREVER = 123
        with patch.object(Application, 'EVENTS', events):
            module_counter().gdo_subscribe_events()
        self.assertEqual(300, events.add_timer_async.call_args.args[0])
        self.assertEqual(123, events.add_timer_async.call_args.args[2])

    async def test_only_dog_starts_flush_worker(self):
        with patch.object(Application, 'IS_DOG', False), \
             patch('gdo.counter.module_counter.asyncio.to_thread', new_callable=AsyncMock) as worker:
            await module_counter().flush_timer()
            worker.assert_not_awaited()
        with patch.object(Application, 'IS_DOG', True), \
             patch('gdo.counter.module_counter.asyncio.to_thread', new_callable=AsyncMock) as worker:
            await module_counter().flush_timer()
            worker.assert_awaited_once()
