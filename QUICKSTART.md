# 操作清单

## 本地首次运行

```bash
cd D:\ops-assistant
copy .env.example .env
# 编辑 .env 填入：
# - OPENCLOW_API_KEY（openclow 平台密钥）
# - OPS_ASSISTANT_API_KEY（业务应用自身密钥，本地开发可留空）

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 灌入运维语料
python -m eval.ingest_corpus

# 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8600

# 另一个终端启动前端（用 8601 避免和后端 8600 冲突）
streamlit run web/app.py --server.port 8601
```

## 本地验证

```bash
# 健康检查
curl http://127.0.0.1:8600/health

# 直接问（如果配置了 OPS_ASSISTANT_API_KEY，需带上 X-API-Key）
curl -X POST http://127.0.0.1:8600/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OPS_ASSISTANT_API_KEY" \
  -d '{"query": "备案期间怎么访问 openclow？"}'

# 追问（用返回的 session_id）
curl -X POST http://127.0.0.1:8600/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OPS_ASSISTANT_API_KEY" \
  -d '{"query": "那前端呢？", "session_id": "上一步返回的 session_id"}'
```

## 一键部署到服务器

```bash
python D:\workbuddy\2026-08-23-20-37-57\outputs\deploy_ops_assistant.py
```

部署脚本会完成：上传代码 → 安装依赖 → 灌入语料 → 安装 systemd 服务 → 启动并验证。

## 手动部署到服务器

```bash
# 1. 上传代码到 /opt/ops-assistant
# 2. 上传 .env 文件（含 OPENCLOW_API_KEY 和 OPS_ASSISTANT_API_KEY）

# 3. 安装依赖
/opt/miniconda/envs/openclaw/bin/pip install -r /opt/ops-assistant/requirements.txt

# 4. 灌入语料（幂等，重复文档会返回 chunks:0）
cd /opt/ops-assistant
/opt/miniconda/envs/openclaw/bin/python -m eval.ingest_corpus

# 5. 复制并启动 systemd 服务
cp /opt/ops-assistant/deploy/ops-assistant-api.service /etc/systemd/system/
cp /opt/ops-assistant/deploy/ops-assistant-ui.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ops-assistant-api ops-assistant-ui
systemctl start ops-assistant-api ops-assistant-ui
```

## 线上验证

- 健康检查：http://103.236.98.200:8600/health
- 聊天接口：POST http://103.236.98.200:8600/api/chat（需 X-API-Key）
- Web 界面：http://103.236.98.200:8601
