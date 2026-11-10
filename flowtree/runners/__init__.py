"""测试运行器适配: 每个 runner 负责 命令构造、映射参数/标识校验、运行时探测、机器报告解析。

公共执行器 (flowtree.execution) 继续负责 attempt、超时、进程组清理、前后基线、落盘与索引。
runner 之间的证据类型不同, 必须如实声明 (manifest `evidence_kind`), 不伪造不存在的独立来源。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..issues import Issue
from ..pytest_report import Classification


@dataclass
class RuntimeProbe:
    digest: Optional[str]
    info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None     # 非空: 已知环境前置缺失 → 执行 blocked / 重检 unknown


@dataclass
class ClassifyOutput:
    classification: Classification
    extra: Dict[str, Any] = field(default_factory=dict)   # 合并进 manifest
    actual_runtime_digest: Optional[str] = None
    runtime_applicable: bool = True    # 是否把"实际运行时"与执行前探测值比较


class Runner:
    name: str = ""
    stdout_file: str = "stdout.txt"
    evidence_kind: str = ""
    # (artifact 名称, 文件名)
    artifacts: Tuple[Tuple[str, str], ...] = ()

    def validate_entry(self, entry, where: str, issues: List[Issue]) -> None:
        raise NotImplementedError

    def resolve_executable(self, entry, cwd: Path, python: Optional[str], env: Dict[str, str]) -> Optional[str]:
        raise NotImplementedError

    def runtime_cache_key(self, entry, exe: Optional[str], python: Optional[str], cwd: Path):
        return None

    def runtime(self, entry, exe: Optional[str], python: Optional[str], env: Dict[str, str],
                cwd: Path, project_root: Path) -> RuntimeProbe:
        return RuntimeProbe(None)

    def build_command(self, entry, exe: str, adir: Path) -> List[str]:
        raise NotImplementedError

    def env_additions(self, adir: Path, run_id: str, attempt_id: str) -> Dict[str, str]:
        return {}

    def classify(self, adir: Path, *, run_id: str, attempt_id: str, cwd: str, returncode: int,
                 required: List[str], runtime_now) -> ClassifyOutput:
        raise NotImplementedError


_REGISTRY: Dict[str, Runner] = {}


def register(runner: Runner) -> None:
    _REGISTRY[runner.name] = runner


def get_runner(name: str) -> Runner:
    return _REGISTRY[name]


def runner_names() -> Tuple[str, ...]:
    return tuple(_REGISTRY)


from . import pytest_runner, flutter_runner  # noqa: E402,F401  (注册)
