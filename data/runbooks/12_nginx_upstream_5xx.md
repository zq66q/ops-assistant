# Nginx 502 / 504 / upstream 错误

症状：
- 前端访问返回 502 Bad Gateway / 504 Gateway Timeout
- Nginx 日志 `upstream timed out` / `connect() failed` / `no live upstreams`

根因：
- 后端服务挂了/起不来（502）；后端处理超时或太慢（504）
- upstream 负载全部不可用；配置代理地址错；健康检查失败被摘除

信号/证据：
- 状态码区分：502=后端不可达，504=后端超时
- journalctl -u nginx / error.log -> upstream 行
- 直接 curl 后端地址看是否可达 / /health

排查步骤：
1. curl 后端地址/端口；后端挂了就修后端
2. 看 nginx error log 定位是 connect 失败(502) 还是 timed out(504)
3. 504 则排查后端慢（慢SQL/IO/锁）或调大 proxy_read_timeout
4. 确认 upstream 全部健康（健康检查/权重）
5. 复测：curl -I 前端地址，看是否 200

来源：Nginx troubleshooting / SRE 上游故障排障
