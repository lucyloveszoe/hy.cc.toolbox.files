import sys
from pathlib import Path

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import s3_mirror as g


class FakeS3:
    def __init__(self, objs, restore=None):
        self.objs, self.restore = objs, restore or {}
        self.got = []

    def get_paginator(self, _):
        outer = self
        class P:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [o for o in outer.objs if o["Key"].startswith(Prefix)]}
        return P()

    def head_object(self, Bucket, Key):
        return {"Restore": self.restore.get(Key, "")}

    def download_file(self, b, k, path):
        self.got.append(k)
        Path(path).write_text("x")


def test_exclude_case_and_space():
    assert g.is_excluded("a/THUMBS.db", ["Thumbs.db"])
    assert g.is_excluded("a/ Thumbs .db/x", ["thumbs.db"])
    assert not g.is_excluded("a/photo.jpg", ["Thumbs.db"])


def test_mirror(tmp_path):
    objs = [
        {"Key": "p/a/1.jpg", "Size": 1, "StorageClass": "GLACIER"},
        {"Key": "p/a/Thumbs.db", "Size": 1, "StorageClass": "GLACIER"},
        {"Key": "p/b/2.jpg", "Size": 1, "StorageClass": "DEEP_ARCHIVE"},
        {"Key": "p/../../evil", "Size": 1},
    ]
    c = FakeS3(objs, {"p/a/1.jpg": 'ongoing-request="false", expiry-date="x"'})
    st = g.mirror(c, "b", "p", tmp_path, g.DEFAULT_EXCLUDES)
    assert c.got == ["p/a/1.jpg"]
    assert (tmp_path / "a/1.jpg").exists()
    assert st.excluded == 1 and st.not_restored == ["p/b/2.jpg"] and len(st.failed) == 1
    # second run: unchanged
    st2 = g.mirror(c, "b", "p", tmp_path, g.DEFAULT_EXCLUDES)
    assert st2.skipped_same == 1 and st2.downloaded == 0


def test_head_failure_does_not_stop_run(tmp_path):
    objs = [
        {"Key": "p/bad.jpg", "Size": 1, "StorageClass": "GLACIER"},
        {"Key": "p/ok.jpg", "Size": 1, "StorageClass": "GLACIER"},
    ]
    c = FakeS3(objs, {"p/ok.jpg": 'ongoing-request="false"'})
    orig = c.head_object
    def head(Bucket, Key):
        if Key == "p/bad.jpg":
            raise ClientError({"Error": {"Code": "403"}}, "HeadObject")
        return orig(Bucket, Key)
    c.head_object = head
    st = g.mirror(c, "b", "p", tmp_path, g.DEFAULT_EXCLUDES)
    assert c.got == ["p/ok.jpg"] and len(st.failed) == 1


def test_recursive_deep_nesting(tmp_path):
    objs = [{"Key": f"p/{d}/f.jpg", "Size": 1} for d in ("a", "a/b", "a/b/c/d/e")]
    objs.append({"Key": "other/x.jpg", "Size": 1})  # outside prefix
    c = FakeS3(objs)
    g.mirror(c, "b", "p", tmp_path, [])
    assert c.got == ["p/a/f.jpg", "p/a/b/f.jpg", "p/a/b/c/d/e/f.jpg"]
    assert (tmp_path / "a/b/c/d/e/f.jpg").is_file()
