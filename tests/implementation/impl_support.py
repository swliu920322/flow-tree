"""实现测试的共享常量。独立于 conftest 命名, 避免与 tests/independent/conftest.py 在同一次运行中同名冲突。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"
