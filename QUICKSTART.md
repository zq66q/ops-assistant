# 操作清单（Agentic 版）

## 本地首次运行

```bash
cd D:\ops-assistant
copy .env.example .env
# 编辑 .env 填入：
#   OPENCLOW_API_KEY  —— openclow 平台密钥
#   OPS_ASSISTANT_API_KEY —— 业务侧密钥（本地可留空）
#   OPS_TOOL_MODE=sim     —— 先用固定样本跑通；演示真实排障再改 real

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 灌入 语料 + 排障手册 到 openclow 知识库（幂等）
python -m eval.ingest_corpus

# 启动后端（8600）
uvicorn app.main:app --host 0.0.0.0 --port 8600

# 另开终端启动前端（8601）
streamlit run web/app.py --server.port 8601
```

## 本地验证

```bash
# 健康检查
curl -s http://127.0.0.1:8600/health

# 同步排障（配置了 OPS_ASSISTANT_API_KEY 需带 X-API-Key）
curl -s -X POST http://127.0.0.1:8600/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"服务 /health 返回 503，日志报 Invalid API key"}'

# 流式排障（看工具轨迹）
curl -s -N -X POST http://127.0.0.1:8600/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query":"服务 503 了"}'

# 工具审计
curl -s http://127.0.0.1:8600/api/audit
```

> 首次默认 `OPS_TOOL_MODE=sim`：工具返回固定样本，agent 走「收集证据→下结论」流程，无需真实主机权限即可演示。

## 切换真实排障（real）

把 `.env` 改成：

```ini
OPS_TOOL_MODE=real
OPS_TARGET_HEALTH=http://103.236.98.200:8000/health
OPS_TARGET_UI=http://103.236.98.200:8501
```

重启后端即可。探活（probe_http）与手册检索（search_runbook → /rag/search）对网络可达目标有效；日志/资源/服务状态在目标主机同机部署时采集真实数据，否则降级为样本。

## 两种工具协议

- `OPS_AGENT_TOOL_PROTOCOL=json`（默认）：LLM 输出标准 JSON action，兼容现有 openclow `/chat/raw`，无需改平台即可跑。
- `OPS_AGENT_TOOL_PROTOCOL=native`：走原生 function-calling，需 openclow 的 `/chat/raw` 已升级透传 `tools`（见 `src/api/models.py` / `src/api/routes/chat.py`）并重新部署。

## 评测

```bash
python -m eval.run_agent_eval           # 工具序列/结论/拒答（mock 编排管线）
python -m eval.run_retrieval_eval       # 检索 Recall@k / MRR（mock 验证指标）
python -m eval.run_agent_eval --live    # 真实 LLM 驱动（需线上连接 + 余额）
python -m eval.run_retrieval_eval --live  # 真实 RAG 召回（需已灌库）
```

## 测试与 CI

```bash
pip install -r requirements-dev.txt
pytest -v
```

## 一键部署到服务器（systemd）

```bash
# 1. 上传代码到 /opt/ops-assistant（SFTP）
# 2. 上传 .env（含 OPENCLOW_API_KEY、OPS_ASSISTANT_API_KEY）
# 3. 安装依赖
/opt/miniconda/envs/openclaw/bin/pip install -r /opt/ops-assistant/requirements.txt
# 4. 灌入语料
cd /opt/ops-assistant && /opt/miniconda/envs/openclaw/bin/python -m eval.ingest_corpus
# 5. 安装并启动服务
cp /opt/ops-assistant/deploy/ops-assistant-api.service /etc/systemd/system/
cp /opt/ops-assistant/deploy/ops-assistant-ui.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ops-assistant-api ops-assistant-ui
systemctl start ops-assistant-api ops-assistant-ui
```

线上验证：健康检查 `http://103.236.98.200:8600/health`，Web `http://103.236.98.200:8601`。
