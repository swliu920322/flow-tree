"""指引共享校验的独立反例，不运行 LPB 或执行播种脚本。"""
import importlib.util
from pathlib import Path

import pytest
import yaml

from flowtree.guide import CURRENT, INVALID, load_guides
from flowtree.issues import ERROR
from flowtree.story import load_stories

ROOT = Path(__file__).resolve().parents[2]


def case(tmp_path):
    stories = tmp_path / "stories"
    guides = tmp_path / "guides"
    stories.mkdir()
    guides.mkdir()
    story = ROOT / "examples/stories/task-a-002.story.yaml"
    guide = ROOT / "examples/guides/task-a-002.guide.yaml"
    (stories / "story.yaml").write_text(story.read_text())
    (guides / "a.yaml").write_text(guide.read_text())
    return stories, guides


@pytest.mark.parametrize("first_stale", [False, True])
def test_duplicate_guides_never_leave_a_selected_usable_candidate(tmp_path, first_stale):
    stories, guides = case(tmp_path)
    first = yaml.safe_load((guides / "a.yaml").read_text())
    second = dict(first)
    (first if first_stale else second)["story_digest"] = "sha256:" + "f" * 64
    for name, data in [("a.yaml", first), ("b.yaml", second)]:
        (guides / name).write_text(yaml.safe_dump(data, allow_unicode=True))
    loaded = load_guides([guides], load_stories([stories]))
    assert any(i.code == "guide.duplicate_story" for i in loaded.issues)
    selected = loaded.get("TASK-A-002")
    assert selected is None or selected.status == INVALID, (
        "conflicting guides must not leave a current/stale candidate selected by filename order"
    )


def test_semantically_invalid_story_cannot_have_a_current_guide(tmp_path):
    stories, guides = case(tmp_path)
    path = stories / "story.yaml"
    data = yaml.safe_load(path.read_text())
    data["branches"][0]["continuation"]["target"] = "STEP-MISSING"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    story_set = load_stories([stories])
    assert any(i.severity == ERROR for i in story_set.get("TASK-A-002").issues)
    # 不是旧版本问题：指引绑定的正是当前这个有语义错误的故事摘要。
    path = guides / "a.yaml"
    data = yaml.safe_load(path.read_text())
    data["story_digest"] = story_set.get("TASK-A-002").digest
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    guide = load_guides([guides], story_set).get("TASK-A-002")
    assert guide.status == INVALID


def test_account_check_does_not_take_comments_as_seed_declarations(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "review_lpb_account_checker", ROOT / "tests/sample_specific/test_lpb_guide_accounts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    script = tmp_path / module.SCRIPT_REL
    script.parent.mkdir(parents=True)
    script.write_text('''#!/bin/bash
python - <<'PYEOF'
PW = "fixture-password"
mom_id, mom = user("mom", "新显示名")
# 旧示例，仅注释：user("mom", "旧显示名")
PYEOF
''')
    monkeypatch.setenv("FLOWTREE_LPB_PROJECT", str(tmp_path))
    password, accounts = module._seed_declaration()
    assert password == "fixture-password"
    assert accounts == {"mom": "新显示名"}, "a comment concealed a changed seed account"


def test_valid_guide_is_current(tmp_path):
    stories, guides = case(tmp_path)
    loaded = load_guides([guides], load_stories([stories]))
    assert loaded.get("TASK-A-002").status == CURRENT
    assert not any(i.severity == ERROR for i in loaded.issues)


def test_account_checker_rejects_password_reassignment():
    spec = importlib.util.spec_from_file_location(
        "review_lpb_password_checker", ROOT / "tests/sample_specific/test_lpb_guide_accounts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 唯一字面量赋值不等于唯一赋值；后续实际密码已经变化。
    script = '''python - <<'PYEOF'
PW = "fixture-password"
PW = "changed-" + "password"
user("mom", "妈妈")
PYEOF
'''
    with pytest.raises(AssertionError, match="PW"):
        module.parse_seed(script)


def test_explicit_missing_path_is_diagnosed(tmp_path):
    stories, _ = case(tmp_path)
    loaded = load_guides([tmp_path / "missing.yaml"], load_stories([stories]))
    assert not loaded.guides
    assert any(i.severity == ERROR for i in loaded.issues)
