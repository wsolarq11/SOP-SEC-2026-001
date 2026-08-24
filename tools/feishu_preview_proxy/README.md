# 飞书在线预览本机代理

本工具用于解决一种特定的网络问题：飞书 Wiki 里的 `.docx` 在线预览会请求 `internal-api-drive-stream.feishu.cn`、`internal-api-lark-api.feishu.cn`、`weboffice.feishu-3rd-party-services.com` 等内部域名，而当前机器直连这些域名不通。

它只在本地监听，只代理配置表中列出的域名，并把请求转发到当前网络可连通的官方替代域名，同时保留原始 `Host`，让飞书预览 iframe 继续按原域名工作。

> 安全边界：这是 HTTPS 中间人代理，会生成并使用本机 CA。只有在你明确接受“本机可解密这 3 个域名的 HTTPS 流量”时才安装。不要用本工具绕过任何网站的服务端权限、登录、风控或法律限制。

## 前置条件

- Windows
- Python 3
- Microsoft Edge 或 Google Chrome
- `openssl` 已加入 `PATH`（用于首次生成本机 CA 和叶子证书）

## 安装到本机

在仓库内执行：

```powershell
cd tools\feishu_preview_proxy
powershell -ExecutionPolicy Bypass -File .\install.ps1 -ConfigureSystem -Startup
```

参数说明：

- `-ConfigureSystem`：把本机 CA 安装到当前用户根证书库，并把系统 PAC 指向 `http://127.0.0.1:18081/feishu_proxy.pac`。
- `-Startup`：在 Windows 启动目录写入自启入口。
- `-Edge`：安装后直接用专用 Edge 配置打开文档。
- `-Url`：配合 `-Edge` 指定飞书 Wiki 地址。

安装目录默认为：

```text
%LOCALAPPDATA%\FeishuLocalPreview
```

普通 Edge 需要完全退出后重新打开一次，才能读取新的 PAC 和证书。

## 日常使用

只启动代理和 PAC：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -NoEdge
```

启动代理并用专用 Edge 打开文档：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Edge -Url "https://xcn87k1zyro7.feishu.cn/wiki/<node>"
```

停止代理：

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

停止并恢复系统代理：

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1 -RestoreSystem
```

## 配置

首次安装会从 `config.example.json` 生成本机 `config.json`，不会入库。默认配置：

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 18080,
  "pac_port": 18081,
  "upstream_port": 443,
  "max_workers": 64,
  "connect_timeout": 20,
  "read_timeout": 30,
  "routes": {
    "internal-api-drive-stream.feishu.cn": "drive-stream.feishu.cn",
    "internal-api-lark-api.feishu.cn": "api-lark-api.feishu.cn",
    "weboffice.feishu-3rd-party-services.com": "weboffice.feishuapp.cn"
  }
}
```

`routes` 的键是浏览器请求的原始内部域名，值是对外连接的实际上游域名。修改配置后重新执行：

```powershell
python .\feishu_mitm_proxy.py --setup --base .\run --config .\config.json
```

`--setup` 会重新生成 PAC，并在缺少证书时生成 CA/叶子证书。证书、私钥、日志、浏览器 profile 都只写在 `run/` 下，已被 `.gitignore` 排除，不会提交进仓库。

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveInstallDir
```

卸载会：

- 停止本机代理和 PAC
- 删除开机自启入口
- 恢复系统代理
- 删除本机 CA（兼容旧版 `Local Feishu Stream Proxy CA`）
- 删除 Edge/Chrome 节流策略值
- 删除安装目录（可选）

## 局限

- 这是临时网络绕行方案，不是飞书官方支持或生产级网关。
- 上游域名映射可能需要随飞书调整。
- 代理当前采用每连接一线程池、HTTP/1.1、流式转发响应体；大量并发或超大文档仍可能产生明显开销。
- 本机 CA 被信任期间，代理进程可以解密配置域名下的 HTTPS 流量，日志不会记录 Cookie/Authorization，但风险边界仍然存在。
- 它不能绕过登录、权限、租户隔离、风控、IP 地域限制等服务端控制。
