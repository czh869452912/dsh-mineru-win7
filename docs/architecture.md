# 服务合同与实现

```text
模型工具 / 原版 Web shell.overlay
                ↓ 工具策略 / Agent session
ctx.mineruWin7 → 会话 ctx.fs → 有界磁盘快照
       ↓ owner + endpoint          ↓
   SQLite TaskStore ← LegacyTasksProvider → 公开 /mineru/tasks
       ↓                                     ↓
受控产物目录、SHA-256                  Office Gateway → Router
```

入口只注入 tools。agents、fs、jobs、credentials 等按操作动态查找，不硬编码导入
其他业务插件。Web 通过 ClientModules / Connection / Typert Remote 提供 mineruPanel，
run 调用同一 ToolsService，含宿主工具策略及 Agent lookup。原版前端不修改。
工具注册、Remote、服务和面板均归所属 Fiber 管理；卸载关闭网络、终止本地等待并关闭数据库，
持久化记录和用户产物保留。

## 固定协议

- POST `<base>/tasks`：multipart 单文件字段 files，响应 202/task_id。
- GET `<base>/tasks/{id}`：pending/processing/completed/failed，404 单独返回。
- GET `<base>/tasks/{id}/result`：200 JSON/ZIP；202 未就绪、409 失败、404 缺失。
- GET `<base>/health`：Office gateway/libreoffice/mineru 或 native version/protocol_version。
- 所有路径由配置公开地址重建，不信任 status_url/result_url 或 JSON 图片 URL。
- Office 默认 pdf_ocr，转换在提交确认前进行；提交未知不能自动重试。
- 没有经核实的取消端点。job_kill 和卸载只停止客户端请求/轮询。

协议调研来源为 Doc2markdonw d6c4810 与 MinerU 53fde6d2，见 research 记录。
这不是实际部署镜像身份或服务互通的证明。新增协议应增加 Provider，不悄悄更改此合同。

## 权限与存储

owner 基于已注册的真实 Agent 身份及其 session；执行上下文 session 必须匹配。
上传通过发起 Agent 的 ctx.fs resolve/stat/readByteRange 读取，不直接打开模型路径。
前后版本/大小校验避免上传读取过程中变化的文件。授权读取后才发送 POST。
快照存于临时磁盘，64 KiB 分块上传；不将整个文件驻留 x86 内存。

SQLite 记录与产物均在包外。数据库和结果查询同时校验 owner、公开 endpoint 与 credentialRef；
凭据实际值不持久化。提交前记录本地 UUID，响应丢失或重启后的草稿表示 submission-unknown。
下载先写临时 staging，通过字节/文件/路径预算后原子发布目录，再发布清单。
中途残留目录不会被静默覆盖或自动删除。

ZIP 检查中央目录数量、路径、设备名、ADS、大小写碰撞、链接、压缩比及实际输出预算；
拒绝 ZIP64、加密和多卷。JSON 大小另限，保存原始 JSON、Markdown 与内联 base64 图片，
保留远端名称映射，名称不直接决定磁盘路径。所有产物都有 SHA-256 与长度清单。
读取/缓存复用先校验，forget 只删除清单内且未变更的文件，未知文件阻止清理。
任务及文件清单分页，文本按字符窗口读取，避免全量注入模型上下文。

## 网络与生命周期

标准库 asyncio HTTP/1.1；最多四个同时在途请求，支持 Content-Length、chunked 和 EOF。
连接/读取/总期限与 AbortSignal/调用取消均有界。TLS 使用系统信任或私有 CA；
每次请求解析凭据引用，不跟随重定向、不使用代理、不自动重试、不接受压缩响应。
头/trailers 各 16 KiB，JSON、上传、下载及落盘各有独立预算。

前台等待按终止状态轮询，可自动下载；后台复用宿主 jobs 的 owner/通知/停止机制。
Web 仅显示有权访问会话的工具结果，正文以转义纯文本显示；不加载远端 HTML。
连接参数由宿主插件配置管理，面板显示有效值，修改后重启。
