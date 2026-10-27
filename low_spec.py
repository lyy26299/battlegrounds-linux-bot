"""Back up and edit the upstream Linux player's options; no game patches."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET


def update(text,fps,resolution=None):
    settings={'graphicsquality':'0','targetframerate':str(fps),'vsync':'0'}
    if resolution is not None:
        if resolution not in ('800x600','1024x768'):raise ValueError('Unsupported resolution')
        width,height=resolution.split('x')
        settings.update(graphicswidth=width,graphicsheight=height)
    result=[]
    for line in text.splitlines():
        if line.partition('=')[0].strip() not in settings: result.append(line)
    return '\n'.join(result+[f'{k}={v}' for k,v in settings.items()])+'\n'

def unity_resolution(text,resolution):
    if resolution not in ('800x600','1024x768'):raise ValueError('Unsupported resolution')
    width,height=resolution.split('x')
    values={'Screenmanager Resolution Width':width,'Screenmanager Resolution Height':height,
            'Screenmanager Resolution Use Native':'0'}
    root=ET.fromstring(text)
    found=set()
    for node in root:
        key=node.attrib.get('name')
        if key in values:
            node.text=values[key];found.add(key)
    if found!=set(values):raise ValueError('Unity resolution fields missing; inspect preferences first')
    return ET.tostring(root,encoding='unicode')


def save_backup(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        backup=path.with_name(path.name+'.backup-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))
        backup.write_bytes(path.read_bytes())
        print('Backup:',backup)
    path.write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Close the game before applying; start with 30 FPS')
    p.add_argument('--fps',type=int,choices=(20,30),default=30)
    p.add_argument('--resolution',choices=('800x600','1024x768'),help='Optional 4:3 render size; defaults to preserving current size')
    p.add_argument('--apply',action='store_true',help='Otherwise print preview only')
    p.add_argument('--path',type=Path,default=Path.home()/'Library/Preferences/Blizzard/Hearthstone/options.txt')
    p.add_argument('--unity-prefs',type=Path,default=Path.home()/'.config/unity3d/Blizzard Entertainment/Hearthstone/prefs')
    a=p.parse_args(); text=a.path.read_text() if a.path.exists() else ''
    proposed=update(text,a.fps,a.resolution)
    native=unity_resolution(a.unity_prefs.read_text(),a.resolution) if a.resolution else None
    if a.apply:
        save_backup(a.path,proposed)
        if native is not None:save_backup(a.unity_prefs,native)
    else:
        print(proposed,end='')
        if native is not None:print('Unity window resolution would also be set to',a.resolution)
