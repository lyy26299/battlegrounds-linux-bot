"""Screen-only recognition for the Chinese 4:3 Battlegrounds client.

This module never controls a desktop. It is also used to replay saved images.
"""
import hashlib
import json
import re
from dataclasses import dataclass

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from core import Observation, Phase
from recovery import disconnected


def parse_gold(text):
    text = text.replace(' ', '').replace('／', '/').replace('.', '/')
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})', text)
    if m:
        a, b = map(int, m.groups())
        return a if 0 <= a <= 99 and 0 <= b <= 20 and (b > 0 or a == 0) else None
    if not text.isdigit():
        return None
    # The tiny slash can disappear in remote screenshots. Accept only an
    # unambiguous valid resource pair, never a guessed number from elsewhere.
    pairs = []
    for i in range(1, len(text)):
        left, right = text[:i], text[i:]
        if (len(left) > 1 and left.startswith('0')) or right.startswith('0'):
            continue
        a, b = int(left), int(right)
        if 0 <= a <= 99 and 0 <= b <= 20 and (b > 0 or a == 0):
            pairs.append(a)
    return pairs[0] if len(pairs) == 1 else None


@dataclass
class Word:
    text: str
    confidence: float
    x: float
    y: float


def color_objects(image, roi, color, min_width=.025, min_height=.05, max_width=.25):
    h, w = image.shape[:2]
    x0, y0, x1, y1 = roi
    crop = image[int(y0*h):int(y1*h), int(x0*w):int(x1*w)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    bounds = {'purple': ((125, 80, 75), (169, 255, 255)),
              'blue': ((78, 65, 110), (118, 255, 255)),
              'green': ((35, 90, 110), (85, 255, 255))}
    lo, hi = bounds[color]
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5,5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x,y,cw,ch = cv2.boundingRect(c)
        if cw >= min_width*w and ch >= min_height*h and cw <= max_width*w:
            boxes.append(((int(x0*w)+x+cw/2)/w, (int(y0*h)+y+ch/2)/h, cw/w, ch/h))
    return sorted(boxes)


def targeting_arrow(image):
    h,w=image.shape[:2]
    hsv=cv2.cvtColor(image,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array((0,130,100)),np.array((12,255,255)))
    mask|=cv2.inRange(hsv,np.array((170,130,100)),np.array((179,255,255)))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    points=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c)
        if .2*w<x<.96*w and .03*h<y<.72*h and cw>.04*w and ch>.035*h and cv2.contourArea(c)>.001*w*h:
            points.append(((x+cw/2)/w,(y+ch/2)/h))
    if len(points)<3:return False
    a=np.array(points)
    return bool(np.ptp(a[:,0])>.18 and np.ptp(a[:,1])>.2 and np.corrcoef(a.T)[0,1]<-.85)


def three_choice_cards(image):
    # Card art splits the green outline into disconnected left/right arcs.
    # Require both tall edges for all three visible cards before clicking.
    edges=color_objects(image,(.08,.19,.92,.65),'green',.01,.18)
    targets=[]
    for center in (.215,.5,.785):
        left=[x for x,y,w,h in edges if center-.14<x<center-.04]
        right=[x for x,y,w,h in edges if center+.04<x<center+.14]
        if not left or not right:return []
        targets.append(((min(left)+max(right))/2,.40))
    return targets


class Detector:
    def __init__(self):
        self.ocr = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)

    def read(self, image, roi=(0,0,1,1), scale=1):
        h,w = image.shape[:2]
        x0,y0,x1,y1 = roi
        crop = image[int(h*y0):int(h*y1),int(w*x0):int(w*x1)]
        if scale != 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        rows,_ = self.ocr(crop)
        result=[]
        for box,text,conf in rows or []:
            if conf < .65:
                continue
            pts = np.array(box)
            result.append(Word(text, float(conf), float(pts[:,0].mean()/scale/w+x0),
                               float(pts[:,1].mean()/scale/h+y0)))
        return result

    def observe(self, image):
        h,w = image.shape[:2]
        if abs(w/h - 4/3) > .025:
            raise ValueError('当前仅验证 4:3 游戏画面。请将游戏设为 1024×768 全屏。')
        words = self.read(image)
        text = ''.join(v.text for v in words)
        obs = Observation(evidence=[v.text for v in words])
        phase_words = [v for v in words if v.x>.84 and .38<v.y<.55]
        timer = re.search(r'(\d{1,3})秒', ''.join(v.text for v in phase_words))
        gold_words=self.read(image,(.68,.90,.744,.95),scale=4) if timer else []
        detected_gold=parse_gold(''.join(v.text for v in gold_words))
        error_title=any(v.text.replace(' ','')=='发生错误' and .3<v.x<.7 and .25<v.y<.5 for v in words)
        choice_title=any(v.text.replace(' ','')=='抉择' and .3<v.x<.7 and .08<v.y<.22 for v in words)
        if error_title:
            # A modal must block the lobby behind it, even if its message is unknown.
            if '对手无法' in text and '游戏无法继续' in text:
                confirm=next((v for v in words if v.text.replace(' ','')=='确定' and .35<v.x<.65 and .5<v.y<.7),None)
                if confirm:
                    obs.phase=Phase.CHOICE
                    obs.buttons['dismiss_match_error']=(confirm.x,confirm.y)
        elif disconnected(text):
            obs.phase = Phase.DISCONNECTED
        elif '正在启动' in text and '暴雪娱乐' in text:
            obs.phase=Phase.LOADING
        elif '点击开始' in text and '健康生活' in text:
            enter=next((v for v in words if v.text.replace(' ','')=='点击开始' and .3<v.x<.7 and .7<v.y<.9),None)
            if enter:
                obs.phase=Phase.START_SCREEN
                obs.buttons['enter']=(enter.x,enter.y)
        elif any(v.text.replace(' ','') in ('你的每周任务','你的任务','你的活动任务') and .30<v.x<.70 and .12<v.y<.30 for v in words):
            obs.phase=Phase.CHOICE
            obs.buttons['dismiss_weekly']=(.50,.76)
        elif '选择一个英雄' in text:
            obs.phase = Phase.HERO
            # An active confirmation button has a bright blue border. Grey
            # confirmation must not be treated as successful hero selection.
            blue = color_objects(image,(.43,.73,.58,.84),'blue',.03,.025)
            if blue:
                obs.buttons['confirm_active']=(.5,.79)
        elif '饰品商店' in text:
            obs.phase=Phase.CHOICE
            # Timed choices need the same stale-frame gate as recruit actions.
            obs.seconds=int(timer.group(1)) if timer else None
            obs.buttons['choice']=(.22,.40)
            if color_objects(image,(.43,.65,.58,.75),'blue',.04,.025):
                obs.buttons['confirm_choice']=(.5,.70)
        elif choice_title:
            # Never let a visible choice modal fall through to the shop beneath it.
            obs.phase=Phase.CHOICE
            obs.seconds=int(timer.group(1)) if timer else None
            choices=color_objects(image,(.1,.2,.9,.7),'green',.1,.2,.3)
            first=[c for c in choices if .18<c[0]<.30 and .3<c[1]<.6]
            hidden=any(v.text=='隐藏' and .1<v.x<.35 and .65<v.y<.85 for v in words)
            three=len(choices)==3 and .43<choices[1][0]<.57 and .7<choices[2][0]<.82
            if len(first)==1 and (hidden or three):
                obs.buttons['choice']=(first[0][0],first[0][1])
        elif '进行选择' in text:
            obs.phase=Phase.CHOICE
            cards=three_choice_cards(image) or color_objects(image,(.15,.27,.85,.72),'green',.08,.20)
            if cards:
                obs.buttons['choice']=(cards[0][0],cards[0][1])
        elif any(re.fullmatch(r'第[一二三四五六七八1-8]名[!！]?', v.text.replace(' ','')) and .25<v.x<.75 and .15<v.y<.65 for v in words) and '等级' in text:
            obs.phase=Phase.RESULT
            obs.buttons['continue']=(.5,.61)
        elif (timer and '联盟重锤' in text and '联盟盾牌' in text
              and len(choice_pair := color_objects(image,(.15,.19,.85,.69),'green',.08,.25)) == 2
              and .28 < choice_pair[0][0] < .45 and .55 < choice_pair[1][0] < .72):
            # This modal keeps the recruit timer/gold visible behind it and has
            # no generic choice heading. Resolve it before inspecting the hand.
            obs.phase=Phase.CHOICE
            obs.seconds=int(timer.group(1))
            obs.buttons['choice']=(choice_pair[0][0],choice_pair[0][1])
        elif timer and detected_gold is not None:
            obs.phase=Phase.RECRUIT
            obs.seconds=int(timer.group(1))
        elif any('战斗' in v.text for v in phase_words):
            obs.phase=Phase.COMBAT
        elif '酒馆战棋' in text and ('等级' in text or '赛季奖励' in text):
            start=next((v for v in words if v.text=='开始' and v.x>.7 and v.y>.6),None)
            if start:
                obs.phase=Phase.LOBBY
                obs.buttons['start']=(start.x,start.y)
        elif '传统对战' in text and '其他模式' in text:
            bg=next((v for v in words if v.text=='酒馆战棋' and .3<v.x<.7 and .2<v.y<.6),None)
            if bg:
                obs.phase=Phase.MENU
                obs.buttons['battlegrounds']=(bg.x,bg.y)
        elif any(s in text for s in ('正在寻找','寻找对手','正在匹配','搜寻对手')):
            obs.phase=Phase.QUEUE
        # Unvalidated choice screens remain unknown and never click.
        if obs.phase==Phase.RECRUIT:
            obs.gold=detected_gold
            obs.evidence += ['gold:'+v.text for v in gold_words]
            # Purple tavern-tier shields are above both minions and the spell;
            # exclude the rightmost shield (the tavern spell) entirely.
            shop=color_objects(image,(.15,.27,.85,.335),'purple',.014,.025)
            obs.shop=[(x,.37) for x,y,bw,bh in shop[:-1] if .015<bw<.055]
            hand=color_objects(image,(.24,.84,.69,.985),'green',.025,.035,.5)
            # Tier badges distinguish minions from targeted spells such as Bananas.
            badges=color_objects(image,(.24,.84,.69,.985),'purple',.008,.015,.06)
            obs.hand=[(min(.68,x+.025),min(.945,max(.91,y+.045))) for x,y,bw,bh in badges]
            if targeting_arrow(image):
                obs.buttons['cancel_target']=(.5,.5)
            board=color_objects(image,(.13,.48,.84,.66),'blue',.025,.06)
            # Blue outlines can split into left and right arcs around artwork.
            groups=[]
            for x,y,bw,bh in board:
                if groups and x-groups[-1][-1][0]<.06:
                    groups[-1].append((x,y))
                else:
                    groups.append([(x,y)])
            obs.board=[tuple(np.mean(g,axis=0)) for g in groups]
        # Ignore timer, animations and OCR noise when checking action progress.
        state=(obs.phase.value,obs.gold,
               [(round(x,2),round(y,2)) for x,y in obs.shop],
               [(round(x,2),round(y,2)) for x,y in obs.hand],
               len(obs.board),sorted(obs.buttons))
        obs.signature=hashlib.sha256(json.dumps(state).encode()).hexdigest()[:16]
        return obs


if __name__=='__main__':
    import argparse
    from dataclasses import asdict
    from PIL import Image
    parser=argparse.ArgumentParser()
    parser.add_argument('images',nargs='+')
    args=parser.parse_args()
    detector=Detector()
    for path in args.images:
        image=np.array(Image.open(path).convert('RGB'))
        print(json.dumps({'path':path,'observation':asdict(detector.observe(image))},ensure_ascii=False))
