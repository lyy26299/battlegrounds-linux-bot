"""Read reward-track counters through the existing parent-owned Mono reader."""
from mono_state import classes

def static_ptr(m,c,name):
    offset,static=m.fields(c)[name]
    if not static:raise ValueError('Expected static field')
    size=m.i32(c+0x54)
    if not 0<=size<10000:raise ValueError('Invalid vtable')
    vtable=m.ptr(m.ptr(c+0xc8)+8)
    return m.ptr(m.ptr(vtable+0x48+8*size)+offset)

def dictionary_values(m,obj,maximum):
    if m.text(m.ptr(m.ptr(m.ptr(obj))+0x40))!='Dictionary`2':raise ValueError('Wrong collection type')
    entries=m.ptr(obj+24);count=m.i32(obj+64)
    if not 0<=count<=maximum:raise ValueError('Invalid dictionary count')
    if count and (not entries or m.i32(entries+24)<count):raise ValueError('Invalid entries array')
    for i in range(count):
        entry=entries+32+24*i
        if m.i32(entry)<0:continue
        value=m.ptr(entry+16)
        if value:yield value

def read_tracks(m):
    c=getattr(m,'reward_service_class',None)
    if c is None:
        c=classes(m,{'ServiceManager'},assembly_name='Blizzard.T5.ServiceLocator',namespace='Blizzard.T5.Services')['ServiceManager']
        m.reward_service_class=c
    locator=static_ptr(m,c,'s_runtimeServices')
    services=m.value(locator,'m_services','ptr')
    for info in dictionary_values(m,services,1000):
        obj=m.value(info,'<Service>k__BackingField','ptr')
        if not obj:continue
        if m.text(m.ptr(m.ptr(m.ptr(obj))+0x40))!='RewardTrackManager':continue
        result=[]
        for track in dictionary_values(m,m.value(obj,'m_rewardTrackEntries','ptr'),20):
            model=m.value(track,'<TrackDataModel>k__BackingField','ptr')
            if not model:continue
            fields={'trackId':'m_RewardTrackId','levelIndex':'m_Level','xp':'m_Xp','needed':'m_XpNeeded','total':'m_TotalXp','season':'m_Season','type':'m_RewardTrackType'}
            data={k:m.value(model,f,'int') for k,f in fields.items()}
            if data['type'] not in (1,2) or not data['trackId']:continue
            if not (0<=data['levelIndex']<10000 and 0<=data['xp']<=data['total']<100000000 and 0<=data['needed']<1000000):raise ValueError('Invalid reward counters')
            result.append(data)
        return result
    raise RuntimeError('Reward-track service not ready')
