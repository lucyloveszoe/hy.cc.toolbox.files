import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import glacier_restore as r
from botocore.exceptions import ClientError


class FakeS3:
    def __init__(self, objs, restore=None, raise_on=None):
        self.objs, self.state, self.raise_on = objs, restore or {}, raise_on
        self.calls = []

    def get_paginator(self, _):
        outer = self
        class P:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [o for o in outer.objs if o["Key"].startswith(Prefix)]}
        return P()

    def head_object(self, Bucket, Key):
        if Key == getattr(self, "head_fail", None):
            raise ClientError({"Error": {"Code": "403"}}, "HeadObject")
        return {"Restore": self.state.get(Key, "")}

    def restore_object(self, Bucket, Key, RestoreRequest):
        if Key == self.raise_on:
            raise ClientError({"Error": {"Code": "RestoreAlreadyInProgress"}}, "RestoreObject")
        self.calls.append((Key, RestoreRequest))


OBJS = [
    {"Key": "p/new.jpg", "Size": 1, "StorageClass": "GLACIER"},
    {"Key": "p/Thumbs.db", "Size": 1, "StorageClass": "GLACIER"},
    {"Key": "p/done.jpg", "Size": 1, "StorageClass": "DEEP_ARCHIVE"},
    {"Key": "p/wip.jpg", "Size": 1, "StorageClass": "GLACIER"},
    {"Key": "p/std.jpg", "Size": 1, "StorageClass": "STANDARD"},
]
STATE = {"p/done.jpg": 'ongoing-request="false", expiry-date="x"',
         "p/wip.jpg": 'ongoing-request="true"'}


def test_preview_requests_nothing():
    c = FakeS3(OBJS, STATE)
    st = r.restore_prefix(c, "b", "p", ["Thumbs.db"], 7, "Bulk", execute=False)
    assert c.calls == [] and st.requested == 1


def test_execute():
    c = FakeS3(OBJS, STATE)
    st = r.restore_prefix(c, "b", "p", ["Thumbs.db"], 7, "Bulk", execute=True)
    assert c.calls == [("p/new.jpg", {"Days": 7, "GlacierJobParameters": {"Tier": "Bulk"}})]
    assert (st.requested, st.excluded, st.already_restored, st.in_progress, st.not_archived) \
        == (1, 1, 1, 1, 1)


def test_already_in_progress_error_is_not_failure():
    c = FakeS3(OBJS, STATE, raise_on="p/new.jpg")
    st = r.restore_prefix(c, "b", "p", ["Thumbs.db"], 7, "Bulk", execute=True)
    assert st.failed == [] and st.in_progress == 2 and st.requested == 0


def test_failures_do_not_stop_run():
    objs = OBJS + [{"Key": "p/z.jpg", "Size": 1, "StorageClass": "GLACIER"},
                   {"Key": "p/y.jpg", "Size": 1, "StorageClass": "GLACIER"}]
    c = FakeS3(objs, STATE)
    c.head_fail = "p/new.jpg"           # head fails on the first candidate
    orig = c.restore_object
    def flaky(Bucket, Key, RestoreRequest):
        if Key == "p/z.jpg":
            raise ClientError({"Error": {"Code": "InternalError"}}, "RestoreObject")
        orig(Bucket, Key, RestoreRequest)
    c.restore_object = flaky
    st = r.restore_prefix(c, "b", "p", ["Thumbs.db"], 7, "Bulk", execute=True)
    assert [k for k, _ in c.calls] == ["p/y.jpg"]
    assert len(st.failed) == 2 and st.requested == 1


def test_recursive_deep_nesting():
    objs = [{"Key": f"p/{d}/f.jpg", "Size": 1, "StorageClass": "GLACIER"}
            for d in ("a", "a/b", "a/b/c/d/e")]
    objs.append({"Key": "other/x.jpg", "Size": 1, "StorageClass": "GLACIER"})  # outside prefix
    c = FakeS3(objs)
    st = r.restore_prefix(c, "b", "p", [], 7, "Bulk", execute=True)
    assert [k for k, _ in c.calls] == ["p/a/f.jpg", "p/a/b/f.jpg", "p/a/b/c/d/e/f.jpg"]
    assert st.requested == 3
