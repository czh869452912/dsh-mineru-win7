# 骨架定向验证记录

日期：2026-11-10。Python：宿主 `.venv` 的 3.8.10 x64。
范围：配置与代理路径合同、真实 ZIP 打包/安装、canonical run_profile 启动、
四个工具调用、所属 Fiber 卸载、Provider close、服务和工具撤销、包移除。
只使用临时 profile，不访问 MinerU 服务器。

最终命令：宿主 Python `-m pytest tests -q --junitxml=<本次目录>/pytest.xml`。
结果：**24 passed，pytest 2.86 秒，退出 0**。
日志、XML、命令、Python 版本及耗时保存在
`.out/scaffold-20261110-173751-95f5f8/`（本地忽略目录）。

首次运行因工具参数的 minLength 超出固定宿主 JSON Schema 子集而失败，
修正为调用阶段的非空校验后重新验证。首次 23 passed / 1 failed 的原始日志和 XML
保存在 `.out/scaffold-20261110-173718-4873bc/`，不改写为成功。

这仅证明骨架包与当前宿主接口可协作。HTTP、解析、产物、真实服务、Win7 实机、
x86 与 Portable 发行资格都尚未验证。不执行完整宿主回归或发行门禁。
