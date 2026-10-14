"""Per-user Windows login startup, limited to this application's own value."""
import subprocess,sys
from pathlib import Path
if sys.platform=='win32':import winreg

RUN_KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'

class StartupRegistration:
    def __init__(self,home,project=None,pythonw=None,value_name='DocumentAssistant'):
        self.home=Path(home).resolve();self.project=Path(project or Path(__file__).resolve().parents[1]).resolve()
        self.frozen=bool(getattr(sys,'frozen',False))
        self.pythonw=Path(pythonw or (sys.executable if self.frozen else self.project/'.venv/Scripts/pythonw.exe')).resolve();self.value_name=value_name
    @property
    def arguments(self):
        if self.frozen:return [str(self.pythonw),'--tray','--home',str(self.home)]
        return [str(self.pythonw),'-B',str(self.project/'startup.py'),'--home',str(self.home)]
    @property
    def command(self):return subprocess.list2cmdline(self.arguments)
    def read(self):
        if sys.platform!='win32':return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_READ) as key:
                value,kind=winreg.QueryValueEx(key,self.value_name)
                return value if kind==winreg.REG_SZ else '<unsupported value type>'
        except FileNotFoundError:return None
    def enabled(self):return self.read()==self.command
    def set_enabled(self,enabled):
        if sys.platform!='win32':raise OSError('开机自启动目前支持 Windows')
        current=self.read()
        if current is not None and current!=self.command:raise ValueError('同名启动项属于其他安装位置；请先在 Windows 启动应用中核对')
        if enabled:
            if not self.pythonw.is_file() or (not self.frozen and not (self.project/'startup.py').is_file()):raise OSError('找不到本程序的启动文件，请检查安装位置')
            if current==self.command:return
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key,self.value_name,0,winreg.REG_SZ,self.command)
            if not self.enabled():raise OSError('开机启动项写入后未通过核对')
        elif current is not None:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:winreg.DeleteValue(key,self.value_name)
            if self.read() is not None:raise OSError('开机启动项关闭后未通过核对')
