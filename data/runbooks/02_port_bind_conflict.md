# Runbook: 端口被占（Address already in use）

**症状**
- 服务起不来，启动日志 `Address already in use` / `bind: address already in use`
- 旧进程仍占用端口，新进程绑定失败后在 crash-restart 循环里打转

**根因**
- 上一次进程未退出，端口 8000/8501 被残留进程占用
- 其它应用抢占同一端口

**排查步骤**
1. `ss -lntp | grep <port>` 看谁占用端口
2. 确认占用者是否是僵尸进程 `ps aux | grep <pid>`
3. 停掉占用者或改端口配置
4. `systemctl restart openclaw-api.service` 并验证监听成功

**参考**: 部署常见问题
