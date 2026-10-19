# 截图工具栏毛玻璃更新

后续修复：高 DPI 下的选区像素错位已修正，见 [CAPTURE_STABILITY_FIX.md](CAPTURE_STABILITY_FIX.md)。

2026-10-19，延续主工作台的蓝黑星空和冰蓝强调色，调整框选截图的上下工具栏、选区与原位标注控件。

- 上方拍照/长截图/视频栏和下方标注/复制栏，按实际位置采样已经冻结的截图，使用共享的低分辨率模糊缓存，叠加冷色半透明材质与轻微高光。不增加屏幕采集。
- 去掉原工具栏的 `QGraphicsDropShadowEffect`，在覆盖层只绘制一层较轻的阴影，避免截图中的厚重黑色叠层。
- 绿色按钮改为冰蓝；选区边线由 3px 调为 1.5px，角标、控制点、尺寸提示和文字输入框同步调整。可拖动范围和键盘操作保持原样。
- 导出的截图仍由原图与用户标注生成，工具栏、选区线和模糊材质不参与导出。红/橙/蓝/绿标注色与已有工具偏好保持不变。
- 保留 `selection_overlay.PANEL_STYLE` 导出，兼容长截图编辑器现有工具栏引用。

## 验证

全部使用生成的示例底图，没有截取真实桌面，没有读取真实资料。

- 原有的选区移动/缩放/原像素确认和拍照/视频模式测试共两项通过。
- 实际原生覆盖层验证了矩形、撤销/重做、文字确认、马赛克、保存/复制图像信号、拍照/长截图/视频路由、Esc，以及 800/1024/1280 逻辑像素宽度。
- Qt 缩放参数 1 与 1.25 均通过。不是实际切换 Windows DPI 或物理显示器的验收。
- 核对未标注时导出与原图裁剪相同，标注后导出包含标注，源图始终不变；两个工具栏共用缓存，没有嵌套阴影效果。

截图和报告：`D:\MyGithub\DocumentAssistant-local\verification\capture-glass-20261019`，含 `capture-photo.png`、`capture-annotations.png`、`capture-result.json` 和 `scale-1.25` 子目录。

本轮验证到保存/复制信号和图像内容，未重新验证全局热键分发、系统剪贴板写入、连续滚动拼接或实际视频录制。未改动这些处理逻辑，也没有重新构建安装包。

代码备份：`D:\MyGithub\DocumentAssistant-local\backups\capture-glass-20261019-110207`。

从托盘选择“退出”，再运行 `D:\MyGithub\DocumentAssistant\Start-DocumentAssistant.cmd`，按原截图快捷键（默认 Alt+S）查看新界面。
