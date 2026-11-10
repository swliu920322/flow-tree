import copy
import textwrap

import pytest
import yaml

from impl_support import FIXTURES
from flowtree.issues import ERROR, WARNING
from flowtree.story import load_stories, load_story_file


def codes(loaded, severity=None):
    return [i.code for i in loaded.issues if severity is None or i.severity == severity]


def write_story(tmp_path, data, name="s.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def base():
    return yaml.safe_load((FIXTURES / "sav-001.story.yaml").read_text(encoding="utf-8"))


def test_spec_example_loads_without_issues_in_original_format():
    loaded = load_story_file(FIXTURES / "sav-001.story.yaml")
    assert loaded.issues == []
    assert loaded.story.inputs["amount"] == "0.25"
    assert loaded.story.unit_ids() == ["STEP-01", "STEP-02", "STEP-03", "STEP-04", "CASE-01", "CASE-02"]
    assert loaded.digest.startswith("sha256:")


def test_untyped_amount_is_not_claimed_validated(tmp_path, base):
    base["inputs"]["amount"] = "abc"  # 无类型声明: 不应报金额错误, 也不应声称已校验
    loaded = load_story_file(write_story(tmp_path, base))
    assert "story.input_decimal" not in codes(loaded)


def test_typed_decimal_ok_and_bad(tmp_path, base):
    base["inputs"]["amount"] = {"type": "decimal", "value": "0.25", "max_scale": 2}
    assert codes(load_story_file(write_story(tmp_path, base)), ERROR) == []
    for bad in ["0.255", "1e3", ".5", "abc", 0.25, "-"]:
        base["inputs"]["amount"] = {"type": "decimal", "value": bad, "max_scale": 2}
        assert "story.input_decimal" in codes(load_story_file(write_story(tmp_path, base))) or \
            "story.input_decimal_scale" in codes(load_story_file(write_story(tmp_path, base))), bad


def test_unknown_input_type_and_float_warning(tmp_path, base):
    base["inputs"]["amount"] = {"type": "money", "value": "1"}
    assert "story.input_type_unknown" in codes(load_story_file(write_story(tmp_path, base)), ERROR)
    base["inputs"]["amount"] = 0.25
    assert "story.input_float_untyped" in codes(load_story_file(write_story(tmp_path, base)), WARNING)


def test_duplicate_ids_within_story_across_steps_and_branches(tmp_path, base):
    base["branches"][0]["id"] = "STEP-01"
    assert "story.duplicate_id" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


def test_dangling_at_and_rejoin_target(tmp_path, base):
    b = copy.deepcopy(base)
    b["branches"][0]["at"] = "STEP-99"
    assert "story.dangling_ref" in codes(load_story_file(write_story(tmp_path, b)), ERROR)
    b = copy.deepcopy(base)
    b["branches"][1]["continuation"]["target"] = "STEP-99"
    assert "story.dangling_ref" in codes(load_story_file(write_story(tmp_path, b)), ERROR)


def test_rejoin_valid_and_backward_rejected(tmp_path, base):
    assert load_story_file(write_story(tmp_path, base)).issues == []
    base["branches"][1]["continuation"]["target"] = "STEP-01"
    assert "story.rejoin_backward" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


def test_retry_rejected_not_treated_as_end(tmp_path, base):
    base["branches"][0]["continuation"] = {"type": "retry", "target": "STEP-01"}
    loaded = load_story_file(write_story(tmp_path, base))
    assert "story.retry_unsupported" in codes(loaded, ERROR)


def test_end_with_target_and_rejoin_without_target_rejected(tmp_path, base):
    base["branches"][0]["continuation"] = {"type": "end", "target": "STEP-03"}
    assert "story.continuation_target" in codes(load_story_file(write_story(tmp_path, base)), ERROR)
    base["branches"][0]["continuation"] = {"type": "rejoin"}
    assert "story.continuation_target" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


def test_structured_open_question_blocks_only_its_units(tmp_path, base):
    base["open_questions"] = [{"id": "Q1", "text": "金额上限？", "blocks": ["CASE-01"]}]
    loaded = load_story_file(write_story(tmp_path, base))
    assert loaded.issues == []
    assert loaded.story.blocked_by_questions() == {"CASE-01": ["Q1"]}


def test_legacy_string_open_question_conservatively_blocks_whole_story(tmp_path, base):
    base["open_questions"] = ["上限未定"]
    loaded = load_story_file(write_story(tmp_path, base))
    assert "story.open_question_legacy" in codes(loaded, WARNING)
    assert set(loaded.story.blocked_by_questions()) == set(loaded.story.unit_ids())


def test_open_question_dangling_block_ref(tmp_path, base):
    base["open_questions"] = [{"id": "Q1", "text": "?", "blocks": ["NOPE"]}]
    assert "story.dangling_ref" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


def test_structured_open_question_requires_blocks(tmp_path, base):
    base["open_questions"] = [{"id": "Q1", "text": "?"}]
    assert "story.schema" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


@pytest.mark.parametrize("now,tz,ok", [
    ("2026-01-01T09:30:00", "Asia/Shanghai", True),
    ("2026-01-01T09:30:00+08:00", "Asia/Shanghai", False),  # 偏移与时区并存有歧义
    ("2026-01-01T09:30:00", "Mars/Olympus", False),
    ("not-a-time", "Asia/Shanghai", False),
    ("2026-11-01T01:30:00", "America/New_York", False),      # 回拨重叠: 歧义
    ("2026-03-08T02:30:00", "America/New_York", False),      # 春季跳变: 不存在
])
def test_clock_validation(tmp_path, base, now, tz, ok):
    base["clock"] = {"now": now, "tz": tz}
    loaded = load_story_file(write_story(tmp_path, base))
    assert (codes(loaded, ERROR) == []) is ok


def test_declared_digest_must_match(tmp_path, base):
    loaded = load_story_file(write_story(tmp_path, base))
    base["digest"] = loaded.digest
    assert load_story_file(write_story(tmp_path, base, "ok.yaml")).issues == []
    base["digest"] = "sha256:deadbeef"
    assert "story.digest_mismatch" in codes(load_story_file(write_story(tmp_path, base, "bad.yaml")), ERROR)


def test_unknown_field_rejected(tmp_path, base):
    base["surprise"] = 1
    assert "story.schema" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


def test_duplicate_yaml_keys_reported(tmp_path):
    p = tmp_path / "dup.yaml"
    p.write_text("schema_version: '0.1'\nid: A\nid: B\n", encoding="utf-8")
    assert "story.yaml" in codes(load_story_file(p), ERROR)


def test_unsupported_schema_version(tmp_path, base):
    base["schema_version"] = "9.9"
    assert "story.schema_version" in codes(load_story_file(write_story(tmp_path, base)), ERROR)


def test_duplicate_story_id_across_files(tmp_path, base):
    write_story(tmp_path, base, "a.yaml")
    write_story(tmp_path, base, "b.yaml")
    result = load_stories([tmp_path])
    assert [i.code for i in result.issues if i.severity == ERROR] == ["story.duplicate_id"]
    assert list(result.stories) == ["SAV-001"]


def test_digest_unaffected_by_formatting(tmp_path, base):
    a = write_story(tmp_path, base, "a.yaml")
    b = tmp_path / "b.yaml"
    b.write_text("# comment\n" + a.read_text(encoding="utf-8").replace("\n", "  \n"), encoding="utf-8")
    assert load_story_file(a).digest == load_story_file(b).digest
