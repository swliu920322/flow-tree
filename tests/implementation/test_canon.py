import pytest

from flowtree.canon import YamlLoadError, content_digest, load_yaml_text

BASE = """
id: X
items: [a, b]
meta: {k: 1, j: "2"}
"""


def d(text):
    return content_digest(load_yaml_text(text))


def test_digest_ignores_comments_layout_quoting_and_key_order():
    other = """
# 注释
meta: {j: '2', k: 1}
items:
  - "a"
  - b
id: X   # trailing
"""
    assert d(BASE) == d(other)


def test_list_order_changes_digest():
    assert d(BASE) != d(BASE.replace("[a, b]", "[b, a]"))


def test_type_difference_changes_digest():
    assert d("a: 1") != d('a: "1"')


def test_digest_field_excluded_and_not_self_referential():
    base = load_yaml_text(BASE)
    with_digest = dict(base, digest="sha256:whatever")
    assert content_digest(base) == content_digest(with_digest)


def test_nfc_normalization():
    assert d("a: é") == d("a: é")


def test_duplicate_keys_rejected():
    with pytest.raises(YamlLoadError, match="duplicate key"):
        load_yaml_text("a: 1\na: 2\n")


def test_timestamp_like_scalars_stay_strings():
    assert load_yaml_text("t: 2026-01-01") == {"t": "2026-01-01"}


def test_non_string_keys_rejected_in_digest():
    with pytest.raises(YamlLoadError):
        content_digest(load_yaml_text("1: a"))
