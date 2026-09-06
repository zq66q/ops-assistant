# Runbook: 模型初始化失败（LLM 凭据无效）

**症状**
- 服务 /health 返回 503，`components.llm=error`
- 日志反复出现 `Invalid API key` / `AuthenticationError` / `model init failed`
- 进程存在但 crash-restart 循环（NRestarts 上升）

**根因**
- `.env` 里 `LLM_API_KEY` 无效、过期或缺失
- `LLM_BASE_URL` 不可达或指向错误服务
- embedding 模型名与后端不匹配

**排查步骤**
1. 核对 `/opt/openclow/.env` 的 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
2. 用 `curl` 直接打一次 LLM 端点，确认凭据与连通性
3. 修正后 `systemctl restart openclaw-api.service`
4. `journalctl -u openclaw-api.service -n 100` 确认初始化日志通过

**参考**: 典型踩坑 #3（生产 /docs 500）
