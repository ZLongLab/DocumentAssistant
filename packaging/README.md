# Windows 打包

需要 Windows x64、Python 3.11+ 和 Inno Setup 7。

先在独立构建环境安装 `requirements-lock.txt` 和 `requirements-build.txt`，再运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build.ps1 -Python .\.venv\Scripts\python.exe -Compiler "D:\Tools\InnoSetup\ISCC.exe" -Output "D:\Builds\DocumentAssistant"
```

输出包含安装 EXE、免安装 ZIP 和 SHA256 校验文件。安装包包含 Python 与 Qt，
用户无需另装 Python。构建工作目录、缓存与临时文件保存在指定输出目录。
构建脚本会临时限制原生依赖搜索路径并清理构建缓存，避免把 Java、Poppler
等其他程序的 DLL 带入安装包；结束后恢复原来的环境变量。

发布前应在干净的 Windows 环境检查启动、文档提取、截图、录屏及卸载。
演示素材使用虚构资料；运行数据、文档库及构建日志不应提交到仓库。
