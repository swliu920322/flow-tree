"""样例专项 (不属于通用核心): 指引里的隔离账号必须与 LPB 人工验收脚本 manual_env.sh 的播种声明一致。

账号在指引与脚本里是"两处声明 + 一致性检查", 不是单一来源。
项目路径必须显式传入: FLOWTREE_LPB_PROJECT=<LPB 根目录>。没有设置或找不到脚本时本检查**未核对**
(pytest 会显示 skipped 及原因), 不应被理解为一致。
"""
import ast
import os
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = "tools/manual_acceptance/manual_env.sh"


def _seed_declaration():
    proj = os.environ.get("FLOWTREE_LPB_PROJECT")
    if not proj:
        pytest.skip("NOT CHECKED: FLOWTREE_LPB_PROJECT is not set")
    script = Path(proj) / SCRIPT_REL
    if not script.is_file():
        pytest.skip(f"NOT CHECKED: {script} not found")
    return parse_seed(script.read_text(encoding="utf-8"))


def parse_seed(text):
    """只解析 manual_env.sh 里实际执行的播种 Python 片段 (heredoc), 用 AST, 不执行脚本。
    注释不会被读到; 不支持的写法 (非字面量参数、重复账号、找不到片段) 明确失败, 不猜测。"""
    blocks = re.findall(r"<<'PYEOF'[^\n]*\n(.*?)\nPYEOF", text, re.S)
    assert len(blocks) == 1, f"expected exactly one PYEOF seed block in manual_env.sh, found {len(blocks)}; update this check"
    tree = ast.parse(blocks[0])
    # 统计 PW 的全部写入 (赋值、增量赋值、解包、for/with/import/def/参数/海象等); 只接受唯一一次字符串字面量赋值
    writes = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "PW" and not isinstance(n.ctx, ast.Load)]
    writes += [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == "PW"]
    writes += [n for n in ast.walk(tree) if isinstance(n, ast.alias) and (n.asname or n.name.split(".")[0]) == "PW"]
    writes += [n for n in ast.walk(tree) if isinstance(n, ast.arg) and n.arg == "PW"]
    writes += [n for n in ast.walk(tree) if isinstance(n, (ast.Global, ast.Nonlocal)) and "PW" in n.names]
    literal = [n for n in ast.walk(tree)
               if isinstance(n, ast.Assign) and len(n.targets) == 1
               and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "PW"
               and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
    assert len(literal) == 1 and len(writes) == 1, (
        f"PW must be written exactly once, by a plain string-literal assignment (found {len(writes)} write(s), {len(literal)} literal assignment(s))")
    pws = [literal[0].value.value]
    users = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "user":
            ok = (len(n.args) == 2 and not n.keywords
                  and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in n.args))
            assert ok, f"unsupported user(...) declaration at line {n.lineno}: arguments must be two string literals"
            name, display = n.args[0].value, n.args[1].value
            assert name not in users, f"account {name!r} seeded twice"
            users[name] = display
    assert users, "no user(...) declarations found in the seed block"
    return pws[0], users


def _guide_accounts():
    out = {}
    for p in sorted((ROOT / "examples" / "guides").glob("*.guide.yaml")):
        for a in yaml.safe_load(p.read_text(encoding="utf-8")).get("accounts", []):
            out.setdefault(a["username"], []).append((p.name, a))
    return out


def test_guide_accounts_match_manual_env_seed():
    pw, seeded = _seed_declaration()
    declared = _guide_accounts()
    for name, uses in declared.items():
        assert name in seeded, f"guide account {name!r} is not seeded by manual_env.sh"
        for fname, a in uses:
            assert a["display_name"] == seeded[name], f"{fname}: display_name of {name!r} differs from seed"
            assert a["password"] == pw, f"{fname}: password of {name!r} differs from seed"
    assert set(seeded) <= set(declared), f"seeded but not in any guide: {sorted(set(seeded) - set(declared))}"


# ---- 解析器自身的回归 (不需要 LPB) ----
def _script(body):
    return "#!/bin/bash\npython - <<'PYEOF'\n" + body + "\nPYEOF\n"


def test_parser_ignores_comments_and_reads_actual_seed():
    pw, users = parse_seed(_script('PW = "p"\nmom_id, mom = user("mom", "新")\n# user("mom", "旧")'))
    assert (pw, users) == ("p", {"mom": "新"})


def test_parser_rejects_duplicate_account():
    with pytest.raises(AssertionError, match="seeded twice"):
        parse_seed(_script('PW = "p"\nuser("a", "x")\nuser("a", "y")'))


def test_parser_rejects_non_literal_declaration():
    with pytest.raises(AssertionError, match="unsupported"):
        parse_seed(_script('PW = "p"\nuser(name, "x")'))


@pytest.mark.parametrize("extra", ['PW = "a" + "b"', 'PW += "x"', 'PW, other = "a", "b"', 'for PW in ["z"]: pass',
                                   'def PW(): pass', 'import os as PW', '(PW := "z")', 'PW: str = "z"'])
def test_parser_rejects_any_second_pw_write(extra):
    with pytest.raises(AssertionError, match="PW"):
        parse_seed(_script('PW = "p"\n' + extra + '\nuser("a", "x")'))


def test_parser_rejects_non_literal_only_pw():
    with pytest.raises(AssertionError, match="PW"):
        parse_seed(_script('PW = "a" + "b"\nuser("a", "x")'))


def test_parser_requires_one_seed_block_and_one_pw():
    with pytest.raises(AssertionError, match="PYEOF"):
        parse_seed("#!/bin/bash\n# user(\"a\", \"b\")\n")
    with pytest.raises(AssertionError, match="PW"):
        parse_seed(_script('user("a", "x")'))
