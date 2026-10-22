"""R67: Sentry check-in protocol helpers. Expected values come from Sentry's own code and tests
(getsentry/relay relay-monitors slugify table, relay-server envelope parsing tests)."""
import base64
import gzip
import json
import zlib

import pytest

from cronsentinel import sentrycompat as sc

SLUG_CASES = [  # relay-monitors/src/lib.rs slugify_matches_sentry
    ("my-monitor", "my-monitor"), ("My Monitor", "my-monitor"), ("MyJob", "myjob"), ("my_job", "my_job"),
    ("  leading and trailing  ", "leading-and-trailing"), ("a - ! - b", "a-b"), ("--a--b--", "a-b"), ("_-_a_-_", "a"),
    ("a\tb\nc", "a-b-c"), ("a\x1cb", "a-b"), ("Café Crème", "cafe-creme"), ("straße", "strae"), ("🦀 crab job", "crab-job"),
    ("🦀🦀", ""), ("日本語", ""), ("ﬁle", "file"), ("Hello, World!", "hello-world"), ("a.b.c", "abc"), ("ÀÉÎÕÜ", "aeiou"),
    ("a" * 49 + "-b", "a" * 49), ("a" * 49 + "_b", "a" * 49 + "_"), ("x" * 60, "x" * 50), ("-", ""), ("", ""),
]


@pytest.mark.parametrize("raw,want", SLUG_CASES)
def test_slugify_matches_sentry(raw, want):
    assert sc.slugify(raw) == want


def test_token_normalises_slug_and_key():
    assert sc.token(4505, "ABCDEF" + "0" * 26, "My Job") == sc.token("4505", "abcdef" + "0" * 26, "my-job") == f"sentry:4505:abcdef{'0' * 26}:my-job"


K = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


@pytest.mark.parametrize("headers,query,path,want", [
    ({"x-sentry-auth": f"Sentry sentry_key={K}, sentry_version=7, sentry_client=sentry.python/2.71.0"}, "", None, K),
    ({"authorization": f"Sentry sentry_key={K},sentry_version=7"}, "", None, K),
    ({"authorization": "Basic " + base64.b64encode(f"{K}:".encode()).decode()}, "", None, K),
    ({}, f"sentry_key={K}&sentry_version=7", None, K),
    ({}, "status=ok", K, K),
    ({}, "status=ok", None, None),
])
def test_key_from_request(headers, query, path, want):
    assert sc.key_from_request(headers, query, path) == want


def test_key_from_dsn():
    assert sc.key_from_dsn(f"https://{K}@o1.ingest.sentry.io/4505") == K
    assert sc.key_from_dsn(f"https://{K}:@sentry.io/42") == K
    assert sc.key_from_dsn(None) is None and sc.key_from_dsn("not a dsn") is None


def test_parse_envelope_explicit_and_implicit_lengths():
    # relay-server envelope tests: explicit length with \r\n inside the payload, then implicit length
    data = (b'{"event_id":"9ec79c33ec9942ab8353589fcb2e04dc","dsn":"https://e12d836b15bb49d7bbf99e64295d995b:@sentry.io/42"}\n'
            b'{"type":"attachment","length":10,"content_type":"text/plain","filename":"hello.txt"}\n'
            b'\xef\xbb\xbfHello\r\n\n'
            b'{"type":"check_in"}\n'
            b'{"check_in_id":"83a7c03ed0a04e1b97e2e3b18d38f244","monitor_slug":"x","status":"ok"}\n')
    header, items = sc.parse_envelope(data)
    assert header["dsn"].startswith("https://e12d")
    assert [i[0]["type"] for i in items] == ["attachment", "check_in"]
    assert items[0][1] == b"\xef\xbb\xbfHello\r\n"
    assert json.loads(items[1][1])["status"] == "ok"


def test_parse_envelope_edge_cases():
    assert sc.parse_envelope(b'{}')[1] == []
    assert sc.parse_envelope(b'{}\n{"type":"check_in"}')[1] == [({"type": "check_in"}, b"")]       # implicit length at EOF
    assert sc.parse_envelope(b'{}\n{"type":"attachment","length":0}\n\n{"type":"attachment","length":0}\n')[1] == [
        ({"type": "attachment", "length": 0}, b""), ({"type": "attachment", "length": 0}, b"")]
    for bad in (b"nope\n", b'{}\nnot json\n', b'{}\n{"type":"x","length":99}\nshort', b'[1]\n'):
        with pytest.raises(sc.BadRequest):
            sc.parse_envelope(bad)


def test_decode_body_encodings():
    body = b'{"x":1}\n' * 10
    assert sc.decode_body(body, None) == body
    assert sc.decode_body(gzip.compress(body), "gzip") == body
    assert sc.decode_body(zlib.compress(body), "deflate") == body
    raw = zlib.compressobj(wbits=-zlib.MAX_WBITS); assert sc.decode_body(raw.compress(body) + raw.flush(), "deflate") == body
    brotli = pytest.importorskip("brotli")
    assert sc.decode_body(brotli.compress(body), "br") == body
    with pytest.raises(sc.BadRequest) as e:
        sc.decode_body(b"x", "zstd")
    assert e.value.status == 415
    with pytest.raises(sc.BadRequest):
        sc.decode_body(b"not gzip", "gzip")


@pytest.mark.parametrize("enc", ["gzip", "deflate", "br"])
def test_decompression_bomb_refused(enc):
    big = b"\0" * (sc.MAX_DECODED * 5)
    if enc == "br":
        brotli = pytest.importorskip("brotli"); packed = brotli.compress(big)
    else:
        packed = gzip.compress(big) if enc == "gzip" else zlib.compress(big)
    assert len(packed) < sc.MAX_BODY
    with pytest.raises(sc.BadRequest) as e:
        sc.decode_body(packed, enc)
    assert e.value.status == 413


def test_checkin_fields():
    f = sc.checkin_fields({"check_in_id": "83a7c03e-d0a0-4e1b-97e2-e3b18d38f244", "status": "in_progress", "environment": "prod", "release": "1.2"})
    assert f == {"status": "start", "duration_ms": None, "meta": {"source": "sentry", "env": "prod", "release": "1.2"},
                 "execution_id": "se-83a7c03ed0a04e1b97e2e3b18d38f244", "sequence": 0}
    f = sc.checkin_fields({"check_in_id": "00000000-0000-0000-0000-000000000000", "status": "error", "duration": 12.5})
    assert f["status"] == "fail" and f["duration_ms"] == 12500 and f["execution_id"] is None and f["sequence"] == 1
    assert sc.checkin_fields({"status": "ok", "duration": "bad"})["duration_ms"] is None
    assert sc.checkin_fields({"status": "ok", "duration": -1})["duration_ms"] is None
    assert sc.checkin_fields({"status": "missed"}) is None and sc.checkin_fields({}) is None
    assert sc.checkin_fields({"status": "ok", "environment": "e" * 100})["meta"]["env"] == "e" * 64
