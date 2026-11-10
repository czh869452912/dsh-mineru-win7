# dsh-mineru-win7

Windows 7 / Python 3.8.10 DSH 的独立 MinerU 客户端插件，连接自部署的
legacy `/tasks` protocol v2 与 Doc2markdonw Office Gateway。运行时无第三方依赖。

当前开发版 `0.1.0-dev.3` 已实现上传、任务状态、JSON/ZIP 下载、安全落盘、
分段阅读、持久化缓存、会话隔离、宿主 jobs 后台等待和原版 Web 外壳中的可选面板。
本机没有 MinerU GPU 服务；已验证本地协议与宿主集成，尚未完成真实服务、
Win7 实机和完整发行验收。指定既有 x86/x64 Portable 中的插件安装、冷启动与卸载
已完成定向检查，详见 [验证记录](docs/verification.md)。

## 安装

从 DSH 宿主仓库执行，先停止目标 profile：

```powershell
.venv\Scripts\python.exe dsh.py plugin --profile web add .\.local_plugin\dsh-mineru-win7
.venv\Scripts\python.exe dsh.py --profile web
```

Portable 中用 `dsh.bat` 替代 `.venv\Scripts\python.exe dsh.py`。
安装会复制当前快照；修改源码后需重新安装。不会默认修改任何产品预设。
打包与移除：

```powershell
.venv\Scripts\python.exe dsh.py plugin --profile web pack .\.local_plugin\dsh-mineru-win7 .\mineru-win7-dev.zip
.venv\Scripts\python.exe dsh.py plugin --profile web remove dsh-mineru-win7
```

## 配置

在目标 profile 的 `cordis.patch.yml` 中覆盖已安装的 `mineru-win7` 条目：

```yaml
- id: mineru-win7
  config:
    baseURL: http://<server>:18080/mineru/
    protocol: legacy-tasks-v2
    officeMode: pdf_ocr
    requestTimeoutSeconds: 360
    enableWebPanel: true
    # credentialRef: MINERU_TOKEN
    # caFile: C:/certificates/mineru-ca.pem
```

未配置地址时读取 `MINERU_BASE_URL`。保留公开地址中的 `/mineru/` 等代理前缀，
不要使用 UI 地址或容器内部地址。停止 profile、修改配置后重启；不支持配置热更新。
`credentialRef` 仅保存引用，由宿主 `ctx.credentials.resolve()` 每次请求解析 Bearer 凭据。
无需鉴权时留空；密钥不写入插件配置。TLS 默认系统信任，`caFile` 可添加私有 CA。
不跟随重定向、结果 URL 或代理环境变量，不重试上传，不请求远端取消接口。

| 配置 | 默认值 | 用途 |
|---|---:|---|
| connectTimeoutSeconds / readTimeoutSeconds | 15 / 360 | 建连与每次读取期限，秒 |
| requestTimeoutSeconds | 360 | 单次请求总期限，含排队、上传和下载 |
| pollIntervalSeconds / waitTimeoutSeconds | 2 / 1800 | 轮询间隔和本地等待上限，秒 |
| maxUploadBytes | 104857600 | 单文件上传上限，100 MiB |
| maxDownloadBytes / maxExtractBytes | 134217728 / 268435456 | 下载和解压字节上限 |
| maxJsonBytes / maxResponseBytes | 8388608 / 65536 | 结果 JSON 与健康/任务元数据上限 |
| maxFiles / maxTasks | 2000 / 1000 | 单次产物数与本地任务数 |
| maxStorageBytes | 1073741824 | 本地存储预算，1 GiB |
| readMaxChars | 12000 | 每次阅读的字符上限 |
| storageDirectory | 空 | 默认 `$DSH_HOME/data/mineru-win7`，未设 DSH_HOME 时 `~/.dsh/data/mineru-win7` |

预算达到上限会返回结构化错误；不会自动删除用户文件腾出空间。
所有范围限制见 `python/mineru_win7/config.py`。

## 工具与流程

除健康检查外，调用必须有真实、已注册的宿主 Agent/session。
返回的 `task_id` 是本地标识，只能由创建任务的 Agent/session 使用；不能填远端 ID。

| 工具 | 参数示例 | 行为 |
|---|---|---|
| mineru_health | `{}` | 健康 JSON 与格式识别；`ok` 表示请求成功，组件是否就绪需查看 data |
| mineru_submit | `{"file_path":"C:/docs/报告.docx","format":"zip"}` | 经会话 fs 权限读取快照后单文件上传 |
| mineru_status | `{"task_id":"本地 ID"}` | 查询并保存任务状态 |
| mineru_result | `{"task_id":"本地 ID"}` | 获取或校验缓存，返回产物清单和目录 |
| mineru_list | `{"offset":0,"limit":20}` | 当前 owner 的分页任务列表 |
| mineru_files | `{"task_id":"本地 ID","offset":0,"limit":20}` | 分页列出全部产物 |
| mineru_read | `{"task_id":"本地 ID","offset":0,"limit":4000}` | 默认读取首个 Markdown，使用 next_offset 续读 |
| mineru_wait | `{"task_id":"本地 ID","background":true}` | 使用宿主 jobs 等待，可通知并下载结果 |
| mineru_forget | `{"task_id":"本地 ID"}` | 清理该 owner 的本地记录与未修改产物 |

推荐：health → submit → wait 或 status → result → files/read。
`read.artifact` 可选择清单中的 `.md/.txt/.json`；offset 按字符计数。
list/files 每页最多 100 条，使用 next_offset/eof；结果响应最多内嵌 100 个产物，
`manifest_truncated` 为真时通过 files 获取余下清单。

支持 PDF、常见图片和 doc/docx/ppt/pptx/xls/xlsx。Office 默认 `pdf_ocr`；
`office_mode=native` 仅允许 OOXML。可选 `backend`、`parse_method`、`language`、
`format=zip|json`、`images`，实际服务支持程度以其版本为准。
后台等待需要宿主 jobs 与 tool-jobs controller；极简宿主可用前台等待。
`job_kill` 只停止本地等待，远端任务继续。提交响应丢失时保存
`submission-unknown`，不自动重试，以避免重复收费或重复解析。

ZIP 拒绝路径穿越、Windows 设备名/ADS、链接、重复大小写路径、加密、ZIP64
及超限解压。JSON 仅保存内联图片，忽略远端 URL。缓存记录 SHA-256；读取前校验。
忘记任务遇到修改或未知文件会拒绝删除并保留数据；卸载保留所有持久化任务与产物。
更换服务地址或凭据引用会隔离原服务的记录，不自动迁移。

## Web 使用

安装到 Web profile 后，原版页面右下角出现 **MinerU**。选择已创建的会话，
输入宿主电脑上的文件路径，检查连接、提交、刷新状态、后台等待、下载并分段阅读。
面板显示有效连接配置，修改使用宿主插件配置并重启。设置 `enableWebPanel: false`
可隐藏面板。面板经 Connection / Typert Remote 调用同一套宿主工具和权限策略，
不修改 `apps/web/dist`，也不绕过文件权限。文档正文只按纯文本显示。

## 开发和后续联调

在本插件目录运行，保持 `.local_plugin/<repo>` 布局可直接找到宿主；
其他布局先设置 `DSH_HOST_ROOT`：

```powershell
../../.venv/Scripts/python.exe scripts/build_client.py
../../.venv/Scripts/python.exe -m pytest tests -q
../../.venv/Scripts/python.exe scripts/verify_live.py --generate-only --output .out/public-probes-new
```

测试使用真实回环套接字、临时 profile 和原版 Web 安装图，不连接 GPU 服务。
新增可重复的离线完整流程与实际 Portable 插件安装检查见
[无 GPU 验证指南](docs/offline-testing.md)。浏览器与模拟服务入口均在 scripts/ 中，
支持源码宿主或指定实际 Portable ZIP；输出记录精确包哈希和独立冷启动结果。
将来有可访问服务器后，可选择运行下列真实联调；脚本不安装或部署服务：

```powershell
../../.venv/Scripts/python.exe scripts/verify_live.py --base-url http://<server>:18080/mineru/ --server-identity <镜像摘要或版本> --output .out/live-new
```

使用 `--token-env <环境变量名>`、`--ca-file <证书路径>` 配置测试鉴权，
输出必须是新目录。脚本生成公开 PDF/PNG/DOCX 样本，逐个执行提交、等待、下载、阅读，
保存 receipt.json。服务身份由操作者提供，仍需另行核对实际镜像与 Win7/Portable。

详见 [实现清单](docs/ROADMAP.md)、[架构](docs/architecture.md)、
[自部署适配评估](docs/research/2026-11-10-mineru-self-hosted-plugin-assessment.md)。
