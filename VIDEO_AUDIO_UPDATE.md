# 录屏声音选项

2026-10-19，本地源码更新。用户确认“有声”指电脑播放的课程/视频声音。

## 使用

1. 重启程序后，按原截图快捷键（默认 Alt+S）。
2. 点击“视频”，旁边显示声音下拉框，选择“无声”或“有声（电脑声音）”。初始为无声，同次运行中的选择会同步到各个截图覆盖层。
3. 框选后点击“开始录制”或按 Enter。倒计时结束才开始画面和声音采集；倒计时取消不创建录屏文件，也不启动音频采集。
4. 按截图快捷键或停止按钮结束，预览后保存 MP4。有声预览支持静音/取消静音。

有声模式只回录 Windows 默认播放设备，不打开麦克风。请让课程/视频从默认播放设备播放。本轮没有增加麦克风或单独应用音频选择功能。

## 实现与依赖

- 复用原有 Qt 区域采集与 H.264 MP4 编码；Windows 播放回录采用 PyAudioWPatch/WASAPI，PCM 通过 QAudioBufferInput 接入同一 Qt 录制会话。AAC 目标码率 128 kb/s，已在本机产物中确认 AAC-LC 128 kb/s。
- 音频与视频共享录制时间基准；先静音、后有声和中间暂停播放不会把声音提前拼接。编码繁忙时保留未发送数据；停止时结束回录并排空音频再封装视频。
- 有声采集失败会报告原因；已有片段尽量完成封装并在预览显示提前结束原因，不自动伪装成成功的无声录制。
- 预览接入 QAudioOutput，支持实际声音播放。只配置每个预览流的音量/静音，不修改系统音量。
- 新依赖 `PyAudioWPatch==0.2.12.9`（Windows 条件依赖），已安装在 `D:\MyGithub\DocumentAssistant\.venv`，下载缓存仍在 D 盘。更新 requirements、锁文件、PyInstaller 元数据与第三方通知。新环境运行 `setup.ps1` 即安装依赖。

参考：[PyAudioWPatch 系统声音回录](https://github.com/s0d3s/PyAudioWPatch)、[Qt QAudioBufferInput](https://doc.qt.io/qt-6/qaudiobufferinput.html)。

## 验证

- 原有录屏测试 8 项通过；新增 5 项覆盖声音选择同步、倒计时取消、采集失败、时间间隔和编码背压。
- 使用生成画面和 PCM 编码并解码真实 MP4：无声文件没有音轨，有声文件有可解码 AAC 音轨；两个测试音区间存在，开始与中间静音保持原位。最终编码配置下也通过。
- 本机实际回录验证通过：默认 `FxSound Speakers` 播放 1.2 秒低音量 880 Hz 测试音，经 WASAPI 回录、AAC MP4 保存及解码，检测到非零测试声音，未启用麦克风。测试没有修改系统音量。
- 实际界面流程通过：点击视频、选择有声、倒计时、生成信号录制、停止、带声音输出的预览、静音开关、保存及临时文件清理。
- 相关截图标注与布局回归见验证目录报告。本轮示例画面完全生成，没有读取真实文档或录制真实桌面。

产物目录：`D:\MyGithub\DocumentAssistant-local\verification\video-audio-20261019`。
`mux-final/audio-mux-result.json` 是最终编码配置报告；`loopback/system-audio-result.json` 是本机实际播放回录报告；`ui/ui-result.json` 是界面流程报告。

备份：`D:\MyGithub\DocumentAssistant-local\backups\video-audio-20261019-114053`。

## 范围

短片编码、解码、默认播放设备回录和界面已验证。尚未验证长时间课程录制、蓝牙设备切换、各厂商电脑兼容性及用户实际听感。没有重新构建或发布安装包，没有退出用户正在运行的旧进程。

正常加载更新：从托盘“退出”，再运行 `D:\MyGithub\DocumentAssistant\Start-DocumentAssistant.cmd`。旧进程不会自动重载源码。
