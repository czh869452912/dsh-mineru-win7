# 插件发布门槛

候选版本为 0.1.0-rc.1。稳定发布前必须收齐同一份插件 ZIP 的证据。
本机没有 MinerU GPU 服务或 Win7 实机；不能把 offline-qualified 写成 stable-ready。
这份插件门槛不替代宿主 scripts/verify_release.py 的完整 Portable 发行门禁。

1. 停止改动候选文件，执行 scripts/build_client.py；从宿主调用 plugin pack，ZIP 输出在源码目录外。
2. 运行 `python scripts/verify_regression.py --archive <ZIP> --output <新目录>`。
   它核对全部发行文件与源码一致，冻结测试文件，执行整个插件 tests 集合，保存命令、日志、XML 和包哈希。
3. 按 offline-testing.md 分别给 verify_offline.py 提供实际 x86/x64 Portable ZIP，启用浏览器。
   必须完成 fresh/cold/removed，两个回执引用同一插件 SHA；禁用浏览器的结果不能用于该门槛。
4. 远端有真实 legacy Tasks + Office Gateway 后，在与候选 Python 源码一致的 checkout 执行
   `python scripts/verify_live.py --plugin-archive <ZIP> --base-url <公开地址> --server-identity <镜像身份> --output <新目录>`。
   PDF/图片/DOCX 分别测试 ZIP 和 JSON，共六次；校验实际识别文字，保存质量结果。
   服务器身份仍需操作者核对镜像摘要。生成样本是英文简单探针，不代替中文、表格与版式的人工质量抽检。
5. 在 Win7 SP1 运行第 3 步，保存实际 Windows 6.1.7601 运行时与浏览器证据。门槛拒绝未安装 SP1 的 7600；需要 Win7 可运行的 Node/Playwright；
   现有观察器在同机访问回环地址，尚未实现跨机器浏览器测试。不能伪填本机版本。
6. 汇总检查：

```powershell
python scripts/check_release.py --archive <ZIP> --junit <回归目录>/pytest.xml `
  --x86 <x86目录>/receipt.json --x64 <x64目录>/receipt.json --output <新目录>
```

有实际证据后增加 `--live <真实回执> --win7 <Win7回执> --require-stable`。
缺少外部证据或版本仍有 rc/dev 后缀时，离线检查可以成功，但 stable_ready 为 false；
`--require-stable` 返回 2。无效/不匹配/缺失浏览器回执直接失败，不转成“尚待验收”的通过。
选定正式版本号后需重新打包，对新 ZIP 重新绑定所有必要证据，不能复用旧 ZIP 的哈希。

上传前人工确认许可证、协议对应镜像、已知限制和变更说明。当前没有配置自动发布或上传密钥，
工具不会创建 GitHub Release，也不会把含 Web 令牌、原始 home 或凭据的诊断目录上传。
