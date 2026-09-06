# Runbook: 健康检查 503（组件降级）

**症状**
- `/health` 返回 503，`status=degraded`
- 某个组件（llm / rag / memory）为 error，其余 ok
- 服务进程在跑，但请求报 5xx

**根因**
- 某个上游组件（LLM / 向量库 / 数据库）异常导致整体降级
- 并非进程未监听，而是组件健康检查失败

**排查步骤**
1. `curl -s http://<host>:8000/health` 看哪个组件 error
2. 针对对应组件看 `journalctl -u openclaw-api.service -n 100`
3. 逐组件排掉（LLM 查凭据、RAG 查向量库、Memory 查数据库）
4. 修复后 `systemctl restart` 并复测 /health

**参考**: 端口与备案期间访问方式
