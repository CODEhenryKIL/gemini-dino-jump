from config import database_schema
"""Public invitation previews. Reading a card never creates a visit or reward."""
from html import escape
import json
import re
from urllib.parse import urlencode

KINDS = {'initial', 'record_share', 'draw_retry', 'prize_share', 'retry_invite', 'general_share'}
IMAGE_PATH = '/assets/prizes/prize-lineup-cutout-v2.png'
DEFAULT_CARD = {'title':'삼탠바이미 그냥 뿌립니다. 🎁','description':'게임 한 판 하고 꽝 없는 상품 받아가자!'}


def share_target(code, query):
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,64}', code):
        raise ValueError('invalid invite code')
    target = {'invite': code}
    rules = {'link': r'initial|record_share|draw_retry|prize_share|retry_invite|general_share',
             'share': r'[A-Za-z0-9:_-]{8,128}',
             'channel': r'[A-Za-z][A-Za-z0-9_-]{0,31}',
             'campaign': r'[A-Za-z][A-Za-z0-9_-]{0,31}'}
    for key, pattern in rules.items():
        values = query.get(key, [])
        if len(values) == 1 and re.fullmatch(pattern, values[0]):
            target[key] = values[0]
    target.setdefault('link', 'retry_invite')
    return target


def public_card(conn, code, kind, version, campaign_id):
    from operations import _score_source
    # Explicit public fields only: never join claims, contacts or authentication.
    row = conn.execute(f'''select p.nickname,p.is_public,b.score,
      case when d.revealed and d.outcome_kind='PRIZE' then z.name end prize_name,
      (select count(*)::int from {_score_source(version)} scores
        join {database_schema()}.participant counted on counted.id=scores.participant_id
        where counted.campaign_id=%s and counted.status='ACTIVE') participant_count
      from {database_schema()}.participant p left join {_score_source(version)} b on b.participant_id=p.id
      left join lateral (select * from {database_schema()}.draw latest where latest.participant_id=p.id and latest.campaign_id=p.campaign_id order by latest.round_number desc limit 1) d on true
      left join {database_schema()}.prize z on z.id=d.prize_id
      where p.referral_code=%s and p.campaign_id=%s and p.status='ACTIVE' ''', (campaign_id, code, campaign_id)).fetchone()
    title = DEFAULT_CARD['title']
    description = DEFAULT_CARD['description']
    if row:
        if kind in {'record_share','retry_invite'}:
            title = f"현재 {row['participant_count']}명, 1등 노려볼 만해! 👀"
            description = '🥇 행사 종료 1등은 무신사 5만원권!'
        elif kind == 'prize_share' and row['prize_name']:
            title = f"나 {row['prize_name']} 뽑았다!"
            description = '삼텐바이미도 나온대! 너도 해봐!'
    return {'title': title, 'description': description}


def render_share_page(card, base_url, code, target):
    destination = '/?' + urlencode(target)
    canonical = base_url + '/invite/' + code + '?' + urlencode({k: v for k, v in target.items() if k != 'invite'})
    title, description = escape(card['title'], quote=True), escape(card['description'], quote=True)
    js_destination = json.dumps(destination).replace('<', '\\u003c')
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>{title}</title><meta name="description" content="{description}">
<meta property="og:type" content="website"><meta property="og:title" content="{title}">
<meta property="og:description" content="{description}"><meta property="og:url" content="{escape(canonical, quote=True)}">
<meta property="og:image" content="{escape(base_url + IMAGE_PATH, quote=True)}">
<meta property="og:image:width" content="1254"><meta property="og:image:height" content="1254">
<meta property="og:image:alt" content="삼텐바이미, 소니 헤드셋, 오쏘몰과 간식 경품">
<meta name="twitter:card" content="summary_large_image"></head>
<body><main><h1>{title}</h1><p>{description}</p><p>게임은 누구나 참여할 수 있고, 실제 경품 대상은 대학 재학생·휴학생입니다.</p>
<a href="{escape(destination, quote=True)}">공룡 점프 시작하기</a></main>
<script>window.location.replace({js_destination});</script></body></html>'''.encode('utf-8')
