# 典型踩坑与排查

## 1. Swagger 没有 Authorize 按钮

**现象**：Swagger 页面上锁头图标点了没反应，没有 Authorize 弹窗。

**原因**：自定义 `openapi()` 没声明 `ApiKeyAuth` 安全方案。

**解决**：在 `src/api/server.py` 重写 `openapi()`，声明 `securitySchemes` 和全局 `security`。

## 2. GitHub push 报 "could not read Username"

**现象**：沙盒里 push 失败，错误看起来是认证问题。

**原因**：通常是网络问题（DNS 污染 / 国际链路不稳定），不是账号问题。

**解决**：用一次性 PAT URL 重试，或换网络环境再推。

## 3. 生产环境 /docs 返回 500

**现象**：开发环境 Swagger 正常，生产访问 /docs 报错。

**原因**：生产依赖缺失、模型初始化失败或 .env 配置不对。

**解决**：看 `journalctl -u openclaw-api.service -n 100` 定位具体错误。

## 4. Docker vs systemd  confusion

**现象**：文档写 Docker，上去排查发现没有容器在跑。

**原因**：部署时用了更快的 systemd + conda 方案。

**解决**：生产排障第一步永远是验证实际运行环境，不要盲信文档。

## 5. 备案期 Caddy 无法启动

**现象**：Caddy 报错无法申请证书或监听 443。

**原因**：80/443 被封，Caddy 需要这些端口做自动 HTTPS。

**解决**：备案通过前用 IP:8000 / IP:8501 直接访问。
