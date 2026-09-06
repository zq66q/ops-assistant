# Redis 缓存击穿 / 雪崩 / 内存超限

症状：
- 缓存失效后大量请求直击数据库（击穿/雪崩），数据库压力骤增
- Redis 报 `OOM command not allowed` / maxmemory；读写超时

根因：
- 热点 key 过期瞬间并发打到 DB（击穿）；大量 key 同时失效（雪崩）
- maxmemory 打满触发淘汰/拒绝写；bigkey / 大内存占用

信号/证据：
- redis-cli info memory -> used_memory / maxmemory_policy
- redis-cli monitor / slowlog -> 慢命令、bigkey
- 应用日志：缓存 miss 峰值、DB 连接暴涨

排查步骤：
1. info memory 看内存与淘汰策略；确认是否 OOM
2. slowlog / bigkeys 定位大 key；object encoding 检查
3. 击穿/雪崩：给热点 key 加逻辑过期+互斥/分布式锁；失效时间加随机抖动
4. 内存不足：清理无用 key、设 maxmemory-policy(如 volatile-lru)、扩容
5. 加缓存预热/多级缓存，避免集中失效

来源：Redis 内存/缓存排障实践
