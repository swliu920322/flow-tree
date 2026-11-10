"""FlowTree pytest 报告插件 (仅依赖标准库; 由 `-p flowtree_pytest_plugin` 在被测项目的解释器内加载)。

记录 JUnit 无法无损提供的事实: 真实 nodeid、实际 rootdir、本次最终收集集合与被剔除项、逐项 setup/call/teardown 结果、
收集错误、改变收集范围的生效选项、会话退出码与终态。环境变量:
  FLOWTREE_REPORT      报告输出路径 (未设置则插件不工作)
  FLOWTREE_RUN_ID / FLOWTREE_ATTEMPT_ID  必须原样写回报告, 用于识别旧文件/串用
报告先写一份 terminal=false 的开始记录, 会话结束时覆盖为 terminal=true; 进程被杀时留下的就是未完成记录。
"""
import hashlib
import json
import os
import platform
import sys
import time

import pytest

PLUGIN_VERSION = "1"
REPORT_SCHEMA = 1

_state = {"path": None, "report": None}


def runtime_info():
    """被测解释器的实际运行环境。FlowTree 在执行前后用同一函数探测, 以判断环境是否变化。"""
    try:
        from importlib import metadata
        dists = sorted(
            "%s==%s" % ((d.metadata["Name"] or "").lower(), d.version)
            for d in metadata.distributions() if d.metadata["Name"]
        )
    except Exception as e:  # pragma: no cover
        dists = ["<unavailable: %s>" % e]
    pytest_version = pytest.__version__
    info = {
        "executable": os.path.realpath(sys.executable),
        "python_version": sys.version,
        "platform": platform.platform(),
        "pytest_version": pytest_version,
        "plugin_version": PLUGIN_VERSION,
        "distributions": dists,
    }
    info["digest"] = "sha256:" + hashlib.sha256(
        json.dumps(info, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return info


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _junit_key(nodeid):
    try:
        from _pytest.junitxml import mangle_test_address
        names = mangle_test_address(nodeid)
        return {"classname": ".".join(names[:-1]), "name": names[-1]}
    except Exception:
        return None


def _scope_options(config):
    """会改变收集/执行范围的生效选项 (来自 argv、PYTEST_ADDOPTS、配置文件 addopts 的合并结果)。"""
    o = config.option
    altering = {}
    for name in ("keyword", "markexpr", "deselect", "ignore", "ignore_glob"):
        v = getattr(o, name, None)
        if v:
            altering[name] = v
    for name in ("lf", "failedfirst", "newfirst", "stepwise", "collectonly"):
        if getattr(o, name, False):
            altering[name] = True
    if getattr(o, "maxfail", 0):
        altering["maxfail"] = o.maxfail
    return altering


def _write(terminal, exitstatus=None):
    rep = _state["report"]
    if rep is None or _state["path"] is None:
        return
    rep["terminal"] = terminal
    rep["exitstatus"] = None if exitstatus is None else int(exitstatus)
    rep["finished_at"] = time.time() if terminal else None
    _atomic_write(_state["path"], rep)


def pytest_configure(config):
    path = os.environ.get("FLOWTREE_REPORT")
    if not path:
        return
    _state["path"] = path
    inipath = getattr(config, "inipath", None)
    _state["report"] = {
        "schema": REPORT_SCHEMA,
        "plugin_version": PLUGIN_VERSION,
        "run_id": os.environ.get("FLOWTREE_RUN_ID"),
        "attempt_id": os.environ.get("FLOWTREE_ATTEMPT_ID"),
        "rootdir": str(config.rootpath),
        "invocation_dir": str(config.invocation_params.dir),
        "inifile": str(inipath) if inipath else None,
        "args": list(config.invocation_params.args),
        "addopts_env": os.environ.get("PYTEST_ADDOPTS"),
        "scope_altering_options": _scope_options(config),
        "runtime": runtime_info(),
        "started_at": time.time(),
        "collected": [],
        "deselected": [],
        "collect_errors": [],
        "items": {},
        "terminal": False,
        "exitstatus": None,
        "finished_at": None,
    }
    _write(False)


def pytest_collectreport(report):
    rep = _state["report"]
    if rep is not None and report.failed:
        rep["collect_errors"].append({"nodeid": report.nodeid, "longrepr": str(report.longrepr)[:500]})


def pytest_deselected(items):
    rep = _state["report"]
    if rep is not None:
        rep["deselected"].extend(i.nodeid for i in items)


def _record_collection(items):
    rep = _state["report"]
    if rep is None:
        return
    rep["collected"] = [
        {"nodeid": i.nodeid, "junit": _junit_key(i.nodeid), "xfail_marker": i.get_closest_marker("xfail") is not None}
        for i in items
    ]


# trylast: 其他插件 (-k/-m/--lf 等) 完成剔除后再记录最终集合
@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    _record_collection(items)


def pytest_runtest_logreport(report):
    rep = _state["report"]
    if rep is None:
        return
    entry = {"outcome": report.outcome, "wasxfail": getattr(report, "wasxfail", None)}
    if report.outcome != "passed":
        entry["longrepr_head"] = str(report.longrepr)[:300]
    rep["items"].setdefault(report.nodeid, {})[report.when] = entry
    _write(False)  # 增量落盘: 中途被杀时能看到已完成的阶段


def pytest_sessionfinish(session, exitstatus):
    _write(True, exitstatus)
