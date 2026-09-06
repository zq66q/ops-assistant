# K8s 应用故障（Pod 异常 / 崩溃循环 / 探针失败）

症状：
- Pod 状态 CrashLoopBackOff / Error / 频繁重启；应用访问不通
- 就绪/存活探针失败导致 Pod 反复重启或流量被摘除

根因：
- 容器内应用启动即失败（入口命令 / 依赖 / 配置错）
- liveness/readiness/startup 探针阈值过严或路径错
- 资源超限（OOMKilled）或镜像拉取失败（ImagePullBackOff）

信号/证据：
- kubectl get pods                     → 状态 / Restarts / READY
- kubectl describe pod <name>          → Events：BackOff / OOMKilled / probe failed / Failed to pull image
- kubectl logs <pod> --previous        → 崩溃前日志（应用真正报错）
- kubectl get events --sort-by=.metadata.creationTimestamp | grep <pod>

排查步骤：
1. kubectl get pods 定位异常 Pod 与状态
2. kubectl describe pod <name> 看 Events：区分 探针失败 / OOM / 拉镜像失败 / 启动即崩
3. kubectl logs --previous 看应用报错（依赖、配置、启动命令）
4. 按根因修：镜像/入口命令/环境变量资源 limit/探针 path 与阈值
5. kubectl rollout status / 重新 deploy 后看 Pod READY

来源：Kubernetes Debugging Cluster / Debugging your application（kubernetes.io/docs/tasks/debug/）
