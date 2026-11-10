# 定向验证记录

## 可重复离线测试与实际 Portable 插件旅程（2026-11-10，0.1.0-dev.3）

本轮补充 scripts/verify_offline.py、offline_fixture.py、offline_worker.py、
offline_browser.cjs 和操作指南。测试仅使用 loopback 模拟服务，未部署 GPU/OCR，
未使用 LLM。观察器使用真实宿主 jobs 的 quiet 通知，避免后台完成触发模型请求。

测试中截图复查发现停止按钮会保留上一任务的 job ID。已将 Web 控制绑定到 task_id，
切换任务后隐藏其他任务的控制，停止成功和读取已完成结果后清除按钮，补充实际浏览器回归。
原版 apps/web/dist 未改动。修复后生成新的 dev.3 ZIP，未重建宿主 Portable。

**精确受测插件 ZIP：** `.local_plugin/dist/dsh-mineru-win7-0.1.0-dev.3.zip`（相对于宿主根目录）。
SHA-256：`04819ecac162882bf3d34932ac5cbc3826d31134500a6799b2ce6647b74dc95e`。
已核对 ZIP 文件清单、Web 文件哈希与 Python 3.8 语法。此记录写入源码后不重建该已验收 ZIP；
包内的 verification.md 保留打包时的历史版本，以外部本轮回执作为精确包验证证据。

| 实际运行环境 | 结果 | 私有原始证据目录 |
|---|---|---|
| 既有 x64 Portable，包内 Python 3.8.10 | fresh/cold/removed 全通过，86.906 秒 | `%TEMP%/mru-x64-1110-final/` |
| 既有 x86 Portable，包内 Python 3.8.10 | fresh/cold/removed 全通过，87.890 秒 | `%TEMP%/mru-x86-1110-final/` |
| 源码宿主，无浏览器模式 | 三阶段通过，27.938 秒 | `%TEMP%/mru-source-headless-1110/` |
| 新入口、包生命周期及严格 Web 合同 | 10 passed，33.14 秒，退出 0 | `.out/offline-consumers-20261110-215815/` |

两个实际 Portable 均来自宿主 `dist/creative-preview-20261107-complete/`，文件分别为
`dsh-win7-portable-creative-preview-20261107-x64.zip` 和 `...-x86.zip`。
包哈希分别为 `416cae0b53914daf4c1cb62e10d5ee957f9b4a2c05620510c3f430216ebb5dcb`、
`51819bd0ff393f0aacf817fe9ab76ef93e797936a8acc8c01574e89a102f3682`。
回执记录完整路径、原包构建来源、实际进程 PID、位数与宿主/插件模块来源。
Portable 子进程只导入该提取包的宿主及隔离 home 中的已安装插件，不使用开发 venv。

每个实际 Portable 的 fresh 阶段完成 PDF ZIP、PNG JSON、DOCX ZIP、真实文件哈希、
跨 owner 任务和 job 拒绝、后台完成通知、本地停止后远端仍 processing、202/409、
丢失 POST 确认不重试。浏览器完成健康→提交→后台等待→结果→阅读/下一段，
会话切换、停止控制归属/清除、失败提示、确认清理及文本 HTML 不执行。
Cold 独立进程恢复原 owner 与缓存，删除一个任务不影响其他任务；Removed 经 CLI 移除后
独立启动，服务/客户端图/面板消失且未忘记的产物保留。Cold 和 Removed 的 HTTP 请求均为零。
每条启用浏览器的完整旅程共 10 次 POST，无远端 DELETE。所有观察器、插件 ZIP 和 Portable ZIP
在运行前后哈希相同，结束后九个 Web 监听端口均已关闭。

浏览器路径：Browser 插件未提供，使用现有 Playwright / Chromium 108.0.5359.0。
两种架构均验证 1440×1000 与 390×844；三个阶段共六份 browser.json 通过，
控制台 error/warning 均为零，截图已人工复查。卸载页面的 API Key 设置提示属于原版引导，
本轮没有输入凭据或调用模型。日志和 ready.json 含本地连接令牌，不公开或整体提交原始 home。

定向 pytest 选择 `tests/test_offline.py tests/test_web.py tests/test_package_lifecycle.py`，
覆盖新增入口的路径/输出保护、模拟器协议，以及新清单和客户端产物的实际安装消费者。
新 UI 回归由两份精确 Portable 包中的实际浏览器操作覆盖，没有重复运行无关宿主全量测试。

原始失败保留于 `%TEMP%/mru-source-1110a/`（cwd 已由宿主创建）、`...1110b/`
（观察器误用历史 Inbox 属性）、`...1110c/`、`...1110d/`（原版引导分阶段弹出）。
相应测试工具问题已修复；dev.2 的源码/Portable 通过记录位于 `...mru-source-1110e/`、
`...mru-x64-1110a/`、`...mru-x86-1110a/`，不拼接为 dev.3 的回执。
测试工具最初的两项失败与修复记录保留于 `.out/offline-targeted-20261110-214730/` 和
`.out/offline-targeted-fixed-20261110-214825/`。

这是**指定既有 Portable 上的插件定向兼容检查**，不是宿主完整发行验收。
尚未完成真实 MinerU 互通/识别质量、真实模型对话自动选工具、Win7 SP1 实机和统一发行门禁。
复现命令与环境参数见 [无 GPU 验证指南](offline-testing.md)。

## 客户端完整功能开发版（2026-11-10，0.1.0-dev.2）

选择范围为整个独立插件的测试集合，包含变更提供端、工具消费者、真实套接字、
真实 ZIP 安装与 canonical Web 图、Remote 合同、冷启动和 Fiber 卸载；
这是插件子系统定向检查，没有运行宿主全量回归或 Portable 发行门禁。

| 环境 | 结果 | 本地证据目录 |
|---|---|---|
| Python 3.8.10 x64 | 106 passed，32.49 秒，退出 0 | `.out/candidate-x64-20261110-205923/` |
| Python 3.8.10 x86 | 106 passed，35.55 秒，退出 0 | `.out/candidate-x86-20261110-205850/` |
| 原版 Web + Chromium 108 | 桌面 1440×1000、窄屏 390×844 通过，控制台无错误 | `.out/browser-candidate-20261110/` |

Python 命令/日志/XML 保存在上述目录；x86 额外记录运行时、位数和墙钟耗时。
x86 使用宿主 `.goose/tools/python-3.8.10-win32/python.exe`，测试工具从开发 venv
复用纯 Python pytest/pytest_asyncio，禁用其他自动插件；这不为产品添加运行依赖。
x64 命令为 `../../.venv/Scripts/python.exe -m pytest tests -q --durations=10 --junitxml=<目录>/pytest.xml`。

范围包括：TLS 系统信任拒绝/私有 CA 接受、凭据轮换、取消/超时/卸载，
multipart 快照与会话 scoped fs 拒绝、owner 跨会话隔离、未知提交不重试，
202/409/404、缓存重启、ZIP 路径/链接/膨胀/碰撞、JSON/图片预算、产物哈希与保守清理，
分页清单、jobs 完成通知和本地停止、Web 严格 Remote 注册与卸载。

浏览器因未提供 Browser 插件而使用 bundled Playwright 与本地 Chromium 108。
在临时 DSH_HOME 安装当前快照，启动 canonical Web profile 和显式本地协议夹具；
检查页面身份、可见面板、原版引导关闭、健康→提交→结果→阅读→下一段、窄屏边界，
保存 qa.json 和 desktop.png/mobile.png。夹具退出后关闭服务，未修改用户 profile。
浏览器证据不代表 GPU 解析或真实服务互通。

验证脚本 `scripts/verify_live.py` 已生成公开 PDF/PNG/DOCX，
并在本地协议夹具上验证完整 13 步调用。真正的远端服务运行尚未执行。
样本保存在 `.out/public-probes-20261110-final/`，不要将其标成真实服务回执。

开发中发现并保留：初始 ZIP/后台通知夹具问题（`.out/workflow-*`），
Web 使用非持久化 Session 的失败（`.out/web-20261110-203629/` 等），
连续下载遇到 WinError 5 的原始失败（`.out/probe-script-20261110-205624/`、
`.out/probe-repeat-20261110-2058/01.log`）。后者经堆栈定位为发布目录重命名，
加入仅针对 Windows 5/32 的最多六次、累计等待 0.85 秒的本地重试；不重试网络。
对应永久拒绝、暂时锁定、取消和直接消费者修复检查在
`.out/publish-verified-20261110-205845/` 通过 33 项，再运行上述稳定候选集合。
首次取消用例断言未考虑宿主 abort 覆盖结果，原始失败保留于 `.out/publish-fix-20261110-205813/`。

**剩余验收：** 本机无 MinerU GPU 服务；未验证真实镜像身份、实际 PDF/图片/Office
识别结果、Win7 SP1 实机、提取后的 x86/x64 Portable 与宿主完整发行资格。
当前结果仅用于客户端开发版，不提升上述验收状态。

## 健康检查首轮实现（2026-11-10）

运行时：宿主 `.venv` Python 3.8.10 x64。
选择范围：配置、真实回环 HTTP 服务、直接 Provider 消费者及 canonical 插件包生命周期。
这覆盖新增传输提供端、工具输出 Schema、宿主信号接入、安装和所属 Fiber 卸载。

最终命令：`../../.venv/Scripts/python.exe -m pytest tests -q --durations=10 --junitxml=.out/health-20261110-201248/pytest.xml`。
结果：**56 passed，pytest 2.58 秒，退出 0**。
命令、运行时、日志、XML、墙钟耗时保留于 `.out/health-20261110-201248/`。
先前通过的 54 项运行保留于 `.out/health-20261110-201122/`；新增预取消和非有限浮点回归后运行上述最终检查。

包含：公开代理前缀、Office/native/unknown 字段识别、Content-Length/chunked/EOF 分帧、
预算与截断、重定向/压缩/非 JSON 拒绝、总期限、信号/调用取消、卸载终止请求及拒绝复用。
打包后在临时 profile 中验证配置与未配置两种工具路径、服务和工具撤销、包移除。

本次未连接真实 MinerU，未验证 HTTPS 服务、鉴权、私有 CA、上传、状态/结果或 Win7 实机。
未运行宿主完整回归与 Portable 发行门禁。本地回环样本不用于提升真实部署验收状态。

## 初始骨架

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
