"""Install observer into an empty mod location; never activate it or replace game files."""
import argparse,hashlib,json,os,shutil
from pathlib import Path
from loader_environment import ASSEMBLY_SHA
p=argparse.ArgumentParser();p.add_argument('game',type=Path);p.add_argument('stage',type=Path);p.add_argument('plugin',type=Path)
a=p.parse_args();os.umask(0o077)
root=a.game.resolve(strict=True);stage=a.stage.resolve(strict=True)
if hashlib.sha256((root/'Hearthstone_Data/Managed/Assembly-CSharp.dll').read_bytes()).hexdigest()!=ASSEMBLY_SHA:raise SystemExit('Unsupported game version')
for name in ('BepInEx','libdoorstop.so','run_bepinex.sh','.doorstop_version'):
 if (root/name).exists():raise SystemExit('Refusing existing loader path: '+name)
files={}
for source in stage.rglob('*'):
 if source.is_symlink():raise SystemExit('Stage contains symlink')
 if not source.is_file():continue
 rel=source.relative_to(stage)
 if str(rel)=='changelog.txt':continue
 if (root/rel).exists():raise SystemExit('Refusing existing file '+str(rel))
 files[str(rel)]=hashlib.sha256(source.read_bytes()).hexdigest()
created=[]
try:
 for rel in files:
  dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copy2(stage/rel,dest);created.append(dest)
 rel='BepInEx/plugins/BattlegroundsShadow/ShadowBridge.dll';dest=root/rel
 dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copy2(a.plugin,dest);created.append(dest)
 files[rel]=hashlib.sha256(dest.read_bytes()).hexdigest()
 (root/'BepInEx/shadow-install-manifest.json').write_text(json.dumps({'files':files,'mode':'shadow_only','assembly_sha256':ASSEMBLY_SHA},indent=2))
except BaseException:
 for path in reversed(created):path.unlink(missing_ok=True)
 raise
print('Observer files installed; not active until experimental host is selected')
