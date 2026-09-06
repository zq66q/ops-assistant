# 数据库连接池耗尽 / 连接爆满

症状：
- 请求报 `too many connections` / `connection pool exhausted` / `TimeoutError`
- 接口大量 5xx，数据库端到端连接数骤增

根因：
- 连接池/数据库 max_connections 过小；连接未释放泄漏；慢查询长期占用连接

信号/证据：
- MySQL：show status like 'Threads_connected/%'
- Postgres：select count(*) from pg_stat_activity
- 应用日志：连接池等待超时 / acquire timeout

排查步骤：
1. 查数据库当前连接数 vs 上限（max_connections / pool size）
2. 定位「谁占着连接」：慢查询、长事务、连接泄漏的进程
3. 查到慢 SQL/长事务 → 优化或 kill
4. 调大 pool size / max_connections（或限制应用并发）到合理值
5. 排查应用是否未正确归还连接（连接池泄漏）

来源：MySQL/PostgreSQL 排障实践
