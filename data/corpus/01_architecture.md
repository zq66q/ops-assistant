# openclow 项目架构与访问方式

## 技术栈

- **后端**：FastAPI，默认端口 8000
- **前端**：Streamlit，默认端口 8501
- **生产反代**：Caddy，负责 80/443 + 自动 HTTPS
- **部署方式**：服务器实际用 systemd 运行，不是 Docker

## 分层架构

openclow 采用 L1~L7 分层：

1. L1 LLM 客户端
2. L2 嵌入与向量
3. L3 RAG 检索
4. L4 记忆
5. L5 Agent
6. L6 业务场景
7. L7 API / UI

## 生产访问方式

| 服务 | 开发模式 | 生产模式（备案通过前） | 生产模式（备案通过后） |
|---|---|---|---|
| 后端 | http://localhost:8000 | http://103.236.98.200:8000 | https://psyidc.com/api |
| 前端 | http://localhost:8501 | http://103.236.98.200:8501 | https://psyidc.com |

## 重要区别

项目仓库里有 Dockerfile 和 docker-compose.prod.yml，但实际生产服务器上跑的是 systemd 服务：

- `openclaw-api.service`
- `openclaw-ui.service`

代码目录是 `/opt/openclow`，不是 git 仓库；更新方式是 SFTP 上传后 `systemctl restart`。
