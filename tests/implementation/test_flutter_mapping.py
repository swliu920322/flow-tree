"""flutter 映射校验: argv 是白名单 (只有测试文件), 测试标识精确; 不需要 Flutter SDK。"""
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
    d = tmp_path / "stories"; d.mkdir()
    shutil.copy(FIXTURES / "sav-001.story.yaml", d)
    return load_stories([d])


@pytest.fixture
def base(stories):
    from flowtree.story import load_story_file
    digest = load_story_file(FIXTURES / "sav-001.story.yaml").digest
    return {"schema_version": "0.1", "story": "SAV-001", "story_digest": digest, "entries": [{
        "id": "M-01", "covers": ["SAV-001.CASE-01"], "level": "client", "runner": "flutter", "cwd": ".",
        "argv": ["flutter", "test", "test/savings_test.dart"],
        "tests": [{"nodeid": "test/savings_test.dart::G resume after lost response", "match": "exact"}],
        "env": {"id": "e"}}]}


def load(tmp_path, data, stories):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return load_mapping_file(p, stories)


def codes(lm, sev=None):
    return [i.code for i in lm.issues if sev is None or i.severity == sev]


def test_valid_flutter_mapping(tmp_path, stories, base):
    assert load(tmp_path, base, stories).issues == []


@pytest.mark.parametrize("opt", [
    "--plain-name", "-N", "--name=x", "-n", "--tags", "-t", "--exclude-tags", "-x", "--reporter=json", "-r", "--file-reporter",
    "--shard-index=1", "--total-shards=2", "--retry=3", "--no-pub", "--pub", "--coverage", "--concurrency=1", "-j",
    "--dart-define=A=B", "--device-id=x", "--fail-fast", "--machine", "--update-goldens", "--help", "-h",
])
def test_every_option_is_rejected_by_the_whitelist(tmp_path, stories, base, opt):
    base["entries"][0]["argv"] = ["flutter", "test", opt, "test/savings_test.dart"]
    assert "mapping.argv_option_not_allowed" in codes(load(tmp_path, base, stories), ERROR), opt


@pytest.mark.parametrize("path", ["test", "test/", "test/*.dart", "/abs/a_test.dart", "../a_test.dart", "test/helper.dart", "lib/x.dart"])
def test_only_relative_test_files_are_accepted(tmp_path, stories, base, path):
    base["entries"][0]["argv"] = ["flutter", "test", path]
    assert "mapping.argv_flutter_path" in codes(load(tmp_path, base, stories), ERROR), path


@pytest.mark.parametrize("argv", [["dart", "test", "test/a_test.dart"], ["flutter", "run", "test/a_test.dart"], ["flutter", "test"], ["python", "-m", "pytest"]])
def test_argv_must_be_flutter_test_with_files(tmp_path, stories, base, argv):
    base["entries"][0]["argv"] = argv
    assert "mapping.argv_not_flutter" in codes(load(tmp_path, base, stories), ERROR)


def test_absolute_flutter_path_and_multiple_files_are_fine(tmp_path, stories, base):
    base["entries"][0]["argv"] = ["/opt/flutter/bin/flutter", "test", "test/savings_test.dart", "test/other_test.dart"]
    base["entries"][0]["tests"].append({"nodeid": "test/other_test.dart::x", "match": "exact"})
    assert codes(load(tmp_path, base, stories), ERROR) == []


@pytest.mark.parametrize("nodeid,code", [
    ("test/savings_test.dart", "mapping.bad_nodeid"),                    # 没有名称
    ("test/savings_test.dart::", "mapping.bad_nodeid"),
    ("test/savings_test.dart:: leading", "mapping.bad_nodeid"),
    ("test/savings_test.dart::trailing ", "mapping.bad_nodeid"),
    ("test/other_test.dart::x", "mapping.test_file_not_in_argv"),        # 文件没有被执行
    ("./test/savings_test.dart::x", None),                                 # 规范化后等价
])
def test_flutter_test_ids_are_exact(tmp_path, stories, base, nodeid, code):
    base["entries"][0]["tests"] = [{"nodeid": nodeid, "match": "exact"}]
    cs = codes(load(tmp_path, base, stories), ERROR)
    assert (code in cs) if code else (cs == [])


def test_name_with_double_colon_is_accepted_and_split_on_the_first_separator_only(tmp_path, stories, base):
    base["entries"][0]["tests"] = [{"nodeid": "test/savings_test.dart::G a::b c", "match": "exact"}]
    assert codes(load(tmp_path, base, stories), ERROR) == []


def test_parametrized_and_duplicates_still_rejected(tmp_path, stories, base):
    b = copy.deepcopy(base); b["entries"][0]["tests"][0]["match"] = "parametrized"
    assert "mapping.match_unsupported" in codes(load(tmp_path, b, stories), ERROR)
    b = copy.deepcopy(base); b["entries"][0]["tests"].append(copy.deepcopy(b["entries"][0]["tests"][0]))
    assert "mapping.duplicate_test" in codes(load(tmp_path, b, stories), ERROR)


def test_pytest_rules_do_not_apply_to_flutter_and_vice_versa(tmp_path, stories, base):
    b = copy.deepcopy(base); b["entries"][0]["runner"] = "pytest"       # flutter 的 argv/标识交给 pytest 校验 → 报错
    cs = codes(load(tmp_path, b, stories), ERROR)
    assert "mapping.argv_not_pytest" in cs and "mapping.bad_nodeid" in cs
