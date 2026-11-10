# 无 GPU 的可重复验证

这些入口只连接 127.0.0.1 的协议模拟器，不调用模型或实际 OCR。模拟正文会明确注明
“模拟结果，不是 OCR 输出”。既有服务端镜像、Win7 实机及宿主完整发行门禁仍须另行验收。

## 运行前准备

在本插件目录运行。需要宿主源码及开发 Python 3.8.10；浏览器检查还需已有的 Node、
Playwright 模块和 Chromium。测试工具不会安装这些依赖，也不会重建 Portable。
先从宿主目录打包插件，输出必须在插件源码目录之外：

```powershell
.venv/Scripts/python.exe dsh.py plugin --profile web pack .local_plugin/dsh-mineru-win7 .local_plugin/dist/mineru-test.zip
```

在插件目录设置以下绝对路径变量：

```powershell
$hostRoot = 'C:/path/to/deepseek-harness-win7'
$pluginZip = "$hostRoot/.local_plugin/dist/mineru-test.zip"
$testNode = 'C:/path/to/node.exe'
$testChromium = 'C:/path/to/chrome.exe'
$testPlaywright = 'C:/path/to/node_modules/playwright'
$testOutput = Join-Path $env:TEMP ('mineru-check-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
```

## 源码宿主或实际 Portable

```powershell
& "$hostRoot/.venv/Scripts/python.exe" scripts/verify_offline.py `
  --host-root $hostRoot --plugin-archive $pluginZip --output $testOutput `
  --node $testNode --chromium $testChromium --playwright-module $testPlaywright
```

验证 Portable 时，将 `--host-root $hostRoot` 替换为
`--portable 'C:/path/to/actual-portable.zip'`，并使用新的 output。
工具解压该实际 ZIP，所有宿主逻辑使用包内 python.exe、apps/、dsh/ 和依赖。
观察脚本在包外，插件代码只能从隔离 home 中已安装的 ZIP 快照导入。
不会将开发 venv 或源码宿主注入 Portable 子进程。

没有浏览器时可显式使用 `--no-browser`，省略三个浏览器参数；回执不会包含浏览器验收。
output 必须是新的短目录，建议在系统临时目录中。工具清除子进程的模型凭据、
DSH 配置及 Python 搜索路径环境继承，设置独立 DSH_HOME 并禁用遥测。
测试 jobs 控制器使用真实宿主 ToolJobsPlugin 的 quiet 通知，避免后台完成唤醒 LLM。

## 流程和判定

1. Fresh：CLI 安装实际插件 ZIP，canonical Web 启动，创建两个真实会话；
   PDF ZIP、PNG JSON、DOCX ZIP；校验产物字节及哈希、分段阅读和跨 owner 拒绝；
   后台任务完成通知、跨 owner job 拒绝、本地停止、202/409、丢失 POST 确认不重试。
2. Browser：原版 Web 面板连接、会话切换、提交、后台等待、下载、阅读/下一段，
   文档 HTML 保持纯文本、停止等待、失败提示与确认清理；桌面和窄屏截图。
3. Cold：退出进程后，使用同一 home 启动独立新进程；恢复原 owner、复用缓存和阅读，
   清理一个任务而保留其他任务；浏览器读取冷缓存；要求远端 HTTP 请求数为零。
4. Removed：停止后 CLI 卸载插件，重新启动原版 Web；服务、客户端条目和面板消失，
   之前保存且未忘记的产物保留；要求远端 HTTP 请求数为零。

每个步骤都有截止时间，失败保留日志/截图，不覆盖目录。回执记录实际插件和 Portable
ZIP 哈希、运行时位数/模块路径、进程 ID、模拟 HTTP 请求和检查结果。
所有子进程和模拟服务在结束时关闭。只存在一条绿色测试日志不足以证明完整通过：
必须同时检查顶层 receipt.json 的 passed、三个阶段回执，以及启用浏览器时的 browser.json。

输出包含隔离 home 和临时 Web 连接令牌，属于本地私有诊断；不要把整个目录提交或公开。
截图和摘要可单独引用。不要删除其他任务的输出目录。

## 单独启动模拟服务

```powershell
& "$hostRoot/.venv/Scripts/python.exe" scripts/offline_fixture.py --output $testOutput
```

地址写入 ready.json 并显示在终端，端口默认自动选择。将该地址配置到隔离测试 profile 的
MINERU_BASE_URL 后可人工操作。文件名 `slow*` 永久 processing，`failed*` 返回失败，
`disconnect*` 丢弃提交确认，其余任务短暂 processing 后成功。模拟器不识别文件内容。
在 output 下创建名为 stop 的文件即可退出，并保存 requests.json。
