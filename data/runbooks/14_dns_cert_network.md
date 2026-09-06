# DNS 解析失败 / 证书过期 / 网络连接异常

症状：
- 域名无法解析 / 解析到错误地址；curl 报 `Could not resolve host`
- HTTPS 访问失败，`SSL certificate expired` / `certificate not yet valid`
- 连接超时 / connection refused / 连到无响应

根因：
- DNS 配置错/缓存/上游 DNS 故障（解析）
- 证书过期或未生效、主机名不匹配（证书）
- 网络不通、防火墙/端口被封、后端未监听（连接）

信号/证据：
- nslookup/dig <域名>          → 解析结果
- openssl s_client -connect <host>:443  → 证书有效期/主题
- curl -v 看握手/错误；nc -vz host port → 端口连通

排查步骤：
1. dig/nslookup 解析是否正确；检查 /etc/resolv.conf、公司/公网 DNS
2. 证书：openssl 看有效期与 CN/SAN 是否匹配；过期则续期/重签
3. 网络：nc/telnet 测端口；看防火墙/安全组是否放行；确认服务是否监听
4. 区分：解析错=DNS；握手错/证书=证书；连不通=网络/端口
5. 修完 curl -v 复测

来源：DNS/网络/证书排障实践
