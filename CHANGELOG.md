# 更新日志

## v0.1.0 (2026-11-06)

第一个可分发版本。

### 新增

- **图形界面**：Tkinter 单窗口，中文界面，支持高 DPI（200% 缩放下不发虚）。
- **本地引擎**：`holmes_desk/engine.py` 自行实现的并发探测，只依赖 `requests`；
  不联网拉取站点表，不调用任何云端接口。
- **481 个站点**：内置 `data/data.json`，字段与上游一致（含 NSFW 标记、正则校验、
  POST 型站点、`urlProbe` 探测地址）。
- **站点预设**：常用 / 开发 / 安全 / 社交 / 游戏 / 影音 六组，可手动改站点名。
- **多用户名**：空格或逗号分隔，`{?}` 自动展开成 `_` `-` `.` 三种变体。
- **导出五种格式**：TXT、CSV、XLSX、HTML（单文件报告，可直接发给别人）、JSONL。
- **一键桌面图标**：`holmes-desk --install-shortcut`，同时在桌面和开始菜单创建，
  图标内嵌在 exe 里（不依赖 .lnk 的图标覆盖，避免显示成白纸）。
- **设置持久化**：窗口位置、上次输入、导出格式等存在 `%APPDATA%\HolmesDesk\config.json`。
- **命令行检索**：`holmes-desk --search 用户名 --sites GitHub,Reddit`，便于脚本调用。
- **打包脚本**：`build/build.ps1` 用 PyInstaller 生成免安装的 `HolmesDesk.exe`。

### 已知限制

- 只支持 Windows（快捷方式与图标相关逻辑是 Windows 专用；核心引擎本身跨平台）。
- 未做站点库编辑器（v0.2 计划）。
- 单个站点超时或返回异常时记为「未知」，不计入命中。
