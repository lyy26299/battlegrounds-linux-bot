"""Compile against the exact game's Mono assemblies, without NuGet packages."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[4]
sdk=root/'work/low-load-v2/dotnet'
compilers=list((sdk/'sdk').glob('*/Roslyn/bincore/csc.dll'))
if not compilers:raise SystemExit('SDK download/installation has not completed')
managed=root/'work/linux-bridge/managed';loader=root/'work/low-load-v2/loader/BepInEx/core'
source=Path(__file__).with_name('ShadowBridge.cs');out=source.with_suffix('.dll')
refs=[managed/n for n in ['mscorlib.dll','System.dll','System.Core.dll','UnityEngine.dll','UnityEngine.CoreModule.dll','UnityEngine.SharedInternalsModule.dll','UnityEngine.InputLegacyModule.dll']]
refs += [loader/n for n in ['BepInEx.Core.dll','BepInEx.Unity.Mono.dll']]
for ref in refs:
 if not ref.exists():raise SystemExit('Missing build reference: '+ref.name)
subprocess.run([str(sdk/'dotnet'),str(sorted(compilers)[-1]),'/nologo','/noconfig','/nostdlib+','/target:library','/optimize+','/out:'+str(out),*[('/reference:'+str(r)) for r in refs],str(source)],check=True)
print('Built',out.name)
