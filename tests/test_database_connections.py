import concurrent.futures
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import db


class FakeConnection:
    def __init__(self):
        self.closed=False
        self.info=SimpleNamespace(transaction_status=db.TransactionStatus.IDLE)
        self.queries=[]
    def close(self): self.closed=True
    def execute(self,sql): self.queries.append(sql)


class ConnectionTest(unittest.TestCase):
    def setUp(self):
        db.close_idle_connections()
        self.settings=SimpleNamespace(database_url="test-dsn",environment="test")
    def tearDown(self): db.close_idle_connections()

    def test_clean_connection_is_reused_without_reopening_tls(self):
        with patch.object(db.psycopg,"connect",side_effect=lambda *a,**k:FakeConnection()) as connect:
            with db.connection(self.settings) as first: pass
            with db.connection(self.settings) as second: pass
        self.assertIs(first,second)
        self.assertEqual(connect.call_count,1)

    def test_completed_concurrent_wave_retains_only_one_idle_connection_without_checkout(self):
        entered=threading.Barrier(9)
        release=threading.Event()
        connections=[]

        def create(*_args,**_kwargs):
            connection=FakeConnection()
            connections.append(connection)
            return connection

        def run(_index):
            with db.connection(self.settings):
                entered.wait(timeout=5)
                release.wait(timeout=5)

        with patch.object(db.psycopg,"connect",side_effect=create):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures=[executor.submit(run,index) for index in range(8)]
                entered.wait(timeout=5)
                release.set()
                for future in futures:future.result(timeout=5)

        self.assertEqual(len(connections),8)
        self.assertEqual(len(db._idle),1)
        self.assertEqual(sum(not connection.closed for connection in connections),1)

    def test_failure_is_not_replayed_and_discards_connection(self):
        with patch.object(db.psycopg,"connect",side_effect=lambda *a,**k:FakeConnection()) as connect:
            with self.assertRaises(db.psycopg.OperationalError):
                with db.connection(self.settings) as failed:
                    raise db.psycopg.OperationalError("lost response")
            self.assertTrue(failed.closed)
            with db.connection(self.settings) as fresh: pass
        self.assertIsNot(fresh,failed)
        self.assertEqual(connect.call_count,2)

    def test_open_transaction_is_never_shared_with_next_request(self):
        with patch.object(db.psycopg,"connect",side_effect=lambda *a,**k:FakeConnection()):
            with db.connection(self.settings) as leaked:
                leaked.info.transaction_status=db.TransactionStatus.INTRANS
            self.assertTrue(leaked.closed)
            with db.connection(self.settings) as fresh: self.assertIsNot(fresh,leaked)

    def test_different_database_or_environment_never_reuses_connection(self):
        with patch.object(db.psycopg,"connect",side_effect=lambda *a,**k:FakeConnection()):
            with db.connection(self.settings) as first: pass
            with db.connection(SimpleNamespace(database_url="other-dsn",environment="test")) as second: pass
        self.assertTrue(first.closed)
        self.assertIsNot(first,second)

    def test_stale_socket_is_checked_before_business_code(self):
        dead=FakeConnection()
        dead.execute=lambda _: (_ for _ in ()).throw(db.psycopg.OperationalError("closed"))
        db._idle.append((("test-dsn","test"),dead,time.monotonic()-10,time.monotonic()-10))
        with patch.object(db.psycopg,"connect",return_value=FakeConnection()) as connect:
            with db.connection(self.settings) as fresh: self.assertIsNot(dead,fresh)
        self.assertTrue(dead.closed)
        self.assertEqual(connect.call_count,1)

    def test_expired_connection_is_closed(self):
        old=FakeConnection()
        db._idle.append((("test-dsn","test"),old,time.monotonic()-301,time.monotonic()))
        with patch.object(db.psycopg,"connect",return_value=FakeConnection()):
            with db.connection(self.settings) as fresh: self.assertIsNot(old,fresh)
        self.assertTrue(old.closed)

    def test_concurrent_requests_have_exclusive_connections_and_bounded_count(self):
        active=set();lock=threading.Lock();maximum=0;live=0;peak_live=0
        def create(*_args,**_kwargs):
            nonlocal live,peak_live
            connection=FakeConnection()
            original_close=connection.close
            with lock:
                live+=1
                peak_live=max(peak_live,live)
            def close():
                nonlocal live
                with lock:
                    if not connection.closed:live-=1
                original_close()
            connection.close=close
            return connection
        def run(_):
            nonlocal maximum
            with db.connection(self.settings) as conn:
                with lock:
                    self.assertNotIn(id(conn),active)
                    active.add(id(conn));maximum=max(maximum,len(active))
                time.sleep(.02)
                with lock: active.remove(id(conn))
        with patch.object(db.psycopg,"connect",side_effect=create):
            with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executor: list(executor.map(run,range(48)))
        self.assertGreater(maximum,2)
        self.assertLessEqual(maximum,8)
        self.assertLessEqual(peak_live,8)
        self.assertEqual((live,len(db._idle)),(1,1))

    def test_failed_connect_releases_capacity_for_later_requests(self):
        with patch.object(db.psycopg,"connect",side_effect=db.psycopg.OperationalError("unavailable")):
            for _ in range(10):
                with self.assertRaises(db.psycopg.OperationalError):
                    with db.connection(self.settings): pass
        with patch.object(db.psycopg,"connect",return_value=FakeConnection()):
            with db.connection(self.settings): pass


if __name__=="__main__":unittest.main()
