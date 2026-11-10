# Win7 DSH 与自部署 MinerU 插件评估

日期：2026-11-10。范围：源码与协议调研，未实现插件、连接用户服务器或取得 Win7 实机验收。
用户后续明确：使用 `C:/Users/fai_l/Documents/Doc2markdonw` 仓库部署、接口以 `/tasks` 组织。对该仓库源码与缓存核验后，首期目标修正为 MinerU 3.x protocol v2 + Office Gateway；不按先前“最新版”假设采用 4.1 Tasks。远端运行镜像尚未直接探测。

## 结论

原版 DSH 社区已有满足“自部署 MinerU”方向的插件；本次未在官方 DSH 固定版本的 packages/docs 搜索及当前官方完整文件树中发现 MinerU 专用内置包。文件树无命中只能支持本次检索结论，不能证明所有历史版本或第三方市场都没有。

推荐在 Win7 版中开发独立、可选安装的 Python 3.8 Host 插件。采用与 HuanLinOTO 客户端相同的 legacy `/tasks` 工作流，参考 Yurzi 的 Provider/读取分层，并适配用户的 Office Gateway。Win7 端负责文件上传、任务状态和结果落盘，服务器负责解析和模型推理。无需在 Win7 安装 MinerU、LibreOffice、Torch、CUDA 或新版 Node。

这属于插件功能移植和协议适配，不能把原 npm 包直接安装等同于完成适配。

## 已核实的社区实现

| 实现 | 自部署能力与源码证据 | 对 Win7 的意义 |
| --- | --- | --- |
| `@huanlin/dsh-plugin-mineru` 0.4.2 | 可配置 baseURL；源码标注 MinerU 3.4.4 protocol v2，调用 `/health`、`/tasks` 与任务结果接口；提供五个模型工具 | 简洁的旧协议参考；不是最新 4.1 客户端。Host 使用 Node fetch/FormData，前端配置依赖较新 DSH。package.json 声明 AGPL-3.0，直接移植源码时需按所选版本处理许可证 |
| `Yurzi/dsh-pdf-mineru` 0.2.3 | 显式区分官方云、自部署 legacy-v2 和 V1；含缓存、分段读取和后台解析。V1 源码实际调用 `/v1/uploads`、`/v1/parse/jobs` | 更适合作为设计参考；现有 V1 实现针对 4.0，不能据 README 的“4.x”推定兼容 4.1。包要求 Node >=24.9.0、DSH >=0.2.2-rc.1，包含 PDF.js/canvas 本地渲染依赖；MIT |
| `Lee-Hilex/dsh-mineru` | 主要封装 MinerU 公网 Precision/Agent API，README 明确无完全离线模式 | 不是自部署场景的首选 |
| `Mu-scorpio/dsh-mineru` | `engine.js` 固定 `https://mineru.net/api/v4`，按公网上传链接/批次结果流程工作 | 不是可直接连接官方自部署 Tasks API 的实现 |

一手来源（源码固定到本次观察的提交）：

- HuanLinOTO：[HTTP 客户端](https://github.com/HuanLinOTO/dsh-plugin-mineru/blob/374edb93b9543a4040aed88f122ddf1ecbd6812e/src/client.ts)、[包描述及许可证声明](https://github.com/HuanLinOTO/dsh-plugin-mineru/blob/374edb93b9543a4040aed88f122ddf1ecbd6812e/package.json)。
- Yurzi：[V1 Provider](https://github.com/Yurzi/dsh-pdf-mineru/blob/ee3e3d7c00fc6bf54a0bc2f3ad9dad2edeacfcdb/src/providers/self-hosted-v1/index.ts)、[包描述](https://github.com/Yurzi/dsh-pdf-mineru/blob/ee3e3d7c00fc6bf54a0bc2f3ad9dad2edeacfcdb/package.json)、[配置说明](https://github.com/Yurzi/dsh-pdf-mineru/blob/ee3e3d7c00fc6bf54a0bc2f3ad9dad2edeacfcdb/docs/configuration.md)。
- Lee-Hilex：[客户端](https://github.com/Lee-Hilex/dsh-mineru/blob/ea07ae3e75d0eaeb5e1655bf26f0057b676823bb/lib/mineru-client.js)。
- Mu-scorpio：[Host](https://github.com/Mu-scorpio/dsh-mineru/blob/1fffb1551d7f82ded95271ab72aa4707ee7c2705/engine.js)。
- 官方 DSH 当前文件树观察：`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`，GitHub tree API 返回 `truncated=false`；路径中无 mineru，另对本地固定提交 packages/docs 执行了内容搜索。

## 用户现有部署的核验与适配结论

部署仓库位于 `C:/Users/fai_l/Documents/Doc2markdonw`，当前提交 `d6c4810`，检查时工作树干净。本次只读该仓库，未修改配置或启动服务。

- `dist/_cache/MinerU-master` 的 HEAD 为 `53fde6d2988603bcf7b4af3cc23dc7d758291580`；`mineru/version.py` 是 **3.4.2**，`mineru/cli/api_protocol.py` 明确 `API_PROTOCOL_VERSION = 2`。部署 README 也声明按 MinerU 3.4.2 验证。构建脚本默认引用 `master`、镜像标签为 `mineru:latest`，所以名称不能证明实际运行的是当前最新版；缓存源码也不单独证明远端镜像的精确字节身份。
- 公开链路是 `Win7 DSH → Nginx /mineru/ → mineru-office-gateway:8081 → mineru-router:8002 → workers`。示例 `PUBLIC_PORT=18080`，故默认示意基址为 `http://<server>:18080/mineru/`；真实地址以用户部署为准。不要使用 `/mineru-ui/` 作为 API，也不要默认绕过 Office Gateway 直连 8002。
- 提交为 `POST <base>/tasks`，multipart 文件字段名 `files`；状态为 `GET <base>/tasks/{id}`；结果为 `GET <base>/tasks/{id}/result`。缓存 Router 明确结果未完成返回 202、任务失败返回 409，成功时代理 JSON 或 ZIP。状态终态为 `completed/failed`，在途为 `pending/processing`。
- Office Gateway 接受 DOC/DOCX/PPT/PPTX/XLS/XLSX；默认 `office_mode=pdf_ocr` 在服务器端经 LibreOffice 转 PDF，并覆盖 backend/parse_method 为网关配置（默认 pipeline/ocr）。OOXML 可选 native；旧 DOC/PPT/XLS 不接受 native。Office 与 PDF/图片混合请求被拒绝，插件应分组或首期单文件提交。
- 网关健康响应是 `{gateway, libreoffice, mineru}`，不同于原生 MinerU 的 version/protocol/队列响应。健康工具需要独立解析；不能要求公开 `/health` 提供原生字段。网关不直接提供自己的 OpenAPI，而通配 GET 可能代理到 Router，因此即使获取到 schema，也不能据此假定包含 Office 扩展规则。
- Router 根据内部请求生成 status_url/result_url，外层网关当前不重写这些响应内容。插件应从配置的公开 base 和 URL 编码后的 task_id 构造状态/结果路径，保留 `/mineru/` 前缀，避免请求容器内部主机或丢失路径前缀。
- Office 渲染在返回 task_id 之前进行，因此“异步提交”的请求阶段也可能持续较久。上传/预处理期限与轮询期限应分开，不能直接套用一分钟总超时。现有网关默认单文件 100 MiB、每请求 10 文件、单次转换 300 秒；插件需允许配置并尊重网关上限。
- 缓存 Router 没有公开任务取消路由；网关虽通配代理 DELETE，并不意味着上游支持删除/取消。首期提供四个远端工具（health/submit/status/result）即可；停止本地轮询不能报告远端已取消。
- 网关的 send_upstream 未透传客户端 Authorization，现有 Nginx 示例也未配置鉴权。以后接入鉴权时，应区分公开网关认证与 Router 上游认证；仅在插件添加 Bearer 头不能自动改变该部署的转发行为。

本地证据：部署仓库的 `deploy/ragflow-mineru/README.md`、`gateway/nginx.conf.template`、`docker-compose.mineru.yml`、`docker-compose.office-gateway.yml`，以及 `services/mineru-office-gateway/app/main.py`、`multipart.py`、`upstream.py`、`tests/test_main.py`。缓存 MinerU 的 `mineru/cli/router.py` 包含实际请求/响应状态与路由。

因此，HuanLinOTO 是当前服务端协议最贴近的轻量参考，Yurzi legacy Provider 是更丰富的阅读与缓存设计参考。前者源码标注 3.4.4，而用户缓存是 3.4.2，仍应以真实样本核验字段差异；两者都需要 Python Host 重写及本段列出的网关适配。

## MinerU 版本差异（未来升级参考）

截至本次查询，发布页列出的最新版本是 4.1.7；“V1 API”不是跨 4.0/4.1 不变的协议保证。

| 服务合同 | 适配决策 |
| --- | --- |
| 较早的 `/file_parse` 服务 | 只有实际部署提供该接口时再做独立适配；不作为最新版默认入口 |
| 3.x legacy `/tasks` | 当前首期目标；参考 HuanLinOTO 或 Yurzi legacy Provider，并适配 Office Gateway |
| 4.0 `/v1/uploads` + `/v1/parse/jobs` | Yurzi 当前 V1 Provider 的请求形态；若服务器确实为 4.0，可单独适配 |
| 4.1 `/v1/tasks` | 未来升级后另加，不作为当前部署首期目标 |

4.1 官方迁移说明明确删除旧 Upload/Parse Job 路由，不保留别名。主 API Server/Router 不提供 `/v1/file_parse`；该接口属于独立 file-parse-server。不能把解析服务地址与远程 VLM 推理服务的 OpenAI 兼容地址混用。

来源：[MinerU 发布页](https://github.com/opendatalab/MinerU/releases)、[4.1 迁移说明](https://github.com/opendatalab/MinerU/blob/711a169320ceac04cf6da692c066764f55997656/docs/zh/reference/migration_4_1.md)、[Tasks 合同](https://github.com/opendatalab/MinerU/blob/711a169320ceac04cf6da692c066764f55997656/docs/zh/usage/tasks.md)。后两项是本次观察的 master 提交，不替代用户部署的 OpenAPI。

## Win7 版可复用的接入点

- `dsh/plugin_api.py`、`examples/python-echo/`：已有 Python Plugin API 1、工具定义和独立安装包范式。
- `dsh/core/tools.py`：工具注册、输出 Schema、执行与撤销机制。插件需要通过 ctx 服务和 disposer/effect 接入，文件读写沿用宿主权限边界。
- `dsh/credentials/credentials.py`：密钥引用及解析；配置保存引用，调用时获取凭据。
- `dsh/jobs/local.py`、`dsh/jobs/tool_jobs.py`：当前 scoped LocalJobRegistry 和模型后台任务控制。需按真实 Agent owner 接入并验证消费者，不能拿历史 `jobs_service.py` 代替当前合同，也不能假定已具备新版 Node JobRegistry 的全部 ABI。
- `examples/python-web-echo/`：Python Host + 原版 ClientModules + Connection/Typert Remote 的交付范式。设置界面可后续新增插件 Client，不修改 `apps/web/dist` 核心前端。
- `dsh/mcp/config.py`：已有 stdio/streamable-http。若以后选用运行在服务器侧的 MinerU MCP 桥，可复用；普通 Tasks HTTP API 本身不是 MCP，不能直接把其 URL 配到 MCP 客户端。

当前 `migration/baseline.json` 和父仓库 gitlink 固定官方 `a4c74a91`（0.1.5-rc.3）。本地 reference 工作树已经指向 `cd5ef814`，属于本次开始前的既有差异，本次不更改它。开发时应以生产固定合同核验，不能误用 reference 当前较新源码推断宿主能力。

## 推荐实现范围

建议包名另设为 `dsh-mineru-win7`，避免与已有 npm 包的身份混淆。初期可按以下职责拆分：

```text
Plugin：ctx 服务、工具定义、配置和生命周期
  ├─ MinerU 服务：提交/查询/结果/取消、本地任务记录
  ├─ LegacyTasksProvider：protocol v2、Office Gateway、上传与下载
  └─ 结果存储/Reader：Markdown、JSON、图片与有界读取
```

首期模型工具建议为 `mineru_health`、`mineru_submit`、`mineru_status`、`mineru_result`；当前不提供远端 cancel。先完成单文件 PDF、扫描 PDF、图片以及经现有 Office Gateway 的 Office 输入，逐类用实际样本验收。

当前流程为：本地文件快照 → multipart POST `/tasks`（含 return_md 等选项）→ 保存 task_id → 从公开基址构造路径并间隔轮询 → GET 结果 → 按 Content-Type 解析 JSON 或有界解压 ZIP → 发布本地产物。JSON 中结果以实际提交/转换后的文件名组织，不能假定 Office 原扩展名始终保留；保留本地源文件到产物的映射。返回摘要、结果路径和读取入口；长 Markdown 分段读取，不全量塞进模型上下文。

技术上可使用 Python 标准库 HTTP/SSL 与 zipfile，或复用发行版已有的 requests；不引入 MinerU SDK。必须做有限超时和上传/下载分块，避免 x86 内存峰值。若使用阻塞 HTTP，应放入 Python 3.8 的 executor，并明确线程退出与请求取消边界；取消本地等待不能误报为服务端任务已取消。后台通知接入现有 jobs，远端 ID 可由插件持久化，但服务重启后任务是否仍有效须按服务端合同处理。

配置建议包含服务基址、明确协议 `legacy-tasks-v2`、健康格式 `office-gateway`、凭据引用、私有 CA、backend/parse_method/语言、office_mode、请求和总期限、并发/文件/产物/输出预算、存储目录。不静默回退公网服务。带凭据的重定向与跨来源上传/下载要分别校验，下载链接不沿用任意 Authorization；ZIP 拒绝越界路径、链接和资源膨胀。上传创建结果未知时不盲目重提，避免重复解析。

## 工作量与验证边界

以下为相对工作量评估，不是已经实现的功能或工期承诺：

| 阶段 | 范围 | 复杂度 |
| --- | --- | --- |
| A | legacy Tasks + Office Gateway、四个工具、结果落盘、错误/停止等待/限制、CLI 可用 | 中；比完整移植更可控 |
| B | 持久化任务映射、后台通知、缓存及分段读取 | 中至高 |
| C | Web 配置/连接测试/进度与结果入口、离线插件包 | 中；受固定浏览器合同影响 |
| D | 原页渲染核对、多协议、复杂证据索引、完整上游功能等价 | 高；单独排期 |

建议先完成 A，再按使用反馈推进 B/C。若需要原页渲染，优先服务器侧生成预览或另行选择经 Win7 验证的渲染器；不直接带入 Node canvas/PDF.js 原生依赖。若另有现代机器承载完整原版 DSH，也可经服务器侧 MCP 桥间接调用，但这增加部署组件，不能称作本地原插件移植。

实施后的定向验证应覆盖：真实 legacy Tasks 响应与网关健康；PDF/扫描件/图片、Office 两种模式及混合批次拒绝、中文空格路径；私有 CA/认证和代理前缀、内部 URL 不被跟随；提交前转换长等待、结果 202/409/404、停止等待；任务所属会话隔离与卸载清理；大文件有界内存和安全落盘；原版 Web 及目标 Chromium 的实际调用；x86/x64 Portable 离线安装及冷启动。到插件稳定候选/发行里程碑再按仓库规则执行完整资格，不为调研运行完整 pytest 或重建 Portable。

尚待确认：实际服务器地址、运行镜像的精确版本/摘要、服务响应样本、对默认认证/反向代理配置是否有修改，以及首期是否要求 Web 操作页。仓库已足以确定首期协议方向，实现验收仍必须绑定真实服务。

## 本次核验

- GitHub Releases API 确认 MinerU 最新发布为 `mineru-4.1.7-released`（2026-11-04），Yurzi 最新发布为 `v0.2.3`（2026-11-05）。
- 文档 UTF-8、9 个本地代码/示例引用存在性及 `git diff --check` 通过；文档新增文件未暂存。本次仅调研和文档，不运行 pytest。
- 按迁移记录入口执行 `scripts/migration.py check` 和 `ready`；两者均退出 1，报告 `missing file: reference/apps/desktop-host/package.json`。这不是插件运行失败，也不是迁移门禁通过；既有 reference 差异保持原样，未修改台账状态。
- 用户补充部署仓库后，追加只读检查了 Compose/Nginx/网关/缓存 MinerU 路由和版本；未构建或运行 Docker、未请求远端服务、未改变 Doc2markdonw 工作树。本轮只更新评估文档，执行文档差分、UTF-8 和证据路径存在性检查。
