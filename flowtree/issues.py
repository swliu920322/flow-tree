from dataclasses import dataclass, asdict
from typing import Any, Dict, List

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: str  # error | warning
    code: str      # 稳定机器码, 如 story.duplicate_id
    where: str     # 文件与位置, 如 SAV-001.branches[0].continuation
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def has_errors(issues: List[Issue]) -> bool:
    return any(i.severity == ERROR for i in issues)
