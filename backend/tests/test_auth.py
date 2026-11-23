"""Password hashes and signed login tokens."""

from app.services.auth import hash_password, make_token, read_token, verify_password

SECRET = "test-secret"


def test_password_round_trip():
    stored = hash_password("advisor-demo")
    assert stored.startswith("scrypt$")
    assert verify_password("advisor-demo", stored)
    assert not verify_password("advisor-dem0", stored)


def test_same_password_hashes_differently():
    assert hash_password("x") != hash_password("x")


def test_malformed_hash_never_verifies():
    assert not verify_password("x", "plaintext")
    assert not verify_password("x", "md5$aa$bb")


def test_token_round_trip():
    assert read_token(make_token("demo", SECRET, now=1000), SECRET, now=1001) == "demo"


def test_key_with_a_colon_survives():
    assert read_token(make_token("a:b", SECRET, now=0), SECRET, now=1) == "a:b"


def test_token_expires():
    t = make_token("demo", SECRET, now=1000, ttl=60)
    assert read_token(t, SECRET, now=1060) == "demo"
    assert read_token(t, SECRET, now=1061) is None


def test_forged_or_tampered_token_is_refused():
    t = make_token("demo", SECRET, now=1000)
    assert read_token(t, "other-secret", now=1001) is None
    payload, sig = t.split(".")
    other = make_token("advisor", SECRET, now=1000).split(".")[0]
    assert read_token(f"{other}.{sig}", SECRET, now=1001) is None
    assert read_token("garbage", SECRET) is None
    assert read_token("", SECRET) is None
