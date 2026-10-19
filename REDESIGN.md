最新视觉更新：按用户最新反馈，采用蓝黑星空与应用内毛玻璃，详见 [GLASS_UI_UPDATE.md](GLASS_UI_UPDATE.md)。以下为之前的设计记录。

# 原生星空工作台

2026-10-18 更新：采用最新 `design-balanced-enhanced.html` 的深紫星空方向。`design-taste-minimal.html` 和旧蓝灰草稿保留为历史材料，不作为本轮视觉验收基准。

主视觉为深紫背景、150 个轻微闪烁星点、低对比流星、紫蓝渐变按钮、半透明侧栏和深色卡片。均为原生 Qt 绘制；窗口隐藏时动画停止，不引入 WebEngine 或外部图片依赖。

200 逻辑像素侧栏保留添加/整理、文档库、截图、主题、更多操作及设置。主区保留三步流程、文档库位置、文件导入、1–4 列卡片和底部确认归档操作。详情默认收起，通过“文件详情”展开。文件卡片显示真实文件名、实际正文/缩略图、分类选择和处理状态；完整依据可在详情或悬停查看。

`layout.py` 是唯一功能构建器，`layout_minimal.py` 选择原生星空工作台的紧凑布局；`cards_minimal.py` 继承完整卡片/详情行为；`theme_starry.py` 提供星空绘制和语义色；`theme_minimal.py` 仅提供共用尺寸调整。文件名保留兼容性，不代表当前页面使用蓝灰配色。

正常启动：

```powershell
cd D:\MyGithub\DocumentAssistant
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

只看临时示例：

```powershell
.\.venv\Scripts\python.exe test_minimal_design.py
```

切换布局只影响下一次启动，保留现有窗口和队列：

```powershell
.\.venv\Scripts\python.exe apply_minimal_design.py --test
.\.venv\Scripts\python.exe apply_minimal_design.py --restore
.\.venv\Scripts\python.exe apply_minimal_design.py
```

`--restore` 选择原布局，不覆盖源码；颜色可独立从主题菜单切换。新工作台首次使用深紫星空，之后保留用户主动选择。上述脚本将偏好保存在运行目录的 `ui-layout.json`；环境变量 `DOCUMENTASSISTANT_LAYOUT=classic` 或 `minimal` 可临时覆盖。

实际结果与边界见 `IMPLEMENTATION_SUMMARY.md`。最新 HTML 原稿保留供视觉对照，浏览器中的概念按钮不是原生功能验收证据。
