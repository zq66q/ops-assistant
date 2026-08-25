# ICP 备案与端口访问

## 备案现状

- 域名：psyidc.com
- 备案提交方：腾讯云
- 服务器：磐石数据（只提供机房，不参与备案流程）
- 当前状态：备案审核中，工信部系统尚未能查到

## 查询方式

- **进度查询**：腾讯云备案控制台 https://console.cloud.tencent.com/beian
- **是否通过查询**：工信部官网 https://beian.miit.gov.cn 或站长工具 https://icp.chinaz.com/psyidc.com

## 备案期端口策略

备案审核期间，80 和 443 端口会被封：

- 不能通过 http://psyidc.com 访问
- 不能通过 https://psyidc.com 访问
- Caddy 自动 HTTPS 暂时无法工作

但以下端口可直接访问：

- 22：SSH
- 8000：FastAPI 后端
- 8501：Streamlit 前端

## 备案期临时访问地址

```
后端 Swagger：http://103.236.98.200:8000/docs
前端界面：    http://103.236.98.200:8501
```

## 备案通过后会怎样

- 80/443 解封
- Caddy 自动申请 HTTPS 证书
- 可通过 https://psyidc.com 统一访问前后端
