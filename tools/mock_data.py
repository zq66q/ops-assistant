"""sim 模式：按「当前问题」解析场景，返回对应的一份自洽样本。

场景（resolve_scenario 按关键词判定，顺序优先）：
    out_of_scope / k8s / nginx / redis / db_conn / dns_cert / permission / app_startup
    / port_bind / resource / healthy / model_init / unknown
每个场景给 5 个工具各返回一段自洽证据。由 agent 循环调用 set_context(问句) 后生效。
"""
from __future__ import annotations

_active = ""

SERVICE = "openclaw-api"
KB = "http://103.236.98.200:8000"


def set_context(question: str) -> None:
    global _active
    _active = question or ""


def resolve_scenario(q: str) -> str:
    q = (q or "").lower()
    if not q.strip():
        return "model_init"
    if any(k in q for k in ("删除", "删掉", "删光", "格式化", "rm -rf", "清空", "drop table", "drop database", "全部删")):
        return "out_of_scope"
    if any(k in q for k in ("crashloopbackoff", "k8s", "kubernetes", "pod ")):
        return "k8s"
    if any(k in q for k in ("502", "504", "bad gateway", "nginx", "upstream")):
        return "nginx"
    if any(k in q for k in ("redis", "maxmemory", "雪崩", "击穿", "缓存")):
        return "redis"
    if any(k in q for k in ("too many connections", "连接池", "max_connections", "数据库连接", "connections")):
        return "db_conn"
    if any(k in q for k in ("证书", "过期", "ssl", "https", "dns", "certificate")):
        return "dns_cert"
    if any(k in q for k in ("403", "401", "permission", "权限", "forbidden", "denied")):
        return "permission"
    if any(k in q for k in ("启动失败", "启动不了", "import error", "modulenotfound", "起不来", "config error", "依赖缺失")):
        return "app_startup"
    if any(k in q for k in ("address already in use", "端口", "占用", "bind", "被占")):
        return "port_bind"
    if any(k in q for k in ("磁盘", "disk", "内存", "写满", "占满", "空间不足", "no space", "oom")):
        return "resource"
    if any(k in q for k in ("正常", "健康", "还好", "没问题", "healthy", "服务状态", "是否正常")):
        return "healthy"
    if any(k in q for k in ("503", "invalid api key", "api key", "authenticationerror", "鉴权失败", "llm 组件", "凭据")):
        return "model_init"
    return "unknown"


FIXTURES: dict[str, dict[str, str]] = {
    "model_init": {
        "probe_http": f"HTTP 503 Service Unavailable\n目标: {KB}/health\n响应体: {{\"status\":\"degraded\",\"components\":{{\"llm\":\"error\",\"rag\":\"ok\"}}}}\n耗时: 1.2s\n推断: LLM 组件异常（非端口未监听）。",
        "query_logs": "最近日志(ERROR): Invalid API key / model init failed: AuthenticationError / start failed retry 4/5\n推断: 连续 Invalid API key 指向凭据配置问题。",
        "check_resources": f"主机资源 ({KB}):\nCPU 12% 内存 41% 磁盘 78% -> 未打满，排除资源耗尽。",
        "service_status": f"{SERVICE}.service:\nactive (running) NRestarts=4 (crash-restart 循环)\n推断: 初始化阶段反复失败。",
        "search_runbook": "《模型初始化失败》: 根因 .env 中 LLM_API_KEY/LLM_BASE_URL 无效或缺失。处置: 核对 .env -> curl 验证 -> systemctl restart -> journalctl 确认。",
    },
    "port_bind": {
        "probe_http": f"连接被拒绝 (Connection refused)\n目标: {KB}:8000\n推断: 端口未监听，服务绑定失败。",
        "query_logs": "uvicorn.error: [Errno 98] address already in use on 0.0.0.0:8000\nstart failed, retry 3/5\n推断: 端口 8000 被占用。",
        "check_resources": f"主机资源 ({KB}):\nCPU 22% 内存 47% 磁盘 81% -> 非资源问题，重点排查端口占用。",
        "service_status": f"{SERVICE}.service:\nactivating (auto-restart) NRestarts=5\n推断: 绑定端口报错，反复重启。",
        "search_runbook": "《端口被占 Address already in use》: 根因残留/其它进程占用。处置: ss -lntp -> kill/换端口 -> systemctl restart -> 验证监听。",
    },
    "resource": {
        "probe_http": f"HTTP 200 OK（响应偏慢 3.4s）\n目标: {KB}/health\n推断: 服务可达但受力争资源影响。",
        "query_logs": "storage: sqlite disk I/O error: No space left on device\nrag: write failed: disk full\nswap usage 88%\n推断: 磁盘/内存接近打满。",
        "check_resources": f"主机资源 ({KB}):\nCPU 76% 内存 91% 磁盘 95% -> 资源严重紧张，是当前主因。",
        "service_status": f"{SERVICE}.service:\nactive (running) NRestarts=0\n推断: 服务存活但受主机资源压力影响。",
        "search_runbook": "《资源耗尽》: 处置: df -h / free -m -> du -sh 定位大户 -> 清理日志/临时/扩容 -> 若内存问题调 max_tokens。",
    },
    "healthy": {
        "probe_http": f"HTTP 200 OK\n目标: {KB}/health\n响应体: {{\"status\":\"running\",\"components\":{{\"llm\":\"ok\",\"rag\":\"ok\"}}}}\n推断: 服务健康。",
        "query_logs": "最近日志(INFO): startup complete / /health 200 ok\n无 ERROR/CRITICAL。",
        "check_resources": f"主机资源 ({KB}):\nCPU 11% 内存 35% 磁盘 62% -> 正常。",
        "service_status": f"{SERVICE}.service:\nactive (running) NRestarts=0\n推断: 稳定运行。",
        "search_runbook": "《健康检查通过》: /health 200，所有组件 ok，无需处置。",
    },
    "out_of_scope": {
        "probe_http": "该请求涉及破坏性操作（删除/清空/格式化），超出只读排障范围，无法执行/不给建议。",
        "query_logs": "拒绝执行：破坏性操作不在排障范围。",
        "check_resources": "拒绝执行：请勿执行破坏性操作。",
        "service_status": "拒绝执行：破坏性操作需人工审批。",
        "search_runbook": "未检索到相关手册；该请求属于越界，建议备份并由人工确认。",
    },
    "k8s": {
        "probe_http": "访问服务失败：Pod 不可达 / 502。\n推断: K8s 内 Pod 未就绪或反复重启。",
        "query_logs": "kubectl logs: Error: CrashLoopBackOff / OOMKilled / liveness probe failed / Back off restarting failed container\n推断: 容器启动即失败或探针/资源超限。",
        "check_resources": f"集群/主机资源 ({KB}):\nCPU/内存未见异常（非资源导致）。",
        "service_status": "Pod 状态: CrashLoopBackOff, Restarts=6\n推断: 反复重启，启动阶段失败。",
        "search_runbook": "《K8s 应用故障（Pod 异常/崩溃循环）》: kubectl get pods -> describe pod 看 Events(BackOff/OOMKilled/probe failed) -> logs --previous -> 修镜像/入口命令/资源limit/探针。",
    },
    "nginx": {
        "probe_http": "HTTP 502 Bad Gateway\n目标: 前端地址\n推断: 后端不可达导致 Nginx 无法转发。",
        "query_logs": "nginx error.log: connect() failed / no live upstreams / upstream timed out\n推断: 后端未监听或超时。",
        "check_resources": f"主机资源 ({KB}):\n资源正常，非压力导致。",
        "service_status": f"{SERVICE}.service:\nactive 但端口未监听/后端异常\n推断: 后端服务不可达。",
        "search_runbook": "《Nginx 502/504 upstream》: 502=后端不可达 504=后端超时。处置: curl 后端 -> 修后端 -> systemctl restart -> 调 proxy_read_timeout(504) -> 复测。",
    },
    "redis": {
        "probe_http": "接口超时/报错，缓存层异常。\n推断: Redis 不可写或命中失败。",
        "query_logs": "redis: OOM command not allowed when used memory > maxmemory\noom_rejected / 缓存 miss 峰值\n推断: Redis maxmemory 打满，拒绝写入。",
        "check_resources": f"主机内存: 偏高（Redis 用内存）。\n推断: 内存压力/大 key。",
        "service_status": "redis-server: running，但拒绝写命令。\n推断: 内存上限触发 OOM 策略。",
        "search_runbook": "《Redis 缓存击穿/雪崩/内存超限》: info memory -> bigkeys/slowlog -> 清理大key/设 maxmemory-policy -> 击穿加互斥/失效时间抖动 -> 多级缓存/预热。",
    },
    "db_conn": {
        "probe_http": "接口 503 / 超时（数据库导致）。",
        "query_logs": "db: too many connections / connection pool exhausted / acquire timeout\n推断: 数据库连接数超限。",
        "check_resources": f"主机资源 ({KB}):\n资源正常，非资源导致。",
        "service_status": f"{SERVICE}.service:\nactive，但请求因 DB 连接超时。",
        "search_runbook": "《数据库连接池耗尽》: 查 Threads_connected vs max_connections -> 慢查询/长事务/连接泄漏 -> 优化或调大 pool/max_connections。",
    },
    "dns_cert": {
        "probe_http": "HTTPS 握手失败：certificate expired / SSL error。\n推断: 证书或 DNS/网络异常。",
        "query_logs": "ssl_error: certificate expired / Could not resolve host <domain>\n推断: 证书过期 或 DNS 解析失败。",
        "check_resources": f"主机资源 ({KB}):\n正常。",
        "service_status": f"{SERVICE}.service:\nactive，但外部访问受影响。",
        "search_runbook": "《DNS/证书/网络》: dig/nslookup 查解析 -> openssl s_client 查证书有效期/CN/SAN -> nc 测端口 -> 续期证书/修 DNS/放行防火墙。",
    },
    "permission": {
        "probe_http": "HTTP 403 Forbidden / 401 Unauthorized。",
        "query_logs": "nginx/app: 401 Unauthorized / 403 Forbidden / Permission denied\n推断: 鉴权失败或权限不足。",
        "check_resources": f"主机资源 ({KB}):\n正常。",
        "service_status": f"{SERVICE}.service:\nactive，但请求被拒。",
        "search_runbook": "《权限 403/401》: 区分 401(未认证)/403(无权) -> 查凭证是否有效 -> nginx deny/ACL -> 文件 ls -l 权限位 -> chmod/chown 给运行账户。",
    },
    "app_startup": {
        "probe_http": "连接被拒 / 503（服务没起来）。",
        "query_logs": "Traceback: ModuleNotFoundError: No module named 'xxx' / KeyError: 'KEY' / ImportError\nstartup failed\n推断: 依赖未装/配置缺失/入口错。",
        "check_resources": f"主机资源 ({KB}):\n正常，非资源导致。",
        "service_status": f"{SERVICE}.service:\nfailed 或自动重启\n推断: 启动即退出。",
        "search_runbook": "《应用启动失败（框架/依赖/配置）》: 看启动日志首个异常 -> pip install -r requirements 核对依赖 -> 核对 .env 变量 -> 核对 uvicorn 入口/工作目录 -> 检查外部依赖(DB/Redis)可连。",
    },
    "unknown": {
        "probe_http": "信息不足，无法定位具体服务；请提供更多现象（进程名/端口/报错）。",
        "query_logs": "信息不足，无法确定要排查哪个服务/日志；请补充现象。",
        "check_resources": "信息不足，无法判断是否为资源问题；请补充现象。",
        "service_status": "信息不足，未指定目标服务。",
        "search_runbook": "未找到与描述匹配的排障手册；请提供更具体的报错或现象。",
    },
}


def evidence(tool: str) -> str:
    """按当前问题场景返回某个工具的样本证据。"""
    scenario = resolve_scenario(_active)
    sc = FIXTURES.get(scenario) or FIXTURES["unknown"]
    return sc.get(tool) or FIXTURES["unknown"].get(tool, "")


# 兼容旧调用名
def probe_evidence() -> str:
    return evidence("probe_http")


def logs_evidence() -> str:
    return evidence("query_logs")


def resources_evidence() -> str:
    return evidence("check_resources")


def service_evidence() -> str:
    return evidence("service_status")


def runbook_evidence(_q: str = "") -> str:
    return evidence("search_runbook")
