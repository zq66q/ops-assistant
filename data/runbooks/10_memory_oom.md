# 内存 OOM / 进程被杀死

症状：
- 进程被杀（OOMKiller），日志 `Killed` / `OOMKilled`（容器）
- 服务重启循环，或大面积进程被 systemd/内核杀死

根因：
- 进程内存超限（泄漏或配置过大）；容器/主机内存不足；无资源上限

信号/证据：
- free -m / dmesg（OOMKiller 记录）/ journalctl -k
- 容器：kubectl describe pod -> Last State: OOMKilled；kubectl get events
- 进程 RSS 是否持续增长（内存泄漏）

排查步骤：
1. dmesg | grep -i oom 看被杀进程与内存峰值
2. free -m / top 看内存压力与 swap
3. 判断是配置过大（调低 max_tokens/缓存）还是内存泄漏（看 RSS 曲线）
4. 容器则调大 resources.limits.memory 或排查应用泄漏
5. 修完重启服务，观察内存曲线是否稳定

来源：SRE 排障 / 内存资源管理实践
