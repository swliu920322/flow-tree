import shutil
from pathlib import Path

import yaml

from flowtree.guide import CURRENT, INVALID, STALE, load_guides
from flowtree.issues import ERROR
from flowtree.story import load_stories

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "examples"


def _setup(tmp_path, story="task-a-002"):
    sd = tmp_path / "stories"; gd = tmp_path / "guides"
    sd.mkdir(); gd.mkdir()
    shutil.copy(EX / "stories" / f"{story}.story.yaml", sd)
    shutil.copy(EX / "guides" / f"{story}.guide.yaml", gd)
    return sd, gd


def _codes(issues, severity=None):
    return {i.code for i in issues if severity is None or i.severity == severity}


def _edit(path, fn):
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(d)
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_shipped_guides_are_current():
    stories = load_stories([EX / "stories"])
    gs = load_guides([EX / "guides"], stories)
    assert not [i for i in gs.issues if i.severity == ERROR], gs.issues
    assert {k: v.status for k, v in gs.guides.items()} == {"TASK-A-002": CURRENT, "TASK-B-001": CURRENT}


def test_no_configured_guides_is_normal_default():
    gs = load_guides([], load_stories([EX / "stories"]))
    assert gs.guides == {} and gs.issues == []


def test_story_without_guide_is_normal(tmp_path):
    sd, gd = _setup(tmp_path)
    shutil.copy(EX / "stories" / "sav-001.story.yaml", sd)
    gs = load_guides([gd], load_stories([sd]))
    assert gs.get("SAV-001") is None and _codes(gs.issues, ERROR) == set()


def test_configured_but_empty_dir_is_reported(tmp_path):
    sd, _ = _setup(tmp_path)
    empty = tmp_path / "none"; empty.mkdir()
    assert "guide.empty_dir" in _codes(load_guides([empty], load_stories([sd])).issues)


def test_broken_yaml_is_reported_not_silent(tmp_path):
    sd, gd = _setup(tmp_path)
    (gd / "task-a-002.guide.yaml").write_text("story: [unclosed\n", encoding="utf-8")
    gs = load_guides([gd], load_stories([sd]))
    assert "guide.yaml" in _codes(gs.issues, ERROR) and gs.guides == {}


def test_unknown_field_and_missing_digest_are_schema_errors(tmp_path):
    sd, gd = _setup(tmp_path)
    p = gd / "task-a-002.guide.yaml"
    def f(d):
        d["bogus"] = 1; del d["story_digest"]
    _edit(p, f)
    gs = load_guides([gd], load_stories([sd]))
    assert "guide.schema" in _codes(gs.issues, ERROR) and gs.guides == {}


def test_unknown_step_reference(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(gd / "task-a-002.guide.yaml", lambda d: d["steps"][0].__setitem__("for", "STEP-99"))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == INVALID and "guide.dangling_ref" in _codes(lg.issues, ERROR)


def test_unknown_auxiliary_reference(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(gd / "task-a-002.guide.yaml", lambda d: d["auxiliary"][0].__setitem__("for", "NOPE"))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == INVALID and "guide.dangling_ref" in _codes(lg.issues, ERROR)


def test_duplicate_step_binding(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(gd / "task-a-002.guide.yaml", lambda d: d["steps"].append(dict(d["steps"][0])))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == INVALID and "guide.duplicate_step" in _codes(lg.issues, ERROR)


def test_unknown_and_duplicate_account(tmp_path):
    sd, gd = _setup(tmp_path)
    p = gd / "task-a-002.guide.yaml"
    _edit(p, lambda d: d["steps"][0].__setitem__("account", "ghost"))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert "guide.unknown_account" in _codes(lg.issues, ERROR)
    _edit(p, lambda d: (d["steps"][0].__setitem__("account", "solo"), d["accounts"].append(dict(d["accounts"][0]))))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert "guide.duplicate_account" in _codes(lg.issues, ERROR)


def test_duplicate_guide_for_same_story(tmp_path):
    sd, gd = _setup(tmp_path)
    shutil.copy(gd / "task-a-002.guide.yaml", gd / "copy.guide.yaml")
    assert "guide.duplicate_story" in _codes(load_guides([gd], load_stories([sd])).issues, ERROR)


def test_guide_for_unknown_story(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(gd / "task-a-002.guide.yaml", lambda d: d.__setitem__("story", "NOPE-1"))
    gs = load_guides([gd], load_stories([sd]))
    assert "guide.dangling_ref" in _codes(gs.issues, ERROR)


def test_story_change_marks_guide_stale_even_if_ids_exist(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(sd / "task-a-002.story.yaml", lambda d: d["main_flow"][1]["expected"].append("新增的预期"))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == STALE
    assert _codes(lg.issues, ERROR) == {"guide.story_changed"}


def test_stale_plus_other_problem_is_invalid(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(sd / "task-a-002.story.yaml", lambda d: d["main_flow"][1]["expected"].append("x"))
    _edit(gd / "task-a-002.guide.yaml", lambda d: d["steps"][0].__setitem__("for", "STEP-99"))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == INVALID


def test_wrong_schema_version(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(gd / "task-a-002.guide.yaml", lambda d: d.__setitem__("schema_version", "9"))
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == INVALID and "guide.schema_version" in _codes(lg.issues, ERROR)


def test_guide_edit_does_not_change_story_digest_or_story_issues(tmp_path):
    sd, gd = _setup(tmp_path)
    before = load_stories([sd])
    _edit(gd / "task-a-002.guide.yaml", lambda d: d["steps"][0].__setitem__("see", "改了文案"))
    after = load_stories([sd])
    assert before.get("TASK-A-002").digest == after.get("TASK-A-002").digest
    assert before.issues == after.issues
    assert load_guides([gd], after).get("TASK-A-002").status == CURRENT


def test_shipped_guide_story_digests_match_examples():
    stories = load_stories([EX / "stories"])
    for p in (EX / "guides").glob("*.guide.yaml"):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert d["story_digest"] == stories.get(d["story"]).digest


def test_uncovered_unit_is_only_a_warning(tmp_path):
    sd, gd = _setup(tmp_path)
    _edit(gd / "task-a-002.guide.yaml", lambda d: d["steps"].pop())
    lg = load_guides([gd], load_stories([sd])).get("TASK-A-002")
    assert lg.status == CURRENT and "guide.unit_uncovered" in _codes(lg.issues)


def test_duplicate_guides_leave_no_usable_candidate(tmp_path):
    for first_stale in (False, True):
        base = tmp_path / str(first_stale); base.mkdir()
        sd, gd = _setup(base)
        dup = gd / "z.guide.yaml"
        shutil.copy(gd / "task-a-002.guide.yaml", dup)
        _edit(gd / ("task-a-002.guide.yaml" if first_stale else "z.guide.yaml"),
              lambda d: d.__setitem__("story_digest", "sha256:" + "f" * 64))
        gs = load_guides([gd], load_stories([sd]))
        assert "guide.duplicate_story" in _codes(gs.issues, ERROR)
        got = gs.get("TASK-A-002")
        assert got is None or (got.status == INVALID and "guide.duplicate_story" in _codes(got.issues, ERROR))


def test_story_with_semantic_error_cannot_have_current_guide_but_others_unaffected(tmp_path):
    sd, gd = _setup(tmp_path)
    shutil.copy(EX / "stories" / "task-b-001.story.yaml", sd)
    shutil.copy(EX / "guides" / "task-b-001.guide.yaml", gd)
    _edit(sd / "task-a-002.story.yaml", lambda d: d["branches"][0]["continuation"].__setitem__("target", "STEP-MISSING"))
    stories = load_stories([sd])
    digest = stories.get("TASK-A-002").digest
    _edit(gd / "task-a-002.guide.yaml", lambda d: d.__setitem__("story_digest", digest))
    gs = load_guides([gd], stories)
    bad, good = gs.get("TASK-A-002"), gs.get("TASK-B-001")
    assert bad.status == INVALID and "guide.story_invalid" in _codes(bad.issues, ERROR)
    assert good.status == CURRENT and not _codes(good.issues, ERROR)
