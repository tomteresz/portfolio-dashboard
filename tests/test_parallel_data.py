"""Concurrency and exception behavior of independent market reads."""
from threading import Barrier
import unittest

from portfolio_app.parallel_data import parallel_loads


class ParallelDataTests(unittest.TestCase):
    def test_independent_reads_overlap_and_preserve_results(self):
        barrier = Barrier(4, timeout=5)

        def load(value):
            barrier.wait()
            return value

        with parallel_loads({str(i): lambda i=i: load(i) for i in range(4)}) as pending:
            self.assertEqual({key: task.result() for key, task in pending.items()},
                             {str(i): i for i in range(4)})

    def test_failure_does_not_discard_other_results(self):
        def unavailable():
            raise ValueError('offline')

        with parallel_loads({'failed': unavailable, 'working': lambda: 42}) as pending:
            with self.assertRaisesRegex(ValueError, 'offline'):
                pending['failed'].result()
            self.assertEqual(pending['working'].result(), 42)

    def test_empty_loaders(self):
        with parallel_loads({}) as pending:
            self.assertEqual(pending, {})
