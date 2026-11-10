import copy
import shutil

import pytest
import yaml

from impl_support import FIXTURES
from flowtree.issues import ERROR, WARNING
from flowtree.mapping import load_mapping_file
from flowtree.story import load_stories


@pytest.fixture
def stories(tmp_path):
    d = tmp_path / "stories"
    d.mkdir()
    shutil.copy(FIXTURES / "sav-001.story.yaml", d)
    return load_stories([d])


@pytest.fixture
def base():
    return yaml.safe_load((FIXTURES / "sav-001.mapping.yaml").read_text(encoding="utf-8"))


def load(tmp_path, data, stories):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return load_mapping_file(p, stories)


def codes(lm, severity=None):
    return [i.code for i in lm.issues if severity is None or i.severity == severity]


def test_fixture_mapping_is_valid_and_pinned(tmp_path, stories, base):
    lm = load(tmp_path, base, stories)
    assert lm.issues == [], lm.issues
    assert set(lm.entry_digests) == {"M-01", "M-02"}
    assert lm.digest.startswith("sha256:")


def test_parametrized_match_explicitly_rejected(tmp_path, stories, base):
    base["entries"][0]["tests"][0]["match"] = "parametrized"
    assert "mapping.match_unsupported" in codes(load(tmp_path, base, stories), ERROR)


def test_bare_string_tests_rejected(tmp_path, stories, base):
    base["entries"][0]["tests"] = ["tests/test_savings.py::test_x"]
    assert "mapping.schema" in codes(load(tmp_path, base, stories), ERROR)


def test_missing_match_rejected(tmp_path, stories, base):
    base["entries"][0]["tests"] = [{"nodeid": "tests/test_savings.py::test_x"}]
    assert "mapping.schema" in codes(load(tmp_path, base, stories), ERROR)


@pytest.mark.parametrize("nodeid", [
    "tests/test_savings.py",              # 没有测试名
    "tests/test_savings.py::test_*",      # 通配符
    "tests/test_savings.py::test_?",
    "/abs/test_x.py::test_a",             # 绝对路径
    "../outside/test_x.py::test_a",       # 越出 rootdir
    "tests/notpy.txt::test_a",
    " tests/test_savings.py::test_a",
])
def test_bad_nodeids_rejected(tmp_path, stories, base, nodeid):
    base["entries"][0]["tests"][0]["nodeid"] = nodeid
    assert "mapping.bad_nodeid" in codes(load(tmp_path, base, stories), ERROR)


def test_exact_parameter_instance_nodeid_allowed(tmp_path, stories, base):
    base["entries"][0]["tests"][0]["nodeid"] = "tests/test_savings.py::test_amount[0.25-ok]"
    assert codes(load(tmp_path, base, stories), ERROR) == []


def test_duplicate_nodeid_in_entry(tmp_path, stories, base):
    base["entries"][0]["tests"].append(copy.deepcopy(base["entries"][0]["tests"][0]))
    assert "mapping.duplicate_test" in codes(load(tmp_path, base, stories), ERROR)


@pytest.mark.parametrize("extra", [["-k", "resume"], ["-kresume"], ["-m", "slow"], ["--deselect", "a"],
                                   ["--deselect=a"], ["--lf"], ["-x"], ["--maxfail=1"], ["--junitxml=r.xml"],
                                   ["-p", "no:cacheprovider"], ["--collect-only"]])
def test_scope_changing_argv_rejected(tmp_path, stories, base, extra):
    base["entries"][0]["argv"] = ["python", "-m", "pytest", "tests/test_savings.py", *extra]
    assert "mapping.argv_scope_option" in codes(load(tmp_path, base, stories), ERROR)


def test_python_dash_m_flag_before_pytest_is_not_confused(tmp_path, stories, base):
    base["entries"][0]["argv"] = ["python3.13", "-m", "pytest", "tests/test_savings.py", "-q"]
    assert codes(load(tmp_path, base, stories), ERROR) == []
    base["entries"][0]["argv"] = [".venv/bin/pytest", "tests/test_savings.py", "-q"]
    assert codes(load(tmp_path, base, stories), ERROR) == []


def test_non_pytest_argv_rejected(tmp_path, stories, base):
    base["entries"][0]["argv"] = ["make", "test"]
    assert "mapping.argv_not_pytest" in codes(load(tmp_path, base, stories), ERROR)


def test_unsupported_runner(tmp_path, stories, base):
    base["entries"][0]["runner"] = "flutter"
    assert "mapping.runner_unsupported" in codes(load(tmp_path, base, stories), ERROR)


def test_covers_dangling_unqualified_cross_story(tmp_path, stories, base):
    for covers, code in [("SAV-001.STEP-99", "mapping.dangling_ref"),
                         ("STEP-01", "mapping.covers_unqualified"),
                         ("OTHER-1.STEP-01", "mapping.covers_cross_story")]:
        b = copy.deepcopy(base)
        b["entries"][0]["covers"] = [covers]
        assert code in codes(load(tmp_path, b, stories), ERROR), covers


def test_unknown_story_reference(tmp_path, stories, base):
    base["story"] = "NOPE-1"
    assert "mapping.dangling_ref" in codes(load(tmp_path, base, stories), ERROR)


def test_story_change_after_pin_is_an_error(tmp_path, stories, base):
    base["story_digest"] = "sha256:" + "0" * 64
    assert "mapping.story_changed" in codes(load(tmp_path, base, stories), ERROR)


def test_unpinned_mapping_warns(tmp_path, stories, base):
    del base["story_digest"]
    lm = load(tmp_path, base, stories)
    assert "mapping.unpinned" in codes(lm, WARNING) and codes(lm, ERROR) == []


def test_entry_digest_changes_only_for_changed_entry(tmp_path, stories, base):
    before = load(tmp_path, base, stories).entry_digests
    base["entries"][1]["timeout_s"] = 301
    after = load(tmp_path, base, stories).entry_digests
    assert before["M-01"] == after["M-01"] and before["M-02"] != after["M-02"]


def test_duplicate_entry_ids(tmp_path, stories, base):
    base["entries"][1]["id"] = "M-01"
    assert "mapping.duplicate_id" in codes(load(tmp_path, base, stories), ERROR)


def test_absolute_cwd_warns_and_unknown_field_rejected(tmp_path, stories, base):
    base["entries"][0]["cwd"] = "/tmp/x"
    assert "mapping.cwd_absolute" in codes(load(tmp_path, base, stories), WARNING)
    base["entries"][0]["shell"] = "true"
    assert "mapping.schema" in codes(load(tmp_path, base, stories), ERROR)
