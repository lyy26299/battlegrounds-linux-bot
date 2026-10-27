"""Opt-in child-only loader environment, locked to validated local files."""
import hashlib,os
from pathlib import Path
ASSEMBLY_SHA='7f81d2ab2277958dea4351c41812921a00ee263a6a7abf1a5cfb4eb0794f26e5'
def game_environment(exe,base=None):
    exe=Path(exe).resolve(strict=True)
    root=exe.parent
    if hashlib.sha256((root/'Hearthstone_Data/Managed/Assembly-CSharp.dll').read_bytes()).hexdigest()!=ASSEMBLY_SHA:
        raise RuntimeError('Game version changed; loader disabled')
    manifest=root/'BepInEx/shadow-install-manifest.json'
    import json
    installed=json.loads(manifest.read_text())
    for relative,expected in installed['files'].items():
        candidate=root/relative
        if candidate.is_symlink():raise RuntimeError('Invalid loader path')
        path=candidate.resolve(strict=True)
        if root not in path.parents:raise RuntimeError('Invalid loader path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Loader integrity mismatch')
    env=dict(os.environ if base is None else base)
    if env.get('LD_PRELOAD'):raise RuntimeError('Unknown preloaded library; refuse to combine')
    search=str(root/'BepInEx/core')
    corlib=root/'BepInEx/unstripped_corlib'
    if corlib.exists():
        names={p.name for p in corlib.iterdir()}
        if not names or not names<={'mscorlib.dll','System.Core.dll','System.dll','Newtonsoft.Json.dll','System.Configuration.dll','System.Xml.dll','Mono.Security.dll','System.Security.dll'} or any('BepInEx/unstripped_corlib/'+name not in installed['files'] for name in names):raise RuntimeError('Unvalidated core library directory')
        search=str(corlib)+':'+search
    env.update(DOORSTOP_ENABLED='1',DOORSTOP_TARGET_ASSEMBLY=str(root/'BepInEx/core/BepInEx.Unity.Mono.Preloader.dll'),
        DOORSTOP_MONO_DLL_SEARCH_PATH_OVERRIDE=search,DOORSTOP_MONO_DEBUG_ENABLED='0',
        DOORSTOP_MONO_DEBUG_SUSPEND='0',DOORSTOP_IGNORE_DISABLED_ENV='0',LD_PRELOAD=str(root/'libdoorstop.so'))
    env['LD_LIBRARY_PATH']=str(root)+((':'+env['LD_LIBRARY_PATH']) if env.get('LD_LIBRARY_PATH') else '')
    return env
