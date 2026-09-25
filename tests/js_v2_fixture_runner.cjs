const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public/js/game/simulation.js'), 'utf8')
  .replace(/export\s+(?=(const|class|function)\s)/g, '');
const context = {};
vm.runInNewContext(`${source}\nglobalThis.V2GameSimulation = V2GameSimulation; globalThis.simulateV2 = simulateV2;`, context);

function runBot(seed, targetRevives = 2) {
  const sim = new context.V2GameSimulation(seed);
  let sacrificeForRevive = false;
  while (!sim.ended) {
    if (sim.heart === 1 && sim.revives < targetRevives) sacrificeForRevive = true;
    const nearbyHeart = sim.items.some((item) => item.kind === 'heart' && item.x > 100 && item.x < 330);
    const threat = sim.obstacles
      .filter((obstacle) => obstacle.type !== 'bird_high' && obstacle.x > 150 && obstacle.x < 300)
      .sort((left, right) => left.x - right.x)[0];
    const shouldJump = sim.isGrounded && !sacrificeForRevive && !nearbyHeart && Boolean(threat);
    const beforeRevives = sim.revives;
    sim.step({ jump: shouldJump, high: true });
    if (sim.revives > beforeRevives) sacrificeForRevive = false;
  }
  return sim.result();
}

const request = JSON.parse(process.argv[2] || '{}');
const result = request.mode === 'bot'
  ? runBot(request.seed, request.target_revives)
  : context.simulateV2(request.seed, request.jumps || [], request.until_ticks);
process.stdout.write(JSON.stringify(result));
