"""Candidate state-to-observation adapter. Must be explicitly enabled after P1 checks."""
import math
from core import Observation,Phase

def stable_recruit(previous,current):
    """Two current main-thread snapshots, with a new sequence and unchanged option context."""
    for s in (previous,current):
        if not isinstance(s,dict) or s.get('available') is not True or s.get('busy') is not False or s.get('game_over') is not False:return False
        if s.get('combat_tag')!=0 or type(s.get('options_id')) is not int or s['options_id']<0:return False
        if not s.get('game_id') or not s.get('session'):return False
        seconds=s.get('seconds_candidate')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 5<=seconds<=300:return False
        if type(s.get('gold_candidate')) is not int or not 0<=s['gold_candidate']<=100:return False
    if any(previous.get(k)!=current.get(k) for k in ('pid','session','game_id','turn','options_id','gold_candidate')):return False
    if type(previous.get('updates')) is not int or type(current.get('updates')) is not int or previous['updates']>=current['updates']:return False
    # Options can stay unchanged while dealing/board animations move click targets.
    try:
        for key in ('entities','shop_candidates'):
            old={c['entity']:c for c in previous[key]}
            new={c['entity']:c for c in current[key]}
            if len(old)!=len(previous[key]) or len(new)!=len(current[key]) or old.keys()!=new.keys():return False
            for identity,card in new.items():
                before=old[identity]
                if any(before.get(k)!=card.get(k) for k in ('zone','position','card_type')):return False
                if before.get('input_ready') is not True or card.get('input_ready') is not True:return False
                for axis in ('x','y'):
                    values=(before.get(axis),card.get(axis))
                    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return False
                    if abs(values[0]-values[1])>.015:return False
    except (KeyError,TypeError,ValueError):return False
    return True

def observation(previous,current):
    if not stable_recruit(previous,current):return None
    def positions(records):
        points=[];ids=set();indices=set()
        for card in sorted(records,key=lambda x:x['position']):
            x,y=card.get('x'),card.get('y');identity=card.get('entity');position=card['position']
            if type(identity) is not int or identity<=0 or identity in ids or type(position) is not int or position<=0 or position in indices:raise ValueError('Ambiguous entity')
            ids.add(identity);indices.add(position)
            if card.get('input_ready') is not True:raise ValueError('Entity not ready')
            if any(type(v) not in (int,float) or not math.isfinite(v) or not .02<v<.98 for v in (x,y)):raise ValueError('Invalid card coordinates')
            points.append((x,y))
        return points
    try:
        entities=current['entities']
        # Spells and targeted actions still require the existing verified path.
        if any(c['zone']==3 and c['card_type']!=4 for c in entities):return None
        hand=positions([c for c in entities if c['zone']==3])
        board=positions([c for c in entities if c['zone']==1])
        shop=positions(current['shop_candidates'])
        if len(hand)>10 or len(board)>7 or len(shop)>7:return None
        return Observation(phase=Phase.RECRUIT,gold=current['gold_candidate'],seconds=int(current['seconds_candidate']),hand=hand,board=board,shop=shop,
            signature=':'.join(str(current[k]) for k in ('game_id','turn','options_id','gold_candidate'))+repr([(c['entity'],c['zone'],c['position']) for c in entities])+repr([(c['entity'],c['position']) for c in current['shop_candidates']]),evidence=['experimental_state_reader'])
    except (KeyError,TypeError,ValueError):return None
