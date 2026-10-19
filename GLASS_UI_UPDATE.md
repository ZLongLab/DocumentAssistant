# 星空毛玻璃界面

截图上下工具栏与选区样式现已同步更新，详见 [CAPTURE_GLASS_UPDATE.md](CAPTURE_GLASS_UPDATE.md)。

2026-10-19，按最新反馈替换之前的深紫星空。功能流程与数据库结构沿用现有版本。

- 主色为蓝黑夜空 `#070e19`、雾蓝面板和冰蓝强调色 `#8acdf5`；蓝青星云与星点由 QPainter 绘制，不下载素材，不更换应用图标。
- 侧栏、列表、流程栏、操作栏、导入卡片和详情面板使用同一背景磨砂材质。先缓存清晰星空，再下采样与平滑放大生成模糊图，按面板实际位置取样，叠加半透明冷色与轻微高光。文字、图标和控件不参与模糊。
- 大部分面板、按钮和表格去掉可见描边及行分隔线。保留键盘焦点、选中卡片和选中行提示，保证可操作性。
- 文档库背景静止；导入页少量星点微动，窗口隐藏即停。尺寸不变时复用背景与模糊缓存，窗口缩放时重新生成。
- 原来的海蓝晶石、暖玫瑰金主题继续保留。主题菜单现在显示“星空毛玻璃”，修复切回星空时状态栏显示成海蓝的文案。

这是应用内星空背景的真实空间模糊，不采集桌面，不是 Windows Acrylic/Mica，也不会模糊文件文字。依赖没有增加，仍使用 PySide6/QSS/QPainter。

## 查看与启动

正常运行：双击 `D:\MyGithub\DocumentAssistant\Start-DocumentAssistant.cmd`。

已经运行的旧进程需从托盘“退出”再重开，才会读取新界面。关闭主窗口通常只是隐藏到托盘。没有强制结束用户现有窗口。

临时交互预览：

```powershell
& 'D:\MyGithub\DocumentAssistant\.venv\Scripts\python.exe' 'D:\MyGithub\DocumentAssistant-local\verification\glass-ui-20261019\preview.py'
```

此预览只使用独立的六份示例文件。验证与截图目录：`D:\MyGithub\DocumentAssistant-local\verification\glass-ui-20261019`。

## 验证

原生窗口启动、文档库搜索/多选/失效状态、导入卡片/详情、三主题和窄窗口，以及背景模糊、取样对齐、缓存复用与隐藏停表检查已通过。导入卡片检查使用 Qt 缩放参数 1 和 1.25；此参数会与系统 DPI 叠加，不表示实际修改过 Windows 显示设置。

报告包括 `library-result-1.json`、`material-result.json` 和 `cards` 子目录；实际截图为 `library-after.png` 与 `import-after.png`。检查了六份示例文档，原文件哈希保持不变。打开按钮验证到本地文件 URL，未启动外部阅读器做视觉验收。

十份独立示例的完整流程回归也已通过：拖入/扫描、手动修改分类、取消与确认复制归档、同名编号、搜索打开 URL、失效状态和重启。报告位于 `workflow/gui-result.json`。

备份：`D:\MyGithub\DocumentAssistant-local\backups\glass-ui-20261019-095932`。没有处理真实资料。安装包未重新构建，物理多显示器/DPI 切换、外部阅读器显示与长期性能未验证。
