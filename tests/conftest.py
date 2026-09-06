"""pytest 公共夹具：隔离数据库、固定 sim 工具模式、把项目根加入 sys.path。

注意：必须在 import 任何 app.* / tools.* / agent.* 之前设置环境变量，
因为 app.config 在模块加载时就读取 os.getenv。
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 隔离 DB 到项目内临时目录（D:\hardness 下，沙盒可写），避免污染 ./data/sessions.db
_tmp = ROOT / ".test_tmp"
_tmp.mkdir(exist_ok=True)
os.environ["OPS_SESSION_DB_PATH"] = str(_tmp / "sessions.db")
os.environ["OPS_AUDIT_DB_PATH"] = str(_tmp / "audit.db")
# 测试一律走 sim + json 协议，确定且无外部依赖
os.environ["OPS_TOOL_MODE"] = "sim"
os.environ["OPS_AGENT_TOOL_PROTOCOL"] = "json"
os.environ["OPENCLOW_BASE_URL"] = "http://localhost:8000"
os.environ["OPENCLOW_API_KEY"] = "test-key"
# 测试走免鉴权开发模式：清掉业务侧 key/users，否则 authenticate 会要求有效 key 导致 test_api 401
os.environ["OPS_ASSISTANT_API_KEY"] = ""
os.environ["OPS_ASSISTANT_USERS"] = ""
# 测试期间关闭后台健康巡检，避免去打真实靶点
os.environ["OPS_MONITOR_ENABLED"] = "false"
