# 磁盘写满 / 文件系统 No space left

症状：
- 服务写入失败，日志 `No space left on device` / `disk full`
- 数据库/日志/上传/向量库写入报错，服务响应变慢

根因：
- 日志、临时文件、旧备份、上传文件占满磁盘
- 分区过小或数据目录无限增长

信号/证据：
- df -h               → 看哪个挂载点满
- du -sh /var/log/* /tmp/* <数据目录>  → 定位占空间大户
- journalctl --disk-usage  → 系统日志占用

排查步骤：
1. df -h 找打满的挂载点
2. du -sh 逐级定位大目录/大文件（日志、上传、备份、向量库）
3. journalctl --vacuum-size=500M 清日志；清临时文件/旧备份；必要时扩容
4. 若向量库/数据库大，看是否需要归档/收缩（如 SQLite VACUUM）
5. 修完 systemctl restart 服务，写一条测试数据验证

来源：SRE Monitoring / 通用磁盘排障实践
