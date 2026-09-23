const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const sourcePath = path.resolve(__dirname, '../public/js/game/gate_runner.js');
const appSourcePath = path.resolve(__dirname, '../public/js/app.js');
const paletteKeys = ['top', 'bottom', 'far', 'mid', 'land', 'water', 'road', 'end', 'light', 'accent'];

function createEventTarget(extra = {}) {
  const listeners = new Map();
  return Object.assign({
    hidden: false,
    style: {},
    dataset: {},
    textContent: '',
    clientWidth: 440,
    clientHeight: 720,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(listener);
    },
    dispatch(type, event = {}) {
      for (const listener of listeners.get(type) || []) {
        listener({ preventDefault() {}, ...event, type, target: this });
      }
    },
    setAttribute(name, value) { this[name] = String(value); },
    getAttribute(name) { return this[name]; },
    focus() { this.focused = true; },
    getBoundingClientRect() { return { left: 0, width: this.clientWidth }; },
    setPointerCapture() {},
  }, extra);
}

function createCanvasContext() {
  const gradient = { addColorStop() {} };
  const operations = [];
  const paint = {
    fillStyle: undefined,
    strokeStyle: undefined,
    font: undefined,
    textAlign: undefined,
    textBaseline: undefined,
    lineWidth: undefined,
  };
  const methods = [
    'arc', 'beginPath', 'bezierCurveTo', 'clearRect', 'closePath', 'drawImage',
    'ellipse', 'fill', 'fillRect', 'fillText', 'lineTo', 'moveTo', 'putImageData',
    'quadraticCurveTo', 'restore', 'rotate', 'save', 'scale', 'setLineDash',
    'stroke', 'strokeText', 'translate',
  ];
  const context = {
    operations,
    resetOperations() { operations.length = 0; },
    createLinearGradient() { return gradient; },
    createRadialGradient() { return gradient; },
    getImageData(x, y, width, height) {
      return { data: new Uint8ClampedArray(width * height * 4) };
    },
    measureText(text) { return { width: String(text).length * 8 }; },
  };
  for (const property of Object.keys(paint)) {
    Object.defineProperty(context, property, {
      get() { return paint[property]; },
      set(value) { paint[property] = value; },
    });
  }
  for (const method of methods) {
    context[method] = (...args) => {
      if (['fill', 'stroke', 'fillText', 'strokeText'].includes(method)) {
        operations.push({ method, args, ...paint });
      }
    };
  }
  return context;
}

function loadGame() {
  const elements = new Map();
  const ctx = createCanvasContext();
  const makeCanvas = () => createEventTarget({
    width: 440,
    height: 720,
    getContext() { return ctx; },
  });
  const ids = [
    'runner-canvas', 'viewport', 'army-count-text', 'stage-badge', 'hint-banner',
    'stage-toast', 'toast-text', 'result-modal', 'btn-restart', 'pause-screen',
    'btn-pause', 'btn-resume', 'btn-start', 'start-screen', 'btn-sound',
    'res-emoji', 'res-title', 'res-subtitle', 'res-final-count', 'res-stage-val',
    'stage-progress', 'distance-text', 'environment-name', 'btn-left', 'btn-right',
  ];
  for (const id of ids) elements.set(id, id === 'runner-canvas' ? makeCanvas() : createEventTarget());
  elements.get('viewport').clientWidth = 440;
  elements.get('viewport').clientHeight = 720;

  const document = createEventTarget({
    hidden: false,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, createEventTarget());
      return elements.get(id);
    },
    createElement(tag) { return tag === 'canvas' ? makeCanvas() : createEventTarget(); },
  });
  const window = createEventTarget({
    devicePixelRatio: 1,
    matchMedia() { return { matches: false }; },
    AudioContext: undefined,
    webkitAudioContext: undefined,
  });

  class FakeImage {
    constructor() {
      this.width = 320;
      this.height = 320;
      this.naturalWidth = 320;
      this.naturalHeight = 320;
      this.src = '';
    }
  }

  const context = vm.createContext({
    console,
    document,
    window,
    navigator: { vibrate() {} },
    Image: FakeImage,
    Path2D: class Path2D {},
    ResizeObserver: class ResizeObserver { observe() {} },
    Uint8Array,
    Uint8ClampedArray,
    Int32Array,
    Math,
    performance: { now: () => 1000 },
    requestAnimationFrame() { return 1; },
    cancelAnimationFrame() {},
    setTimeout,
    clearTimeout,
  });
  context.globalThis = context;

  const exposure = `
      globalThis.__gateRunnerTest = {
        STAGE_CONFIGS,
        ENVIRONMENTS,
        getEnvironment,
        initStage,
        evaluateGateCount: typeof evaluateGateCount === 'function' ? evaluateGateCount : undefined,
        getGateChoices: typeof getGateChoices === 'function' ? getGateChoices : undefined,
        updateGateMotion: typeof updateGateMotion === 'function' ? updateGateMotion : undefined,
        updateEnemyMotion: typeof updateEnemyMotion === 'function' ? updateEnemyMotion : undefined,
        applyGate,
        handleEnemyBattle,
        handleStageClear,
        setPaused,
        update,
        updateArmyOffsets,
        updateArmyMotion: typeof updateArmyMotion === 'function' ? updateArmyMotion : undefined,
        drawGateHalf,
        resize,
        draw,
        drawSky,
        drawSoftClouds,
        drawLandscape,
        drawRoadsideProps,
        get state() { return state; },
        set state(value) { state = value; },
        get currentStageIndex() { return currentStageIndex; },
        get stageClearRemaining() { return stageClearRemaining; },
        get distance() { return distance; },
        set distance(value) { distance = value; },
        get playerTargetX() { return playerTargetX; },
        set playerTargetX(value) { playerTargetX = value; },
        get playerArmy() { return playerArmy; },
        get activeGates() { return activeGates; },
        get activeEnemies() { return activeEnemies; },
        setPlayerCount(count) {
          playerArmy = Array.from({ length: count }, (_, index) => ({
            type: 'dino',
            offsetX: 0,
            offsetY: 0,
            followX: 0,
            animSeed: index / 10,
            spawnProgress: 0
          }));
          updateArmyOffsets();
        }
      };
  `;
  const source = fs.readFileSync(sourcePath, 'utf8');
  const closeIndex = source.lastIndexOf('})();');
  assert.notEqual(closeIndex, -1, 'game IIFE closure must be present');
  const instrumented = source.slice(0, closeIndex) + exposure + source.slice(closeIndex);
  vm.runInContext(instrumented, context, { filename: sourcePath });

  return { api: context.__gateRunnerTest, ctx, document, elements, window };
}

function loadAppRouter(search) {
  const navigations = [];
  const elements = new Map();
  const document = createEventTarget({
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, createEventTarget({ classList: { add() {}, remove() {} } }));
      return elements.get(id);
    },
    querySelectorAll() { return []; },
  });
  const view = { render() {} };
  const context = vm.createContext({
    api: {
      async initParticipant() {},
      async getMe() { return { tickets: 1, best_score: 0, pending_draw: null }; },
    },
    ui: { showToast() {} },
    HomeView: view,
    GameView: view,
    ResultView: view,
    DrawView: view,
    PrizeView: view,
    RankingView: view,
    InviteView: view,
    BenefitView: view,
    document,
    window: { location: { search }, scrollTo() {} },
    URLSearchParams,
    performance: { now: () => 0 },
    setInterval,
    clearInterval,
    console,
  });
  context.globalThis = context;
  let source = fs.readFileSync(appSourcePath, 'utf8').replace(/^import .*;\n/gm, '');
  source = source.slice(0, source.indexOf('// Bootstrap on DOM ready'));
  source += '\nglobalThis.__AppRouter = AppRouter;';
  vm.runInContext(source, context, { filename: appSourcePath });
  const router = new context.__AppRouter();
  router.runSplashScreen = async () => {};
  router.hideSplashScreen = () => {};
  router.navigate = viewName => navigations.push(viewName);
  return { router, navigations };
}

function plainEnemy(count, isBoss = false) {
  return {
    currentCount: count,
    totalCount: count,
    destroyed: false,
    isBoss,
    label: 'test enemy',
    x: 0,
    dist: 0,
  };
}

function applyOptimalGate(api, gate) {
  const before = api.playerArmy.length;
  const choices = api.getGateChoices(gate);
  const leftCount = api.evaluateGateCount(before, choices.left);
  const rightCount = api.evaluateGateCount(before, choices.right);
  api.applyGate(gate, leftCount >= rightCount ? choices.left : choices.right, 0, 0);
}

test('gate arithmetic supports fixed and chained variants and clamps the army from 0 to 500', () => {
  const { api } = loadGame();
  const gate = { punch: 1 };
  assert.equal(typeof api.evaluateGateCount, 'function');
  api.setPlayerCount(10);

  api.applyGate(gate, { op: 'add', val: 5, isGood: true }, 0, 0);
  assert.equal(api.playerArmy.length, 15);
  api.applyGate(gate, { op: 'mul', val: 2, isGood: true }, 0, 0);
  assert.equal(api.playerArmy.length, 30);
  api.applyGate(gate, { op: 'sub', val: 7, isGood: false }, 0, 0);
  assert.equal(api.playerArmy.length, 23);
  api.applyGate(gate, { op: 'div', val: 2, isGood: false }, 0, 0);
  assert.equal(api.playerArmy.length, 11);
  api.applyGate(gate, { op: 'mul', val: 100, isGood: true }, 0, 0);
  assert.equal(api.playerArmy.length, 500);

  assert.equal(api.evaluateGateCount(73, { op: 'set', val: 14 }), 14);
  assert.equal(api.evaluateGateCount(8, {
    op: 'chain',
    steps: [{ op: 'mul', val: 2.5 }, { op: 'sub', val: 3 }],
  }), 17);
  assert.equal(api.evaluateGateCount(20, { op: 'sub', val: 100 }), 0);
  assert.equal(api.evaluateGateCount(400, { op: 'mul', val: 3 }), 500);
});

test('game starts ready and supports manual and visibility pause/resume', () => {
  const { api, document, elements } = loadGame();
  assert.equal(api.state, 'ready');

  elements.get('btn-start').dispatch('click');
  assert.equal(api.state, 'playing');
  elements.get('btn-pause').dispatch('click');
  assert.equal(api.state, 'paused');
  elements.get('btn-resume').dispatch('click');
  assert.equal(api.state, 'playing');

  document.hidden = true;
  document.dispatch('visibilitychange');
  assert.equal(api.state, 'paused');
  elements.get('btn-resume').dispatch('click');
  assert.equal(api.state, 'playing');
});

test('fractional battle damage is equivalent at 30, 60, and 120 updates per second', () => {
  for (const fps of [30, 60, 120]) {
    const { api } = loadGame();
    api.setPlayerCount(100);
    const enemy = plainEnemy(100);
    for (let frame = 0; frame < fps; frame++) api.handleEnemyBattle(enemy, 1 / fps);
    assert.equal(enemy.currentCount, 82, `${fps}fps enemy loss`);
    assert.equal(api.playerArmy.length, 82, `${fps}fps player loss`);
  }
});

test('lethal combat shows game over and restart resets stage and army', () => {
  const { api, elements } = loadGame();
  api.state = 'playing';
  api.setPlayerCount(3);
  const enemy = plainEnemy(4);

  api.handleEnemyBattle(enemy, 1);
  assert.equal(api.state, 'gameover');
  assert.equal(api.playerArmy.length, 0);
  assert.equal(enemy.currentCount, 1);
  assert.equal(elements.get('result-modal').style.display, 'flex');

  elements.get('btn-restart').dispatch('click');
  assert.equal(api.state, 'playing');
  assert.equal(api.currentStageIndex, 0);
  assert.equal(api.playerArmy.length, 1);
  assert.equal(elements.get('result-modal').style.display, 'none');
});

test('live stages include deceptive losses, fixed totals, chained arithmetic, and -100 events', () => {
  const { api } = loadGame();
  const gates = api.STAGE_CONFIGS.flatMap(stage => stage.gates);
  const options = gates.flatMap(gate => [gate.left, gate.right]);

  assert.ok(options.some(option => option.op === 'set'));
  assert.ok(options.some(option => option.op === 'chain'));
  assert.ok(options.some(option => option.op === 'sub' && option.val === 100));
  assert.ok(gates.some(gate =>
    api.evaluateGateCount(20, gate.left) < 20 &&
    api.evaluateGateCount(20, gate.right) < 20
  ), 'at least one gate should make both options costly');

  assert.equal(api.evaluateGateCount(210, { op: 'sub', val: 100 }), 110);
  assert.equal(api.evaluateGateCount(210, { op: 'div', val: 2 }), 105);
  assert.equal(api.evaluateGateCount(120, { op: 'div', val: 2 }), 60);
  assert.equal(api.evaluateGateCount(120, { op: 'sub', val: 150 }), 0);
});

test('all five harder stages remain winnable but optimal direct fights finish with small armies', () => {
  const { api } = loadGame();
  api.initStage(0, null);
  const expectedSurvivors = [5, 6, 60, 125, 5];

  for (let stageIndex = 0; stageIndex < api.STAGE_CONFIGS.length; stageIndex++) {
    if (stageIndex > 0) api.initStage(stageIndex, api.playerArmy);
    for (let index = 0; index < api.activeGates.length; index++) {
      const gate = api.activeGates[index];
      applyOptimalGate(api, gate);
      api.handleEnemyBattle(api.activeEnemies[index], 10);
      assert.equal(api.state, 'playing', `survives stage ${stageIndex + 1}, fight ${index + 1}`);
      assert.equal(api.activeEnemies[index].destroyed, true, `wins stage ${stageIndex + 1}, fight ${index + 1}`);
    }
    assert.equal(api.playerArmy.length, expectedSurvivors[stageIndex], `stage ${stageIndex + 1} survivor count`);
  }
  assert.equal(api.playerArmy.length, 5);
});

test('blindly choosing the same displayed side cannot clear the full campaign', () => {
  const { api } = loadGame();
  api.initStage(0, null);

  for (let stageIndex = 0; stageIndex < api.STAGE_CONFIGS.length && api.state === 'playing'; stageIndex++) {
    if (stageIndex > 0) api.initStage(stageIndex, api.playerArmy);
    for (let index = 0; index < api.activeGates.length && api.state === 'playing'; index++) {
      const choice = api.getGateChoices(api.activeGates[index]).left;
      api.applyGate(api.activeGates[index], choice, 0, 0);
      if (api.state === 'playing') api.handleEnemyBattle(api.activeEnemies[index], 10);
    }
  }

  assert.equal(api.state, 'gameover', `blind-left route survived with ${api.playerArmy.length} units`);
});

test('a 60fps controller can clear the complete live campaign using only displayed choices', () => {
  const { api } = loadGame();
  api.initStage(0, null);
  const dt = 1 / 60;

  for (let frame = 0; frame < 30000 && !['won', 'gameover'].includes(api.state); frame++) {
    if (api.state === 'playing') {
      const gate = api.activeGates
        .filter(candidate => !candidate.passed && candidate.dist >= api.distance - 25)
        .sort((a, b) => a.dist - b.dist)[0];
      if (gate && gate.dist - api.distance < 720) {
        const choices = api.getGateChoices(gate);
        const count = api.playerArmy.length;
        const leftCount = api.evaluateGateCount(count, choices.left);
        const rightCount = api.evaluateGateCount(count, choices.right);
        api.playerTargetX = leftCount > rightCount ? -0.52 : 0.52;
      }
    }
    api.update(dt);
  }

  assert.equal(api.state, 'won');
  assert.equal(api.currentStageIndex, api.STAGE_CONFIGS.length - 1);
  assert.ok(api.playerArmy.length > 0 && api.playerArmy.length <= 500);
});

test('parking on either lane fails in the actual 60fps campaign', () => {
  for (const parkedX of [-0.52, 0.52]) {
    const { api } = loadGame();
    api.initStage(0, null);

    for (let frame = 0; frame < 30000 && !['won', 'gameover'].includes(api.state); frame++) {
      if (api.state === 'playing') api.playerTargetX = parkedX;
      api.update(1 / 60);
    }

    const lane = parkedX < 0 ? 'left' : 'right';
    assert.equal(
      api.state,
      'gameover',
      `${lane}-parked route survived stage ${api.currentStageIndex + 1} with ${api.playerArmy.length} units`
    );
  }
});

test('stage-clear countdown stops while paused and resumes into the next stage', () => {
  const { api } = loadGame();
  api.initStage(0, null);
  api.handleStageClear();
  assert.equal(api.state, 'stage_cleared');
  assert.equal(api.stageClearRemaining, 1.6);

  api.update(0.6);
  assert.ok(Math.abs(api.stageClearRemaining - 1) < 1e-9);
  api.setPaused(true);
  api.update(10);
  assert.ok(Math.abs(api.stageClearRemaining - 1) < 1e-9);
  assert.equal(api.currentStageIndex, 0);

  api.setPaused(false);
  api.update(1.01);
  assert.equal(api.currentStageIndex, 1);
  assert.equal(api.state, 'playing');
});

test('an enemy at relative distance 24.5 does not stall forward progress', () => {
  const { api } = loadGame();
  api.initStage(0, null);
  api.distance = 100;
  const enemy = api.activeEnemies[0];
  enemy.dist = 124.5;
  enemy.speed = 0;

  api.update(0.1);
  assert.ok(api.distance > 100);
});

test('stage forward speeds increase and drive actual movement', () => {
  const { api } = loadGame();
  const expected = [155, 195, 245, 300, 360];
  assert.deepEqual(Array.from(api.STAGE_CONFIGS, stage => stage.forwardSpeed), expected);

  for (let stage = 0; stage < expected.length; stage++) {
    api.initStage(stage, null);
    api.activeGates.splice(0);
    api.activeEnemies.splice(0);
    api.distance = 0;
    api.update(1 / 30);
    assert.ok(Math.abs(api.distance - expected[stage] / 30) < 1e-9, `stage ${stage + 1} movement`);
  }
});

test('fast stage movement does not skip nearby gates or enemy encounters at 30fps', () => {
  const { api } = loadGame();
  api.initStage(4, null);
  api.setPlayerCount(10);
  api.activeEnemies.splice(0);
  api.activeGates.splice(1);
  api.activeGates[0].dist = 5;
  api.distance = 0;

  api.update(1 / 30);
  assert.equal(api.activeGates[0].passed, true);

  api.initStage(4, null);
  api.setPlayerCount(10);
  api.activeGates.splice(0);
  api.activeEnemies.splice(1);
  Object.assign(api.activeEnemies[0], {
    dist: 30,
    initialDist: 30,
    speed: 0,
    x: 0,
    widthSpan: 1,
    totalCount: 1,
    currentCount: 1,
    destroyed: false,
  });
  api.distance = 0;
  api.update(1 / 30);
  api.update(1 / 30);
  assert.equal(api.activeEnemies[0].destroyed, true);
});

test('swap gates alternate displayed choices, freeze near the player, and apply the displayed side', () => {
  const { api } = loadGame();
  api.initStage(1, null);
  const gate = api.activeGates.find(candidate => candidate.swapPeriod > 0);
  assert.ok(gate);
  const initial = api.getGateChoices(gate);

  api.distance = gate.dist - 500;
  api.updateGateMotion(gate, gate.swapPeriod + 0.01);
  const swapped = api.getGateChoices(gate);
  assert.equal(swapped.left.op, initial.right.op);
  assert.equal(swapped.left.val, initial.right.val);
  assert.equal(swapped.right.op, initial.left.op);

  api.distance = gate.dist - 200;
  const frozenPhase = gate.phase;
  api.updateGateMotion(gate, 20);
  assert.equal(gate.locked, true);
  assert.equal(gate.phase, frozenPhase);

  api.activeGates.splice(0, api.activeGates.length, gate);
  api.activeEnemies.splice(0);
  api.setPlayerCount(10);
  api.distance = gate.dist - 5;
  const expected = api.evaluateGateCount(10, api.getGateChoices(gate).right);
  api.update(1 / 30);
  assert.equal(gate.passed, true);
  assert.equal(api.playerArmy.length, expected);
});

test('swap timers do not advance while paused', () => {
  const { api } = loadGame();
  api.initStage(3, null);
  const gate = api.activeGates.find(candidate => candidate.swapPeriod > 0);
  api.distance = gate.dist - 500;
  api.setPaused(true);
  const before = gate.phase;
  api.update(gate.swapPeriod * 2);
  assert.equal(gate.phase, before);
});

test('Claude units patrol freely within bounds, pause cleanly, and lock their lane near contact', () => {
  const { api } = loadGame();
  api.initStage(2, null);
  const enemy = api.activeEnemies[0];
  api.distance = enemy.dist - 400;
  const startX = enemy.x;

  for (let i = 0; i < 120; i++) api.updateEnemyMotion(enemy, 1 / 60);
  assert.notEqual(enemy.x, startX);
  assert.ok(enemy.x >= -0.62 && enemy.x <= 0.62);
  assert.ok(['patrol', 'pursuit'].includes(enemy.motionMode));

  api.setPaused(true);
  const paused = [enemy.x, enemy.motionPhase, enemy.motionTargetX];
  api.update(1);
  assert.deepEqual([enemy.x, enemy.motionPhase, enemy.motionTargetX], paused);
  api.setPaused(false);

  api.distance = enemy.dist - 30;
  const contact = [enemy.x, enemy.motionPhase];
  api.updateEnemyMotion(enemy, 2);
  assert.equal(enemy.motionMode, 'contact');
  assert.deepEqual([enemy.x, enemy.motionPhase], contact);
});

test('all gate choices use the same neutral treatment and neutral guidance text', () => {
  const { api, ctx } = loadGame();
  const render = data => {
    ctx.resetOperations();
    api.drawGateHalf(10, 20, 120, 150, data, 1, 100);
    return ctx.operations.map(operation => ({
      method: operation.method,
      text: operation.method.endsWith('Text') ? operation.args[0] : undefined,
      fillStyle: operation.fillStyle,
      strokeStyle: operation.strokeStyle,
      font: operation.font,
      lineWidth: operation.lineWidth,
    }));
  };
  const bonus = render({ op: 'add', val: 25, isGood: true });
  const penalty = render({ op: 'div', val: 2, isGood: false });
  const neutralText = operations => operations
    .filter(operation => operation.method === 'fillText')
    .map(operation => operation.text);
  const paintSignature = operations => operations.map(operation => {
    if (operation.method === 'fill') {
      return { method: operation.method, fillStyle: operation.fillStyle };
    }
    if (operation.method === 'stroke') {
      return { method: operation.method, strokeStyle: operation.strokeStyle, lineWidth: operation.lineWidth };
    }
    return {
      method: operation.method,
      fillStyle: operation.fillStyle,
      font: operation.font,
    };
  });

  assert.deepEqual(neutralText(bonus), ['GATE', '+25', '공룡 수 계산']);
  assert.deepEqual(neutralText(penalty), ['GATE', '÷2', '공룡 수 계산']);
  assert.deepEqual(paintSignature(bonus), paintSignature(penalty));
});

test('variant gates explain their mechanics without changing the neutral palette', () => {
  const { api, ctx } = loadGame();
  const render = data => {
    ctx.resetOperations();
    api.drawGateHalf(10, 20, 120, 150, data, 1, 100);
    return ctx.operations.map(operation => ({ ...operation, args: [...operation.args] }));
  };
  const chain = render({ op: 'chain', steps: [{ op: 'mul', val: 2 }, { op: 'sub', val: 3 }] });
  const fixed = render({ op: 'set', val: 14 });
  const texts = operations => operations
    .filter(operation => operation.method === 'fillText')
    .map(operation => operation.args[0]);
  const palette = operations => operations.map(operation => operation.method === 'stroke'
    ? { method: operation.method, color: operation.strokeStyle }
    : { method: operation.method, color: operation.fillStyle });

  assert.deepEqual(texts(chain), ['연속 계산', '×2 −3', '왼쪽부터 차례로']);
  assert.deepEqual(texts(fixed), ['인원 고정', '→14', '현재 인원과 교체']);
  assert.deepEqual(palette(chain), palette(fixed));
});

test('army formation assigns targets for at most 81 visible units without snapping positions', () => {
  const { api } = loadGame();
  api.setPlayerCount(500);

  for (const unit of api.playerArmy.slice(0, 81)) {
    assert.equal(Number.isFinite(unit.targetOffsetX), true);
    assert.equal(Number.isFinite(unit.targetOffsetY), true);
    assert.equal(Number.isFinite(unit.offsetX), true);
    assert.equal(Number.isFinite(unit.offsetY), true);
    assert.equal(unit.offsetX, 0);
    assert.equal(unit.offsetY, 0);
  }
  for (const unit of api.playerArmy.slice(81)) {
    assert.equal(unit.targetOffsetX, undefined);
    assert.equal(unit.targetOffsetY, undefined);
  }
});

test('individual dinosaurs ease from the centre into a bounded free-moving flock', () => {
  const { api } = loadGame();
  api.setPlayerCount(81);
  const before = api.playerArmy.map(unit => ({ x: unit.offsetX, y: unit.offsetY }));

  api.updateArmyMotion(0.2);
  const after = api.playerArmy.map(unit => ({ x: unit.offsetX, y: unit.offsetY }));
  assert.ok(after.some((unit, index) => unit.x !== before[index].x || unit.y !== before[index].y));
  assert.ok(new Set(after.map(unit => `${unit.x.toFixed(3)},${unit.y.toFixed(3)}`)).size > 60);
  for (const unit of api.playerArmy) {
    assert.equal(Number.isFinite(unit.offsetX), true);
    assert.equal(Number.isFinite(unit.offsetY), true);
    assert.equal(Number.isFinite(unit.followX), true);
    assert.equal(Number.isFinite(unit.animSeed), true);
    assert.ok(Math.abs(unit.offsetX) <= 114);
    assert.ok(unit.offsetY >= -5 && unit.offsetY <= 128);
    assert.ok(unit.spawnProgress > 0 && unit.spawnProgress <= 1);
  }

  api.state = 'paused';
  const paused = api.playerArmy.map(unit => [unit.offsetX, unit.offsetY, unit.followX, unit.spawnProgress]);
  api.update(1);
  assert.deepEqual(api.playerArmy.map(unit => [unit.offsetX, unit.offsetY, unit.followX, unit.spawnProgress]), paused);
});

test('new recruits spawn at the centre and spread into their assigned flock positions', () => {
  const { api } = loadGame();
  api.setPlayerCount(1);
  api.applyGate({ punch: 1 }, { op: 'add', val: 4, isGood: true }, 0, 0);
  const recruits = api.playerArmy.slice(1);

  assert.equal(recruits.length, 4);
  for (const unit of recruits) {
    assert.equal(unit.offsetX, 0);
    assert.equal(unit.offsetY, 0);
    assert.equal(unit.spawnProgress, 0);
    assert.equal(Number.isFinite(unit.targetOffsetX), true);
    assert.equal(Number.isFinite(unit.targetOffsetY), true);
    assert.equal(Number.isFinite(unit.followX), true);
    assert.equal(Number.isFinite(unit.animSeed), true);
  }

  api.updateArmyMotion(0.2);
  assert.ok(recruits.some(unit => unit.offsetX !== 0 || unit.offsetY !== 0));
  assert.ok(recruits.every(unit => unit.spawnProgress > 0));
});

test('environment palettes interpolate finitely and join adjacent stages exactly', () => {
  const { api } = loadGame();
  assert.equal(api.ENVIRONMENTS.length, 5);
  assert.equal(api.getEnvironment(0, 0).night, 0);
  assert.equal(api.getEnvironment(4, 1).night, 1);

  for (let stage = 0; stage < api.ENVIRONMENTS.length; stage++) {
    for (const progress of [0, 0.5, 1]) {
      const env = api.getEnvironment(stage, progress);
      assert.equal(Number.isFinite(env.night), true);
      assert.ok(env.night >= 0 && env.night <= 1);
      for (const key of paletteKeys) {
        const match = /^rgb\((\d+),(\d+),(\d+)\)$/.exec(env[key]);
        assert.ok(match, `stage ${stage + 1} ${key} is an rgb color`);
        for (const channel of match.slice(1).map(Number)) {
          assert.equal(Number.isFinite(channel), true);
          assert.ok(channel >= 0 && channel <= 255);
        }
      }
    }
    if (stage < api.ENVIRONMENTS.length - 1) {
      const end = api.getEnvironment(stage, 1);
      const nextStart = api.getEnvironment(stage + 1, 0);
      assert.equal(end.night, nextStart.night);
      for (const key of paletteKeys) assert.equal(end[key], nextStart[key]);
    }
  }
});

test('all five environments render at start, midpoint, and end on narrow canvases', () => {
  const { api, elements } = loadGame();
  const viewport = elements.get('viewport');

  for (const canvasWidth of [320, 390]) {
    viewport.clientWidth = canvasWidth;
    viewport.clientHeight = 640;
    api.resize();
    for (let stage = 0; stage < api.STAGE_CONFIGS.length; stage++) {
      api.initStage(stage, null);
      api.setPlayerCount(81);
      for (const progress of [0, 0.5, 1]) {
        api.distance = api.STAGE_CONFIGS[stage].trackLength * progress;
        assert.doesNotThrow(() => api.draw(), `${canvasWidth}px stage ${stage + 1} at ${progress}`);
      }
    }
  }
});

test('stage initialization displays the matching environment name', () => {
  const { api, elements } = loadGame();
  for (let stage = 0; stage < api.ENVIRONMENTS.length; stage++) {
    api.initStage(stage, null);
    assert.equal(elements.get('environment-name').textContent, api.ENVIRONMENTS[stage].name);
  }
});

test('direction controls hold, release, cancel, pause, and keyboard clicks correctly', () => {
  const { api, elements } = loadGame();
  const left = elements.get('btn-left');
  const right = elements.get('btn-right');
  api.initStage(0, null);

  right.dispatch('pointerdown', { pointerId: 1 });
  api.update(0.25);
  assert.ok(api.playerTargetX > 0);
  right.dispatch('pointerup', { pointerId: 1 });
  const afterRightRelease = api.playerTargetX;
  api.update(0.25);
  assert.equal(api.playerTargetX, afterRightRelease);

  left.dispatch('pointerdown', { pointerId: 2 });
  api.update(0.25);
  assert.ok(api.playerTargetX < afterRightRelease);
  left.dispatch('pointercancel', { pointerId: 2 });
  const afterLeftCancel = api.playerTargetX;
  api.update(0.25);
  assert.equal(api.playerTargetX, afterLeftCancel);

  api.setPaused(true);
  right.dispatch('pointerdown', { pointerId: 3 });
  api.update(1);
  assert.equal(api.playerTargetX, afterLeftCancel);
  api.setPaused(false);

  api.playerTargetX = 0;
  right.dispatch('click', { detail: 0 });
  assert.equal(api.playerTargetX, 0.28);
  left.dispatch('click', { detail: 0 });
  assert.equal(api.playerTargetX, 0);
});

test('AppRouter accepts safe entry views and rejects arbitrary query routes', async () => {
  const safe = loadAppRouter('?view=ranking');
  await safe.router.init();
  assert.equal(safe.navigations.at(-1), 'ranking');

  const unsafe = loadAppRouter('?view=game');
  await unsafe.router.init();
  assert.equal(unsafe.navigations.at(-1), 'home');
});
