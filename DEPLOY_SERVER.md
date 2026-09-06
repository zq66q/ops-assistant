# ops-assistant 服务器部署手册（DEPLOY_SERVER）

> 目标：把 ops-assistant 部署到服务器 `103.236.98.200`（CentOS），`OPS_TOOL_MODE=real`，取证全真实。
> 你 SSH 上去，按顺序执行即可。全程不用 root 也可（建 `ops` 用户更稳；下面示例用 root，本地验证可）。

---

## 0) 前提
- SSH 能连到 `103.236.98.200`。
- 服务器有 `/opt/miniconda`（之前部署 openclow 用过）；Python ≥3.10。
- openclow 平台在同机 `8000` 端口跑着。

---

## 1) 上传代码到 `/opt/ops-assistant`
在你**本地**用 WinSCP / scp 把 `D:\ops-assistant` 内容拷过去（**排除** `.venv`、`.git`、`__pycache__`、`data/*.db`）。
```bash
# 若服务器没有目标目录先建
mkdir -p /opt/ops-assistant
```
> 或用 git：服务器 `git clone <你的repo> /opt/ops-assistant`。

## 2) 建独立环境 + 装依赖（服务器上）
```bash
cd /opt/ops-assistant
/opt/miniconda/bin/python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3) 配置 `.env`
```bash
cat > /opt/ops-assistant/.env <<'EOF'
# openclow 平台（同机）
OPENCLOW_BASE_URL=http://127.0.0.1:8000
OPENCLOW_API_KEY=oc_qHL-xxxxxx        # 你真实的 key

# 取证全真实
OPS_TOOL_MODE=real
OPS_TARGET_HEALTH=http://127.0.0.1:8000/health
OPS_TARGET_UI=http://127.0.0.1:8501
OPS_SERVICE_NAME=openclaw-api

# 前端连后端（同机）
OPS_ASSISTANT_API=http://127.0.0.1:8600
OPS_ASSISTANT_API_KEY=ops_xxx          # 业务侧 key，可自定义
# （可选多用户）OPS_ASSISTANT_USERS={"default":"ops_xxx","alice":"ops_alice","bob":"ops_bob"}

# 数据
OPS_SESSION_DB_PATH=./data/sessions.db
OPS_AUDIT_DB_PATH=./data/tool_audit.db
EOF
```

## 4) 灌入知识库（corpus + runbooks）
```bash
cd /opt/ops-assistant
.venv/bin/python -m eval.ingest_corpus
# 预期打印各文档 chunks；/rag/status 能看到 47+ 文档
```

## 5) 安装 systemd 服务
`/etc/systemd/system/ops-assistant-api.service`：
```ini
[Unit]
Description=ops-assistant API
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/opt/ops-assistant
EnvironmentFile=/opt/ops-assistant/.env
ExecStart=/opt/ops-assistant/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8600
Restart=always
[Install]
WantedBy=multi-user.target
```
`/etc/systemd/system/ops-assistant-ui.service`：
```ini
[Unit]
Description=ops-assistant UI
After=network.target ops-assistant-api.service
[Service]
Type=simple
User=root
WorkingDirectory=/opt/ops-assistant
EnvironmentFile=/opt/ops-assistant/.env
ExecStart=/opt/ops-assistant/.venv/bin/streamlit run web/app.py --server.port 8601 --server.address 0.0.0.0
Restart=always
[Install]
WantedBy=multi-user.target
```
启动：
```bash
systemctl daemon-reload
systemctl enable ops-assistant-api ops-assistant-ui
systemctl restart ops-assistant-api ops-assistant-ui
systemctl status ops-assistant-api ops-assistant-ui --no-pager
```

## 6) 放行端口
```bash
firewall-cmd --permanent --add-port=8600/tcp --add-port=8601/tcp && firewall-cmd --reload
# ufw 则：ufw allow 8600 8601
```
腾讯云**安全组**：放行 `8600`、`8601`（TCP）。

## 7) 验证
```bash
curl http://127.0.0.1:8600/health                                   # 后端 ok
curl -H "X-API-Key: ops_xxx" http://127.0.0.1:8600/api/sessions     # 鉴权/会话
```
浏览器打开：`http://103.236.98.200:8601`。

**测真实取证**：问「服务正常吗？」→ 真探活应返回 **200**（你服务器现在正常），证明 real 全真实。

---

## 常见问题
- **改了代码**：`git pull`/上传后 `systemctl restart ops-assistant-api ops-assistant-ui`。
- **前端起不来**：看 `journalctl -u ops-assistant-ui.service -n 50`；确认 `.env` 的 `OPS_ASSISTANT_API=http://127.0.0.1:8600`。
- **权限/写库**：若非 root 跑，给运行用户 `data/` 写权限；`.env` 权限 `chmod 600`。
- **回滚**：上传前备份 `/opt/ops-assistant`。
