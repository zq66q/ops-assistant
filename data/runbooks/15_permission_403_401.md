# 权限 / 403 / 401 访问被拒

症状：
- 接口/页面返回 403 Forbidden / 401 Unauthorized
- 文件/目录读写报 `Permission denied`；服务无法读配置/密钥

根因：
- 认证缺失/凭证无效（401）；无授权或 ACL/Nginx deny（403）
- 进程/用户对该路径无读/写权限；selinux/a. 权限位错

信号/证据：
- 区分 401(未认证) 与 403(已认证但无权)
- Nginx/应用日志看 401/403 来源；ls -l / namei 看权限
- 服务账户(如 systemd User)对 /opt/.../.env 等是否有权限

排查步骤：
1. 401：检查是否带对凭证（API Key / token / 密码），Key 是否有效
2. 403：Nginx 是否 deny/ACL；应用 RBAC 是否授权
3. 文件权限：ls -l 看属主/属组/权限位；必要时 chmod/chown 给运行账户
4. 服务进程以哪个用户跑（systemd User），确保能读配置/写数据目录
5. 复测：换正确凭证/授权后访问

来源：权限/认证排障实践
