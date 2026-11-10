# dsh-mineru-win7

Win7 DSH 与自部署 MinerU 的独立 Python 插件开发仓库。
目标服务为 Doc2markdonw 部署的 legacy `/tasks` protocol v2 + Office Gateway。

**当前状态：骨架。** 配置、插件装载、服务生命周期、四个工具入口和 Provider
接口已搭建；HTTP、上传、解析、落盘和 Web 页面尚未实现。工具会返回
`NOT_IMPLEMENTED`（未配置地址时为 `NOT_CONFIGURED`），不会发起网络请求。

运行时为 Python 3.8.10，插件无第三方运行依赖；DSH 宿主提供 Plugin API 1。
本仓库未复制第三方插件源码；独立编写实现，调研来源保留在评估文档中。

## 目录

```text
python/mineru_win7/
  plugin.py                 Cordis 入口、配置 Schema、可撤销服务
  config.py                 配置及公开 API 路径
  service.py                业务服务边界
  tools.py                  health/submit/status/result 工具注册
  errors.py                 占位和配置错误
  providers/base.py         协议接口
  providers/legacy_tasks.py  /tasks Provider 占位
docs/
  architecture.md           接入合同和实现约束
  ROADMAP.md                后续实现顺序
  research/                 已复制的调研评估
tests/                      配置合同、真实宿主装载/执行/卸载及包验证
```

## 配置

服务地址示例为 `http://<server>:18080/mineru/`，端口以实际部署为准。
不要使用 `/mineru-ui/`；不要把容器内部地址当作 Win7 可访问地址。
未配置 `baseURL` 时，可使用进程环境变量 `MINERU_BASE_URL`。

安装后，在所选 profile 的 `cordis.patch.yml` 中加入以下配置覆盖：

```yaml
- id: mineru-win7
  config:
    baseURL: http://<server>:18080/mineru/
    protocol: legacy-tasks-v2
    officeMode: pdf_ocr
    requestTimeoutSeconds: 360
```

目前不声明配置热更新；停止 profile 后修改，再重启。
预留的请求期限包含 Office 提交前的转换等待，实际 HTTP 实现仍待完成。

## 安装与打包

先停止目标 profile。从 DSH Win7 宿主仓库执行（仅安装到明确选定的 profile）：

```powershell
.venv\Scripts\python.exe dsh.py plugin --profile web add .\.local_plugin\dsh-mineru-win7
.venv\Scripts\python.exe dsh.py --profile web
```

完整 Portable 使用 `dsh.bat` 替代 `.venv\Scripts\python.exe dsh.py`。
安装复制当前快照，编辑此仓库不会更新已安装的副本。骨架验证请使用临时 profile。

```powershell
.venv\Scripts\python.exe dsh.py plugin --profile web pack .\.local_plugin\dsh-mineru-win7 .\mineru-win7-dev.zip
.venv\Scripts\python.exe dsh.py plugin --profile web remove dsh-mineru-win7
```

当前包可安装不代表可用来解析文件。开发阶段不默认挂载到任何产品预设。

## 开发验证

从本插件目录执行；`DSH_HOST_ROOT` 指向含 dsh/、scripts/ 和开发虚拟环境的宿主源码仓库：

```powershell
$env:DSH_HOST_ROOT = 'D:\Project\deepseek-harness-win7'
& "$env:DSH_HOST_ROOT\.venv\Scripts\python.exe" -m pytest tests -q
```

若保持当前 `.local_plugin/<repo>` 目录布局，可省略该环境变量。
测试使用宿主现有的短 pytest 工作区机制，不访问真实 MinerU、不写用户 profile。
这些测试验证骨架合同与宿主集成，不代表网络、Win7 实机或 Portable 验收。

下一步见 [实现清单](docs/ROADMAP.md)，调研见
[自部署适配评估](docs/research/2026-11-10-mineru-self-hosted-plugin-assessment.md)。
