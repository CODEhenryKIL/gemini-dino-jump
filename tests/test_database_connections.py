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

    def test_sequential_connections_close_at_quiescence_and_reopen_tls(self):
        with patch.object(db.psycopg,"connect",side_effect=lambda *a,**k:FakeConnection()) as connect:
            with db.connection(self.settings) as first: pass
            with db.connection(self.settings) as second: pass
        self.assertIsNot(first,second)
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertEqual(connect.call_count,2)

    def test_completed_concurrent_wave_leaves_no_idle_connection_without_checkout(self):
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
        self.assertEqual(len(db._idle),0)
        self.assertEqual(sum(not connection.closed for connection in connections),0)

    def test_waiting_borrower_reuses_returned_connection_during_overlap(self):
        entered=threading.Barrier(9)
        release_first=threading.Event()
        release_rest=threading.Event()
        ninth_done=threading.Event()
        connections=[]

        def create(*_args,**_kwargs):
            connection=FakeConnection()
            connections.append(connection)
            return connection

        def holder(index):
            with db.connection(self.settings):
                entered.wait(timeout=5)
                (release_first if index==0 else release_rest).wait(timeout=5)

        def ninth():
            with db.connection(self.settings):pass
            ninth_done.set()

        with patch.object(db.psycopg,"connect",side_effect=create):
            with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
                holders=[executor.submit(holder,index) for index in range(8)]
                entered.wait(timeout=5)
                waiting=executor.submit(ninth)
                deadline=time.monotonic()+5
                while db._borrowers<9 and time.monotonic()<deadline:time.sleep(.001)
                self.assertEqual(db._borrowers,9)
                release_first.set()
                self.assertTrue(ninth_done.wait(timeout=5))
                release_rest.set()
                waiting.result(timeout=5)
                for future in holders:future.result(timeout=5)

        self.assertEqual(len(connections),8)
        self.assertEqual((db._borrowers,len(db._idle)),(0,0))
        self.assertTrue(all(connection.closed for connection in connections))

    def test_failed_semaphore_acquire_drains_idle_and_borrower_count(self):
        idle=FakeConnection()
        db._idle.append((("test-dsn","test"),idle,time.monotonic(),time.monotonic()))
        with patch.object(db._slots,"acquire",return_value=False):
            with self.assertRaises(db.DatabaseBusy):
                with db.connection(self.settings):pass
        self.assertTrue(idle.closed)
        self.assertEqual((db._borrowers,len(db._idle)),(0,0))

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
        self.assertEqual((live,len(db._idle)),(0,0))

    def test_failed_connect_releases_capacity_for_later_requests(self):
        with patch.object(db.psycopg,"connect",side_effect=db.psycopg.OperationalError("unavailable")):
            for _ in range(10):
                with self.assertRaises(db.psycopg.OperationalError):
                    with db.connection(self.settings): pass
        with patch.object(db.psycopg,"connect",return_value=FakeConnection()):
            with db.connection(self.settings): pass

    def test_emaxconn_admission_retries_twice_then_yields_business_body_once(self):
        attempts=[
            db.psycopg.OperationalError("(EMAXCONN) max client connections reached, limit: 200"),
            db.psycopg.OperationalError("max client connections reached"),
            FakeConnection(),
        ]
        body_calls=0
        with patch.object(db.psycopg,"connect",side_effect=attempts) as connect, \
             patch.object(db,"sleep") as pause:
            with db.connection(self.settings):
                body_calls+=1
        self.assertEqual((connect.call_count,body_calls),(3,1))
        self.assertEqual([call.args[0] for call in pause.call_args_list],[.05,.1])
        self.assertEqual((db._borrowers,len(db._idle)),(0,0))

    def test_emaxconn_exhausts_four_attempts_without_yield_and_releases_capacity(self):
        exhausted=db.psycopg.OperationalError("(EMAXCONN) max client connections reached")
        body_calls=0
        with patch.object(db.psycopg,"connect",side_effect=[exhausted]*4) as connect, \
             patch.object(db,"sleep") as pause:
            with self.assertRaises(db.psycopg.OperationalError):
                with db.connection(self.settings):body_calls+=1
        self.assertEqual((connect.call_count,body_calls),(4,0))
        self.assertEqual([call.args[0] for call in pause.call_args_list],[.05,.1,.2])
        self.assertEqual((db._borrowers,len(db._idle)),(0,0))
        with patch.object(db.psycopg,"connect",return_value=FakeConnection()):
            with db.connection(self.settings):pass

    def test_non_emaxconn_connection_errors_are_not_retried(self):
        for message in ("password authentication failed","connection timed out"):
            with self.subTest(message=message), \
                 patch.object(db.psycopg,"connect",side_effect=db.psycopg.OperationalError(message)) as connect, \
                 patch.object(db,"sleep") as pause:
                with self.assertRaises(db.psycopg.OperationalError):
                    with db.connection(self.settings):pass
                self.assertEqual(connect.call_count,1)
                pause.assert_not_called()

    def test_business_body_emaxconn_error_is_never_replayed(self):
        body_calls=0
        with patch.object(db.psycopg,"connect",return_value=FakeConnection()) as connect, \
             patch.object(db,"sleep") as pause:
            with self.assertRaises(db.psycopg.OperationalError):
                with db.connection(self.settings):
                    body_calls+=1
                    raise db.psycopg.OperationalError("(EMAXCONN) max client connections reached")
        self.assertEqual((connect.call_count,body_calls),(1,1))
        pause.assert_not_called()

    def test_emaxconn_retry_start_deadline_stops_late_attempts(self):
        error=db.psycopg.OperationalError("(EMAXCONN) max client connections reached")
        with self.subTest("first failure arrives after window"), \
             patch.object(db.psycopg,"connect",side_effect=error) as connect, \
             patch.object(db,"monotonic",side_effect=[10.0,10.8]), \
             patch.object(db,"sleep") as pause:
            with self.assertRaises(db.psycopg.OperationalError):
                db._connect("test-dsn",{})
            self.assertEqual(connect.call_count,1)
            pause.assert_not_called()

        with self.subTest("deadline expires during backoff"), \
             patch.object(db.psycopg,"connect",side_effect=error) as connect, \
             patch.object(db,"monotonic",side_effect=[20.0,20.7,20.8]), \
             patch.object(db,"sleep") as pause:
            with self.assertRaises(db.psycopg.OperationalError):
                db._connect("test-dsn",{})
            self.assertEqual(connect.call_count,1)
            pause.assert_called_once_with(.05)


if __name__=="__main__":unittest.main()
