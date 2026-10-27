"""Read-only Linux Mono scene probe, experimental Unity 6000.3 x86_64.
Adapted from DawnMagnet/hearthstone-linux-gui hsreplay/mono.rs (MIT).
No injection, memory writes, credential reads or permission changes.
Caller must already have ordinary Linux permission to read the child process.
"""
import os, struct, subprocess, json, sys, hashlib
from pathlib import Path

class Memory:
    def __init__(self,pid):
        self.pid=int(pid)
        if Path(f'/proc/{pid}').stat().st_uid != os.getuid():
            raise RuntimeError('Refusing another user process')
        exe=Path(f'/proc/{pid}/exe').resolve()
        if exe.name!='Hearthstone.x86_64':
            raise RuntimeError('Not Hearthstone')
        assembly=exe.parent/'Hearthstone_Data/Managed/Assembly-CSharp.dll'
        if hashlib.sha256(assembly.read_bytes()).hexdigest()!='7f81d2ab2277958dea4351c41812921a00ee263a6a7abf1a5cfb4eb0794f26e5':
            raise RuntimeError('Game build changed; revalidate layouts before using this probe')
        self.fd=os.open(f'/proc/{pid}/mem',os.O_RDONLY)
        self.cache={}
    def close(self): os.close(self.fd)
    def read(self,addr,n):
        if not (0<addr<2**47 and 0<=n<=1048576 and addr+n<2**47):
            raise ValueError('Invalid memory range')
        try:
            b=os.pread(self.fd,n,addr)
        except OSError as exc:
            raise OSError(exc.errno,f'Mono read at {addr:#x}, length {n}: {exc.strerror}') from exc
        if len(b)!=n: raise RuntimeError('Short memory read')
        return b
    def ptr(self,a): return struct.unpack('<Q',self.read(a,8))[0]
    def i32(self,a): return struct.unpack('<i',self.read(a,4))[0]
    def text(self,a): return self.read(a,128).split(b'\0',1)[0].decode('utf8',errors='strict') if a else ''
    def fields(self,c):
        if c in self.cache:return self.cache[c]
        result={};seen=set();current=c
        while current:
            if current in seen or len(seen)>=64:raise RuntimeError('Cyclic class chain')
            seen.add(current);array=self.ptr(current+0x90);count=self.i32(current+0xf8)
            if not 0<=count<10000:raise RuntimeError('Invalid field count')
            for i in range(count if array else 0):
                f=array+i*0x20; offset=self.i32(f+0x18)
                flags=struct.unpack('<H',self.read(self.ptr(f)+8,2))[0]
                if offset>=0:result.setdefault(self.text(self.ptr(f+8)),(offset,bool(flags&16)))
            current=self.ptr(current+0x28)
        self.cache[c]=result;return result
    def instance(self,c):
        offset,static=self.fields(c)['s_instance']
        if not static:raise RuntimeError('Singleton field not static')
        size=self.i32(c+0x54)
        if not 0<=size<10000:raise RuntimeError('Invalid vtable size')
        runtime=self.ptr(c+0xc8)
        if not runtime:return 0
        vtable=self.ptr(runtime+8)
        if not vtable:return 0
        statics=self.ptr(vtable+0x48+8*size)
        if not statics:return 0
        return self.ptr(statics+offset)
    def value(self,obj,name,kind):
        c=self.ptr(self.ptr(obj));offset,static=self.fields(c)[name]
        if static:raise RuntimeError('Expected instance field')
        a=obj+offset
        if kind=='bool':
            b=self.read(a,1)[0]
            if b not in (0,1):raise RuntimeError('Invalid boolean')
            return bool(b)
        if kind=='ptr':return self.ptr(a)
        return self.i32(a)

def root_domain(m):
    for line in Path(f'/proc/{m.pid}/maps').read_text().splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)==6 and int(parts[2],16)==0 and parts[5].endswith('/libmonobdwgc-2.0.so'):
            base=int(parts[0].split('-')[0],16);lib=f'/proc/{m.pid}/root'+parts[5];break
    else: raise RuntimeError('Mono runtime not loaded')
    symbols=subprocess.run(['readelf','--dyn-syms','--wide',lib],capture_output=True,text=True,check=True,timeout=5).stdout
    for line in symbols.splitlines():
        p=line.split()
        if len(p)>=8 and p[7]=='mono_get_root_domain':symbol=base+int(p[1],16);break
    else: raise RuntimeError('Mono symbol missing')
    b=m.read(symbol,16);start=4 if b.startswith(bytes.fromhex('f30f1efa')) else 0
    if b[start:start+3]!=bytes.fromhex('488b05') or b[start+7]!=0xc3:raise RuntimeError('Unsupported Mono runtime code')
    return m.ptr(symbol+start+7+struct.unpack('<i',b[start+3:start+7])[0])

def classes(m,names,assembly_name='Assembly-CSharp',namespace=''):
    node=m.ptr(root_domain(m)+0x98);seen=set()
    while node:
        if node in seen or len(seen)>=4096:raise RuntimeError('Invalid assembly chain')
        seen.add(node);assembly=m.ptr(node)
        if m.text(m.ptr(assembly+0x10))==assembly_name:image=m.ptr(assembly+0x60);break
        node=m.ptr(node+8)
    else:raise RuntimeError('Game assembly not loaded')
    cache=image+0x4d0;size=m.i32(cache+0x18);table=m.ptr(cache+0x20)
    if not 0<=size<=2**20:raise RuntimeError('Invalid cache size')
    result={};seen=set()
    for bucket in range(size):
        c=m.ptr(table+8*bucket)
        while c:
            if c in seen or len(seen)>=2**21:raise RuntimeError('Invalid class cache')
            seen.add(c);name=m.text(m.ptr(c+0x40))
            if name in names and m.text(m.ptr(c+0x48))==namespace:
                result[name]=c
                if set(result)==names:return result
            c=m.ptr(c+0x100)
    if names-set(result):raise RuntimeError('Required classes missing')
    return result

def snapshot(m,types):
    scene=m.instance(types['SceneMgr']);game=m.instance(types['GameState'])
    result={'scene_present':bool(scene),'game_present':bool(game)}
    if scene:
        for field,kind in [('m_mode','int'),('m_sceneLoaded','bool'),('m_transitioning','bool')]:
            result[field]=m.value(scene,field,kind)
    if game:
        for field in ['m_gameOver','m_busy']:
            result[field]=m.value(game,field,'bool')
        entity=m.value(game,'m_gameEntity','ptr')
        if entity:
            result['bacon_combat_phase']=m.value(entity,'m_realTimeBaconCombatPhase','int')
    return result

if __name__=='__main__':
    m=Memory(int(sys.argv[1]))
    try:print(json.dumps(snapshot(m,classes(m,{'SceneMgr','GameState'}))))
    finally:m.close()

class StateObserver:
    """Optional diagnostic; failure never supplies a guessed gameplay state."""
    def __init__(self):
        self.memory=None
        self.types=None
        self.denied_pid=None
    def close(self):
        if self.memory:self.memory.close()
        self.memory=self.types=None
    def observe(self,pid):
        if pid==self.denied_pid:return {'available':False,'reason':'not_parent'}
        if self.memory and self.memory.pid!=pid:self.close()
        stage='open'
        try:
            if not self.memory:self.memory=Memory(pid)
            stage='classes'
            if not self.types:self.types=classes(self.memory,{'SceneMgr','GameState'})
            stage='snapshot'
            return {'available':True,**snapshot(self.memory,self.types)}
        except PermissionError:
            self.close();self.denied_pid=pid
            return {'available':False,'reason':'not_parent'}
        except (OSError,ValueError,RuntimeError,KeyError,subprocess.SubprocessError) as exc:
            self.close()
            return {'available':False,'reason':stage+': '+type(exc).__name__+': '+str(exc)}


def retain_game_parentage():
    import ctypes
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'Cannot preserve game child parentage')
