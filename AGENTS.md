# MinerU Win7 插件开发约定

- 目标为 Windows 7 SP1 / Python 3.8.10 / DSH Python Plugin API 1。
- 首期合同是 Doc2markdonw 的 MinerU 3.4.2 protocol v2 + Office Gateway。
- 服务基址保留 `/mineru/`；不用 `/v1/tasks` 替代当前 `/tasks`。
- 插件间通过 ctx 服务交互；工具、服务、任务及网络资源随所属 Fiber 撤销。
- 无用户明确要求时不修改 DSH 核心或 Doc2markdonw 部署。
- 当前为骨架；禁止把占位返回、mock 测试或缓存源码称为真实服务器验收。
- 实现上传前，接入宿主文件权限和任务所属会话校验；实现网络前，明确请求取消、大小限制和超时。
- 不凭空提供远端取消功能，不跟随返回的容器内部 status_url/result_url。
- Python 使用 typing 泛型、显式 UTF-8；不得添加 Python 3.9+ 语法/API。
- 修改模型工具需更新 tests；先定向验证，稳定发行候选再执行完整门禁。

开发入口见 README.md、docs/architecture.md 和 docs/ROADMAP.md。
