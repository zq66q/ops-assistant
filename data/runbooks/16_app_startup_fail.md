# 应用启动失败（框架/依赖/配置）

症状：
- 服务起不来，启动日志报 `ModuleNotFoundError` / `ImportError` / `KeyError`
- uvicorn/gunicorn 启动即退出；`.env` 变量缺失导致初始化失败

根因：
- 依赖未安装/版本不符；python/环境路径错
- 缺配置项或配置格式错（环境变量、配置文件）
- 入口命令错 / 模块路径错；数据库或外部依赖连不上

信号/证据：
- 服务启动日志前几行（报的异常类型与模块）
- pip list / conda list 核对依赖版本
- .env / 配置文件与代码期望的变量对齐

排查步骤：
1. 看启动日志第一次异常（ImportError/KeyError/config error）
2. 核对依赖：pip install -r requirements.txt 是否装全、版本符
3. 核对环境变量：代码 Getenv 的每个变量是否在 .env 有值
4. 入口/命令：uvicorn app.main:app 模块路径是否对；工作目录是否对
5. 外部依赖（DB/Redis）是否可连；修完重启看是否 initialize 成功

来源：应用框架启动排障 / SRE 可观测
