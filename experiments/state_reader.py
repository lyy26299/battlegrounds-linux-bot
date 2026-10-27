"""Experimental read-only shadow reader; never supplies controller actions."""
from mono_state import classes
TAGS={'entity':53,'controller':50,'zone':49,'position':263,'resources':26,'used':25,'temporary':295,'turn':20,'card_type':202,'player_id':30}
def available_gold(resources,used,temporary,queued,used_temporary):
    if resources is None or used is None:return None
    return max(0,resources+temporary-used-queued-used_temporary)

def type_name(m,obj):return m.text(m.ptr(m.ptr(m.ptr(obj))+0x40))
def map_values(m,obj,maximum):
    if type_name(m,obj)!='Map`2':raise ValueError('Unsupported map')
    array=m.ptr(obj+40);length=m.i32(array+24)
    if not 0<=length<=maximum:raise ValueError('Map exceeds limit')
    for i in range(length):
        value=m.ptr(array+32+8*i)
        if value:yield value

def tags(m,obj):
    wrapper=m.value(obj,'m_tags','ptr')
    if type_name(m,wrapper)!='TagMap':raise ValueError('Unsupported tags')
    dictionary=m.value(wrapper,'m_values','ptr')
    if type_name(m,dictionary)!='Dictionary`2':raise ValueError('Unsupported tag dictionary')
    entries=m.ptr(dictionary+24);count=m.i32(dictionary+64)
    if not 0<=count<=2048:raise ValueError('Too many tags')
    result={};wanted=set(TAGS.values())
    for i in range(count):
        entry=entries+32+16*i
        if m.i32(entry)<0:continue
        key=m.i32(entry+8)
        if key in wanted:result[key]=m.i32(entry+12)
    return result

def read_state(m):
    if not hasattr(m,'shadow_types'):m.shadow_types=classes(m,{'GameState'})
    game=m.instance(m.shadow_types['GameState'])
    if not game:return {'available':False,'reason':'no_game'}
    players=list(map_values(m,m.value(game,'m_playerMap','ptr'),32))
    local=[p for p in players if m.value(p,'m_local','bool')]
    if len(local)!=1:return {'available':False,'reason':'no_unique_local_player'}
    pt=tags(m,local[0]);player_id=pt.get(TAGS['player_id'])
    if player_id is None:return {'available':False,'reason':'missing_player_id'}
    entities=[]
    for entity in map_values(m,m.value(game,'m_entityMap','ptr'),8192):
        t=tags(m,entity)
        # Restrict output to own hand and own board. Never expose opposing hidden cards.
        if t.get(TAGS['controller'])!=player_id or t.get(TAGS['zone']) not in (1,3):continue
        record={k:t.get(TAGS[k]) for k in ('entity','controller','zone','position','card_type')}
        if record['entity'] is None:raise ValueError('Missing entity identity')
        if record['card_type'] in (4,5) and record['position'] is not None and record['position']>0:
            entities.append(record)
    resources=pt.get(TAGS['resources']);used=pt.get(TAGS['used']);temporary=pt.get(TAGS['temporary'],0)
    queued=m.value(local[0],'m_queuedSpentMana','int');used_temporary=m.value(local[0],'m_usedTempMana','int')
    gold=available_gold(resources,used,temporary,queued,used_temporary)
    if gold is not None and not 0<=gold<=100:raise ValueError('Implausible gold')
    if game!=m.instance(m.shadow_types['GameState']):raise ValueError('Scene changed during read')
    return {'available':True,'player_id':player_id,'gold_candidate':gold,'resources':resources,'used':used,'temporary':temporary,'queued':queued,'used_temporary':used_temporary,'busy':m.value(game,'m_busy','bool'),'game_over':m.value(game,'m_gameOver','bool'),'entities':entities,'control_allowed':False}
