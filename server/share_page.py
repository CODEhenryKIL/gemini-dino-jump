"""Public invitation previews. Reading a card never creates a visit or reward."""
from html import escape
import json
import re
from urllib.parse import urlencode

KINDS = {'initial', 'record_share', 'prize_share', 'retry_invite'}
IMAGE_PATH = '/assets/dino/gemini_dino_anime.jpg'
DEFAULT_CARD = {'title':'공룡 점프 챌린지','description':'친구와 기록에 도전하고, 참가자당 한 번의 복주머니를 열어 보세요.'}


def share_target(code, query):
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,64}', code):
        raise ValueError('invalid invite code')
    target = {'invite': code}
    rules = {'link': r'initial|record_share|prize_share|retry_invite',
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
      case when d.revealed and d.is_won then z.name end prize_name
      from dino_dev.participant p left join {_score_source(version)} b on b.participant_id=p.id
      left join dino_dev.draw d on d.participant_id=p.id and d.campaign_id=p.campaign_id
      left join dino_dev.prize z on z.id=d.prize_id
      where p.referral_code=%s and p.campaign_id=%s and p.status='ACTIVE' ''', (code, campaign_id)).fetchone()
    title = DEFAULT_CARD['title']
    description = DEFAULT_CARD['description']
    if row and row['is_public']:
        if kind == 'record_share' and row['score'] is not None:
            title = f"{row['nickname']}님의 {row['score']}점에 도전해 봐!"
            description = '코인과 하트를 모아 내 최고 기록에 도전하세요.'
        elif kind == 'prize_share' and row['prize_name']:
            title = f"{row['nickname']}님의 복주머니 결과"
            description = f"테스트 경품: {row['prize_name']}. 실제 경품 지급이 없는 검토용 화면입니다."
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
<meta name="twitter:card" content="summary_large_image"></head>
<body><main><h1>{title}</h1><p>{description}</p><p>게임은 누구나 참여할 수 있고, 실제 경품 대상은 대학 재학생입니다.</p>
<a href="{escape(destination, quote=True)}">공룡 점프 시작하기</a></main>
<script>window.location.replace({js_destination});</script></body></html>'''.encode('utf-8')
