# Runbook: 磁盘 / 内存 写满（资源耗尽）

**症状**
- 服务写入失败或响应变慢
- 日志 `No space left on device` / `OOMKilled` / 数据库 `disk full`
- 监控显示磁盘或内存持续打满

**根因**
- 日志/缓存/向量库占满磁盘
- 内存不足触发 OOM 或 swap 抖动

**排查步骤**
1. `df -h` 看磁盘、`free -m` 看内存
2. `du -sh /opt/openclaw/data/*` 定位占空间大户
3. 清理过期日志/上传文件，必要时扩容
4. 若是内存问题，调低 max_tokens 或增加内存，并 `systemctl restart`

**参考**: 资源排障
