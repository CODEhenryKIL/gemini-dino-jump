from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import app
from operations import DomainError


class RateLimitBucketTest(unittest.TestCase):
    def setUp(self):
        self.handler=object.__new__(app.DinoJumpHandler)
        self.settings=SimpleNamespace(token_pepper="x"*32)
        self.ip_hash="a"*64

    def buckets(self,path,participant="",allowed=True):
        with patch.object(self.handler,"_ip_subject",return_value=self.ip_hash), \
             patch.object(app.db,"rate_limits",return_value=allowed) as limited:
            self.handler._rate(object(),self.settings,path,participant)
        return limited.call_args.args[1]

    def test_sixteen_shards_preserve_the_single_12000_request_ip_budget(self):
        buckets=[self.buckets("/api/me",hex_digit+"0"*63)[0] for hex_digit in "0123456789abcdef"]
        self.assertEqual(len({key for key,_limit in buckets}),16)
        self.assertEqual(sum(limit for _key,limit in buckets),12000)
        self.assertEqual({limit for _key,limit in buckets},{750})

    def test_anonymous_and_admin_use_the_same_ip_shard_family(self):
        anonymous=self.buckets("/api/participants/anonymous")[0]
        admin=self.buckets("/api/admin/overview")[0]
        self.assertEqual(anonymous,admin)
        self.assertEqual(anonymous,("ip:"+self.ip_hash+":"+self.ip_hash[0],750))

    def test_participant_shard_mapping_is_stable(self):
        participant="f"+"1"*63
        first=self.buckets("/api/me",participant)[0]
        second=self.buckets("/api/me",participant)[0]
        self.assertEqual(first,second)
        self.assertEqual(first,("ip:"+self.ip_hash+":f",750))

    def test_route_subjects_and_existing_limits_are_unchanged(self):
        participant="b"+"2"*63
        cases=[
          ("/api/participants/anonymous","",240,self.ip_hash),
          ("/api/admin/overview","",90,self.ip_hash),
          ("/api/game-sessions/session/finish",participant,30,participant),
          ("/api/me",participant,180,participant),
        ]
        for path,subject,expected_limit,expected_subject in cases:
            with self.subTest(path=path):
                route=self.buckets(path,subject)[1]
                self.assertEqual(route,("route:"+path+":"+expected_subject,expected_limit))

    def test_database_rejection_remains_a_retryable_429(self):
        with self.assertRaises(DomainError) as raised:
            self.buckets("/api/me","c"+"3"*63,allowed=False)
        self.assertEqual((raised.exception.code,raised.exception.status,raised.exception.retryable),("RATE_LIMITED",429,True))


if __name__=="__main__":unittest.main()
