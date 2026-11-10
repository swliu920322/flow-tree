"""pytest 适配: 原 mapping/execution 中的 pytest 专属逻辑, 语义保持不变。"""
import json
import os
import posixpath
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .. import baseline as bl
from ..issues import ERROR, WARNING, Issue
from ..pytest_report import classify, parse_junit
from . import ClassifyOutput, Runner, RuntimeProbe, register

# pytest 选项: 会筛选/截断/改写执行范围或与 FlowTree 自行注入的报告冲突
_FORBIDDEN_LONG = {
    "--deselect", "--lf", "--last-failed", "--ff", "--failed-first", "--nf", "--new-first",
    "--sw", "--stepwise", "--maxfail", "--exitfirst", "--collect-only", "--co",
    "--junitxml", "--junit-xml", "--confcutdir", "--ignore", "--ignore-glob",
    "--pyargs", "--keep-duplicates", "--markers", "--help", "--version",
}
_FORBIDDEN_SHORT = ("-k", "-m", "-x", "-p", "-h", "-V")


def pytest_args(argv: List[str]) -> Optional[List[str]]:
    """识别 pytest 调用并返回其后的参数; 无法识别返回 None。"""
    head = Path(argv[0]).name
    if head in ("pytest", "py.test"):
        return argv[1:]
    if head.startswith("python") and argv[1:3] == ["-m", "pytest"]:
        return argv[3:]
    return None


def _forbidden_arg(arg: str) -> Optional[str]:
    if not arg.startswith("-"):
        return None
    if arg.startswith("--"):
        name = arg.split("=", 1)[0]
        return name if name in _FORBIDDEN_LONG else None
    for s in _FORBIDDEN_SHORT:
        if arg == s or arg.startswith(s):  # -k expr / -kexpr / -x / -pfoo
            return s
    return None


class PytestRunner(Runner):
    name = "pytest"
    stdout_file = "stdout.txt"
    evidence_kind = "pytest plugin JSON report (real nodeids, collected set) cross-checked against JUnit XML"
    artifacts = (("plugin_report", "plugin-report.json"), ("junit", "junit.xml"),
                 ("stdout", "stdout.txt"), ("stderr", "stderr.txt"))

    def validate_entry(self, entry, where, issues):
        rest = pytest_args(entry.argv)
        if rest is None:
            issues.append(Issue(ERROR, "mapping.argv_not_pytest", where, "argv must invoke pytest (e.g. [python, -m, pytest, ...] or [pytest, ...])"))
        else:
            for a in rest:
                bad = _forbidden_arg(a)
                if bad:
                    issues.append(Issue(ERROR, "mapping.argv_scope_option", where, f"argv option {a!r} ({bad}) changes collection/report scope; execution range could not be proven"))
        for j, t in enumerate(entry.tests):
            tw = f"{where}.tests[{j}]"
            nid = t.nodeid
            base = nid.split("[", 1)[0]  # 参数实例括号内允许出现任意字符
            if "::" not in nid or nid != nid.strip() or "*" in base or "?" in base:
                issues.append(Issue(ERROR, "mapping.bad_nodeid", tw, f"nodeid {nid!r} must be an exact pytest nodeid like path/to/test_x.py::test_name (no wildcards or prefixes)"))
            else:
                file_part = nid.split("::", 1)[0]
                if file_part.startswith("/") or ".." in posixpath.normpath(file_part).split("/"):
                    issues.append(Issue(ERROR, "mapping.bad_nodeid", tw, f"nodeid path {file_part!r} must be relative to the pytest rootdir and stay inside it"))
                if not file_part.endswith(".py"):
                    issues.append(Issue(ERROR, "mapping.bad_nodeid", tw, f"nodeid path {file_part!r} must be a .py test file"))

    def resolve_executable(self, entry, cwd, python, env):
        head = entry.argv[0]
        if Path(head).name.startswith("python"):
            if python:
                return python if os.path.exists(python) else None
            return shutil.which(head, path=env.get("PATH")) if not os.path.dirname(head) else (
                str((cwd / head).resolve()) if (cwd / head).exists() else None)
        if os.path.dirname(head):
            p = (cwd / head).resolve() if not os.path.isabs(head) else Path(head)
            return str(p) if p.exists() else None
        return shutil.which(head, path=env.get("PATH"))

    def _probe_python(self, entry, exe, python):
        """用于探测运行时的 python: python* 形式用其本身; pytest 脚本形式必须显式给 --python。"""
        if Path(entry.argv[0]).name.startswith("python"):
            return exe
        return python

    def runtime_cache_key(self, entry, exe, python, cwd):
        return self._probe_python(entry, exe, python)

    def runtime(self, entry, exe, python, env, cwd, project_root):
        py = self._probe_python(entry, exe, python)
        if not py:
            return RuntimeProbe(None)
        info, err = bl.probe_runtime(py, env)
        return RuntimeProbe(info["digest"] if info else None, info, err if info is None else None)

    def build_command(self, entry, exe, adir):
        cmd = [exe, *entry.argv[1:]]
        rest_index = len(entry.argv) - len(pytest_args(entry.argv))
        inject = ["-p", "flowtree_pytest_plugin", "-p", "no:cacheprovider", f"--junitxml={adir / 'junit.xml'}"]
        return cmd[:rest_index] + inject + cmd[rest_index:]

    def env_additions(self, adir, run_id, attempt_id):
        return {"FLOWTREE_REPORT": str(adir / "plugin-report.json"), "FLOWTREE_RUN_ID": run_id,
                "FLOWTREE_ATTEMPT_ID": attempt_id}

    def classify(self, adir, *, run_id, attempt_id, cwd, returncode, required, runtime_now):
        report_path, junit_path = adir / "plugin-report.json", adir / "junit.xml"
        report = None
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = None
        junit, jerr = parse_junit(str(junit_path)) if junit_path.exists() else (None, "junit report missing")
        c = classify(report, junit, jerr, run_id=run_id, attempt_id=attempt_id, cwd=cwd,
                     returncode=returncode, required_nodeids=required)
        extra: Dict = {"evidence_kind": self.evidence_kind}
        if report:
            extra.update({"runtime": report.get("runtime"), "pytest_rootdir": report.get("rootdir"),
                          "collected_count": len(report.get("collected", [])),
                          "deselected_count": len(report.get("deselected", []))})
        actual = (report or {}).get("runtime", {}).get("digest")
        # 插件没起来 (无报告) 时没有"实际运行时"可比, 沿用执行前探测值
        return ClassifyOutput(c, extra, actual, runtime_applicable=report is not None)


register(PytestRunner())
