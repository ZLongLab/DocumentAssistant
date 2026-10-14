"""Validated preferences for screenshot tools, stored separately from hotkey settings."""
import copy,json

DEFAULT_TOOLS={
    'rectangle':{'color':'#e34f45','width':3},
    'arrow':{'color':'#e34f45','width':3},
    'text':{'color':'#e34f45','size':22},
    'mask':{'brush':12,'block':6},
}
COLORS=('#e34f45','#ec9b21','#377fde','#24825c')

def normalize_tools(value):
    result=copy.deepcopy(DEFAULT_TOOLS)
    if not isinstance(value,dict):return result
    limits={'width':(1,16),'size':(12,64),'brush':(4,64),'block':(2,32)}
    for kind,defaults in result.items():
        saved=value.get(kind)
        if not isinstance(saved,dict):continue
        for key in defaults:
            item=saved.get(key)
            if key=='color':
                if item in COLORS:defaults[key]=item
            elif type(item) is int and limits[key][0]<=item<=limits[key][1]:defaults[key]=item
    return result

def load_tools(path):
    try:return normalize_tools(json.loads(path.read_text(encoding='utf-8')))
    except (OSError,ValueError):return normalize_tools(None)

def save_tools(path,value):
    data=normalize_tools(value)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    return data
