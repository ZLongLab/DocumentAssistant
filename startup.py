"""Windows login entry: run from any working directory and stay in the tray."""
import argparse,os,sys
from pathlib import Path

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--home',type=Path)
    args=parser.parse_args();project=Path(__file__).resolve().parent
    home=(args.home or project.parent/'DocumentAssistant-local').resolve();home.mkdir(parents=True,exist_ok=True)
    temporary=home/'tmp';temporary.mkdir(exist_ok=True)
    os.environ.update(DOCUMENTASSISTANT_HOME=str(home),TEMP=str(temporary),TMP=str(temporary),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    os.chdir(project);sys.path.insert(0,str(project))
    from document_assistant.gui import main
    return main(start_in_tray=True)

if __name__=='__main__':raise SystemExit(run())
