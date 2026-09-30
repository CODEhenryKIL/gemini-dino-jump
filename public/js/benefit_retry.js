// Presentation only. The webhook independently rechecks and grants each reward.
export function benefitRetryAvailability(draw = {}, tickets = {}, status = 'ACTIVE', now = Date.now()) {
  const active = status === 'ACTIVE';
  const used = Number(draw.used_count || 0);
  const credits = Number(draw.available_credits || 0);
  const max = Number(draw.max_count || 10);
  const won = draw.actual_prize_won === true;
  const cooldown = Date.parse(tickets.cooldown_until || '') > now;
  const capped = Number(tickets.invitation || 0) + Number(tickets.invitation_reserved || 0) >= 3;
  const drawGrant = active && !won && used + credits < max;
  const gameGrant = active && !won && !cooldown && !capped;
  const drawReady = !won && credits > 0 && used < max;
  const gameReady = tickets.unlimited_play === true || Number(tickets.available_total ?? (Number(tickets.initial || 0) + Number(tickets.invitation || 0))) > 0;
  let message;
  if (!active) message = status === 'NOT_OPEN' ? '행사 시작 후 재도전할 수 있어요.' : '현재 추가 뽑기와 게임권 적립을 이용할 수 없어요.';
  else if (drawGrant && gameGrant) message = '카카오톡 전송 확인 시 뽑기권 1개 + 게임권 1장';
  else if (drawGrant) message = `카카오톡 전송 확인 시 뽑기권 1개${cooldown ? ' · 게임권은 적립 대기 중' : ' · 게임권은 최대 3장 보유'}`;
  else if (gameGrant) message = '뽑기 10회 한도에 도달했어요. 공유하면 게임권 1장을 받아요.';
  else message = won ? '실제 상품 당첨으로 추가 뽑기가 완료됐어요.' : '뽑기 10회 한도에 도달했고, 게임권도 현재 적립할 수 없어요.';
  return { active, drawGrant, gameGrant, drawReady, gameReady, message };
}

export function benefitRewardMessage(receipt) {
  const game = receipt?.rewards?.game?.quantity === 1 || (receipt?.reward_type === 'GAME' && receipt?.reward_status === 'granted');
  const draw = receipt?.rewards?.draw?.quantity === 1 || (receipt?.reward_type === 'DRAW' && receipt?.reward_status === 'granted');
  if (game && draw) return '뽑기권 1개와 게임권 1장을 받았어요!';
  if (draw) return '뽑기권 1개를 받았어요! 게임권은 보유 한도·적립 대기 규칙이 적용돼요.';
  if (game) return '게임권 1장을 받았어요! 뽑기는 최대 10회까지예요.';
  if (receipt?.status === 'rejected') return '친구나 단톡방에 전송해야 재도전권을 받을 수 있어요.';
  if (receipt?.status === 'expired') return '전송 확인 시간이 지났어요. 다시 공유해 주세요.';
  return '전송은 확인됐지만 현재 추가 보상을 받을 수 없어요.';
}
