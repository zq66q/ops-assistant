# 服务器部署与更新流程

## 实际运行方式

服务器 IP：103.236.98.200（域名 psyidc.com，备案中）

openclow 在服务器上通过 systemd 运行：

```bash
systemctl status openclaw-api.service
systemctl status openclaw-ui.service
```

## 项目位置

- 代码目录：`/opt/openclow`
- Python 环境：`/opt/miniconda/envs/openclaw`
- 启动命令：`cli.py serve`
- 数据目录：`/opt/openclow/data/`

## 代码更新流程

1. 本地改完代码，py_compile 检查
2. 用 SFTP 上传到 `/opt/openclow`
3. 服务器上执行：
   ```bash
   systemctl restart openclaw-api.service
   systemctl restart openclaw-ui.service
   ```
4. 检查状态：
   ```bash
   systemctl status openclaw-api.service
   journalctl -u openclaw-api.service -n 100 --no-pager
   ```

## 为什么没用 Docker

项目里有 Docker 配置，但部署时为了快速上线用了 conda + systemd。Docker 方案保留为后续备案通过、Caddy 可用时的迁移目标。

## 日志排查

```bash
# 后端实时日志
journalctl -u openclaw-api.service -f

# 前端实时日志
journalctl -u openclaw-ui.service -f
```
