import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

class CircuitSyncer:
    """负责将本地电路与遥测数据异步/同步上报到 FlowTree 中心服务器"""

    def __init__(self, server_url: str = "http://127.0.0.1:8000"):
        self.server_url = server_url.rstrip("/")

    def sync(self, circuit_data: Dict[str, Any]) -> Dict[str, Any]:
        sync_endpoint = f"{self.server_url}/api/projects/sync"
        payload = json.dumps(circuit_data).encode("utf-8")

        req = urllib.request.Request(
            sync_endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return {"synced": True, "server_url": self.server_url, "response": result}
        except urllib.error.URLError as e:
            return {"synced": False, "server_url": self.server_url, "error": f"服务器未启动或无法连接: {e}"}
        except Exception as e:
            return {"synced": False, "server_url": self.server_url, "error": str(e)}
