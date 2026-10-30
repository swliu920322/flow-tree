import os
from pathlib import Path
from typing import Dict, Any, List, Optional

class ProjectScanner:
    """负责深度扫描目标工程目录，提取技术文档、API与用户故事"""

    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir).resolve()

    def discover_docs(self) -> Dict[str, Path]:
        candidates = [
            "USER_STORY_MAP.md",
            "TESTING_AND_ROLE_GUIDE.md",
            "PROJECT_DOC.md",
            "ACCEPTANCE_TEST_PLAN.md",
            "README.md"
        ]
        found = {}
        for c in candidates:
            p = self.target_dir / c
            if p.exists():
                found[c] = p
        return found

    def inspect_tech_stack(self) -> Dict[str, Any]:
        has_flutter = (self.target_dir / "pubspec.yaml").exists()
        has_fastapi = (self.target_dir / "backend" / "app" / "main.py").exists()
        has_docker = (self.target_dir / "backend" / "docker-compose.yml").exists() or (self.target_dir / "docker-compose.yml").exists()

        return {
            "has_flutter": has_flutter,
            "has_fastapi": has_fastapi,
            "has_docker": has_docker,
            "backend_dir": (self.target_dir / "backend") if has_fastapi else None,
            "frontend_dir": (self.target_dir / "lib") if has_flutter else None,
        }

    def scan(self) -> Dict[str, Any]:
        docs = self.discover_docs()
        tech = self.inspect_tech_stack()
        project_name = self.target_dir.name

        return {
            "projectName": project_name,
            "projectPath": str(self.target_dir),
            "docs": docs,
            "tech": tech
        }
