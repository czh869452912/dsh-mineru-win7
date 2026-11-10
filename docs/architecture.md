# 骨架与服务合同

```text
DSH tools → ctx.mineruWin7 → LegacyTasksProvider
                              ↓（待实现）
http://<server>:<port>/mineru/ → Office Gateway → MinerU Router → workers
```

插件通过 `ctx.set_service` 提供 mineruWin7；模型工具动态获取该服务。
注册与 close 归所属 Cordis Fiber 管理。只依赖 tools，不硬编码导入其他业务插件。

## 当前部署合同

- POST `<base>/tasks`：multipart，文件字段 `files`，返回 202/task_id。
- GET `<base>/tasks/{id}`：pending/processing/completed/failed。
- GET `<base>/tasks/{id}/result`：成功 JSON 或 ZIP；未就绪 202；失败 409。
- GET `<base>/health`：Office Gateway 的 gateway/libreoffice/mineru 字段。
- 不跟随服务返回的内部 status_url/result_url，保留公开 base 的代理前缀。
- 没有经核实的远端取消接口；不得把本地停止轮询叫作远端取消。
- Office 默认在返回 task_id 前完成 LibreOffice 转 PDF，提交阶段需独立期限。
- Office 和 PDF/图片不得混在同一请求；首期单文件提交。
- Office 的默认 pdf_ocr 会由网关覆盖为其 backend/parse_method 配置。

调研依据是 Doc2markdonw `d6c4810` 及缓存 MinerU `53fde6d2`（3.4.2/protocol 2）。
这不是远端运行镜像摘要的证明；正式实现前需绑定实际服务响应。

## 边界

当前 Provider 统一抛出 PendingImplementation，四个工具返回结构化失败。
没有 HTTP 客户端、文件访问、轮询任务、缓存或落盘。输出 Schema 也只是骨架错误合同。
后续实现应在 Provider 完成协议传输，在服务层处理权限/owner/预算/产物，工具只作适配。

上传必须先经过宿主 fs/权限策略；本地任务 ID 和远端 ID 需按 Agent/session 隔离。
只保存凭据引用，使用 ctx.credentials 获取密钥。当前尚未提供凭据配置字段。
下载与 ZIP 解压需限制总字节、文件数、路径和链接，流式处理以控制 x86 内存。
数据放在包外的受控目录；卸载清理运行资源，用户产物的保留策略需明确。

后续 Web 配置和结果入口用现有 ClientModules / Connection / Typert Remote，
不修改原版 apps/web/dist。4.1 协议若将来需要，新增 Provider，不更改 legacy 合同。
