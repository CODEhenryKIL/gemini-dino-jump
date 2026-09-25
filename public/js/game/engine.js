/**
 * Deterministic Canvas 2D Game Engine for Team Gemini Dino Jump (v1.2)
 * Features:
 * - 2-Stage Jump (Low Jump -680, High Jump -720 boost at 100ms hold)
 * - Chrome Dino Authentic Obstacles: Small/Tall/Double Cacti & High/Low Pterodactyls
 * - Fast initial start (390 px/s) & 1.2s first obstacle delay
 * - 60 tick/s deterministic simulation synchronized with server verifier
 */

import { audio } from './audio.js';
import { V2GameSimulation, V2_RULES } from './simulation.js';

class PRNG {
  constructor(seed) {
    this.state = seed >>> 0;
  }
  nextFloat() {
    this.state = (Math.imul(this.state, 1664525) + 1013904223) >>> 0;
    return (this.state >>> 8) / 16777216.0;
  }
}

// Cinematic Day-to-Sunset-to-Night Sky Keyframes
const TIME_KEYFRAMES = [
  {
    time: 0,
    skyTop: [225, 238, 255],     // Fresh bright daylight
    skyBottom: [255, 255, 255],
    sunX: 740, sunY: 90, sunR: 44,
    sunColor: '#FBBC04',
    sunGlow: 'rgba(255, 235, 150, 0.45)',
    moonX: 810, moonY: 650, moonAlpha: 0,
    starAlpha: 0,
    groundColor: '#1967D2',
    dashColor: 'rgba(25, 103, 210, 0.35)',
    gridColor: 'rgba(25, 103, 210, 0.04)',
    dinoGlow: 0
  },
  {
    time: 15,
    skyTop: [255, 232, 205],     // Late afternoon golden sunlight
    skyBottom: [255, 246, 236],
    sunX: 770, sunY: 170, sunR: 48,
    sunColor: '#F9AB00',
    sunGlow: 'rgba(255, 210, 130, 0.5)',
    moonX: 810, moonY: 650, moonAlpha: 0,
    starAlpha: 0,
    groundColor: '#E37400',
    dashColor: 'rgba(227, 116, 0, 0.35)',
    gridColor: 'rgba(227, 116, 0, 0.04)',
    dinoGlow: 0
  },
  {
    time: 30,
    skyTop: [142, 85, 168],      // Sunset (황금빛/다홍빛 노을)
    skyBottom: [255, 115, 75],
    sunX: 800, sunY: 300, sunR: 56, // Sun touching horizon
    sunColor: '#EA4335',
    sunGlow: 'rgba(255, 138, 101, 0.6)',
    moonX: 810, moonY: 600, moonAlpha: 0,
    starAlpha: 0,
    groundColor: '#AB47BC',
    dashColor: 'rgba(171, 71, 188, 0.4)',
    gridColor: 'rgba(255, 112, 67, 0.05)',
    dinoGlow: 0
  },
  {
    time: 45,
    skyTop: [36, 26, 72],        // Twilight / 황혼 매직아워
    skyBottom: [165, 62, 112],
    sunX: 820, sunY: 530, sunR: 56, // Sun sinking below ground
    sunColor: '#D93025',
    sunGlow: 'rgba(234, 67, 53, 0.2)',
    moonX: 810, moonY: 300, moonAlpha: 0.6, // Moon rising
    starAlpha: 0.45,
    groundColor: '#7E57C2',
    dashColor: 'rgba(126, 87, 194, 0.45)',
    gridColor: 'rgba(126, 87, 194, 0.05)',
    dinoGlow: 6
  },
  {
    time: 60,
    skyTop: [12, 20, 48],        // Starry Night / 밤
    skyBottom: [28, 38, 70],
    sunX: 820, sunY: 750, sunR: 50,
    sunColor: 'transparent',
    sunGlow: 'transparent',
    moonX: 810, moonY: 140, moonAlpha: 0.95,
    starAlpha: 0.85,
    groundColor: '#4285F4',
    dashColor: 'rgba(66, 133, 244, 0.45)',
    gridColor: 'rgba(66, 133, 244, 0.06)',
    dinoGlow: 10
  },
  {
    time: 75,
    skyTop: [5, 9, 24],          // Deep Midnight / 은하수 깊은 밤
    skyBottom: [15, 23, 44],
    sunX: 820, sunY: 750, sunR: 50,
    sunColor: 'transparent',
    sunGlow: 'transparent',
    moonX: 810, moonY: 100, moonAlpha: 1.0,
    starAlpha: 1.0,
    groundColor: '#8AB4F8',
    dashColor: 'rgba(138, 180, 248, 0.55)',
    gridColor: 'rgba(138, 180, 248, 0.08)',
    dinoGlow: 14
  }
];

export class DinoGameEngine {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');

    this.onScoreUpdate = options.onScoreUpdate || (() => {});
    this.onStageChange = options.onStageChange || (() => {});
    this.onGameOver = options.onGameOver || (() => {});
    this.onCoinCollected = options.onCoinCollected || (() => {});
    this.onHeartChange = options.onHeartChange || (() => {});
    this.onRevive = options.onRevive || (() => {});
    this.gameVersion = options.version || V2_RULES.version;
    this.reducedMotion = options.reducedMotion ?? window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

    // Canonical Logical Dimensions (16:10 ratio)
    this.width = 960;
    this.height = 600;
    this.groundY = 490;

    // Simulation Constants
    this.tickRate = 60;
    this.dt = 1.0 / this.tickRate;
    this.gravity = 2200;
    this.jumpVelocityLow = -680;
    this.jumpVelocityHighBoost = -720;
    this.holdTicks = 6; // 100ms hold threshold for high jump boost

    // Dino State
    this.dinoX = 120;
    this.dinoW = 64;
    this.dinoH = 72;
    this.dinoHitbox = { offsetX: 10, offsetY: 8, width: 44, height: 58 };

    this.dinoY = this.groundY - this.dinoH;
    this.dinoVy = 0;
    this.isGrounded = true;

    // 2-Stage Jump Input State
    this.isHoldingJump = false;
    this.activeJumpTick = null;
    this.activeJumpHigh = false;
    this.jumpBufferedUntil = -1;

    // Game State
    this.isRunning = false;
    this.isPaused = false;
    this.currentTick = 0;
    this.score = 0;
    this.currentStage = 1;
    this.jumpTicks = []; // Array of { tick, high }

    this.obstacles = [];
    this.nextSpawnTime = 1.2; // 1.2s snappy first obstacle

    // Stages from game_constants.json (Day to Sunset to Starry Night Journey)
    this.stages = [
      { stage: 1, start: 0, end: 15, spd1: 390, spd2: 450, minGap: 0.95, title: "STAGE 1", sub: "상쾌한 낮, 가볍게 출발!" },
      { stage: 2, start: 15, end: 30, spd1: 450, spd2: 530, minGap: 0.88, title: "STAGE 2", sub: "기울어지는 오후 햇살" },
      { stage: 3, start: 30, end: 45, spd1: 530, spd2: 620, minGap: 0.80, title: "STAGE 3", sub: "황금빛 노을 & 새 출현!" },
      { stage: 4, start: 45, end: 60, spd1: 620, spd2: 710, minGap: 0.74, title: "STAGE 4", sub: "보랏빛 황혼 매직아워" },
      { stage: 5, start: 60, end: 75, spd1: 710, spd2: 800, minGap: 0.68, title: "STAGE 5", sub: "별빛과 달빛의 밤하늘" },
      { stage: 6, start: 75, end: 999999, spd1: 800, spd2: 880, minGap: 0.62, title: "STAGE 6", sub: "신비로운 제미나이 은하수" }
    ];

    // Obstacle Definitions
    this.obstacleTypes = [
      { type: 'cactus_small', w: 36, h: 48, altitude: 'ground', hb: { offsetX: 6, offsetY: 4, width: 24, height: 42 } },
      { type: 'cactus_tall', w: 44, h: 84, altitude: 'ground', hb: { offsetX: 6, offsetY: 4, width: 32, height: 76 } },
      { type: 'cactus_double', w: 68, h: 64, altitude: 'ground', hb: { offsetX: 6, offsetY: 4, width: 56, height: 56 } },
      { type: 'bird_low', w: 52, h: 40, altitude: 'air_low', offsetFromGround: 85, hb: { offsetX: 4, offsetY: 4, width: 44, height: 32 } },
      { type: 'bird_high', w: 52, h: 40, altitude: 'air_high', offsetFromGround: 140, hb: { offsetX: 4, offsetY: 4, width: 44, height: 32 } }
    ];

    // Visual assets
    this.dinoImg = new Image();
    this.dinoLoaded = false;
    this.dinoImg.onload = () => { this.dinoLoaded = true; };
    this.dinoImg.onerror = () => { this.dinoLoaded = false; };
    this.dinoImg.src = '/assets/icons/Dino-Dark.png';

    this.smileImg = new Image();
    this.smileLoaded = false;
    this.smileImg.onload = () => { this.smileLoaded = true; };
    this.smileImg.onerror = () => { this.smileLoaded = false; };
    this.smileImg.src = '/assets/icons/Smile-Light.png';

    this.heartImg = new Image();
    this.heartLoaded = false;
    this.heartImg.onload = () => { this.heartLoaded = true; };
    this.heartImg.onerror = () => { this.heartLoaded = false; };
    this.heartImg.src = '/assets/icons/Heart-Light.png';

    this.particles = [];
    this.groundOffset = 0;

    // Fixed starry sky field
    this.stars = [];
    for (let i = 0; i < 50; i++) {
      this.stars.push({
        x: Math.random() * this.width,
        y: Math.random() * (this.groundY - 100),
        r: Math.random() * 2.2 + 0.8,
        twinklePhase: Math.random() * Math.PI * 2,
        color: ['#FFFFFF', '#E8F0FE', '#FFF8E1', '#8AB4F8'][Math.floor(Math.random() * 4)]
      });
    }
    this.shootingStars = [];
    this.currentEnv = TIME_KEYFRAMES[0];

    // Loop variables
    this.accumulator = 0;
    this.lastFrameTime = 0;
    this.animId = null;

    this.resizeCanvas();
    this.resizeHandler = () => this.resizeCanvas();
    window.addEventListener('resize', this.resizeHandler);
  }

  resizeCanvas() {
    this.canvas.width = this.width;
    this.canvas.height = this.height;
  }

  start(seed) {
    this.seed = seed;
    this.prng = new PRNG(seed);
    this.simulation = this.gameVersion === V2_RULES.version ? new V2GameSimulation(seed) : null;

    this.isRunning = true;
    this.isPaused = false;
    this.currentTick = 0;
    this.score = 0;
    this.currentStage = 1;
    this.jumpTicks = [];
    this.obstacles = [];
    this.particles = [];
    this.nextSpawnTime = 1.2;

    this.dinoY = this.groundY - this.dinoH;
    this.dinoVy = 0;
    this.isGrounded = true;

    this.isHoldingJump = false;
    this.activeJumpTick = null;
    this.activeJumpHigh = false;
    this.jumpBufferedUntil = -1;

    this.shootingStars = [];
    this.currentEnv = TIME_KEYFRAMES[0];
    this.lastWasCombo = false;
    this.accumulator = 0;
    this.lastFrameTime = performance.now();

    cancelAnimationFrame(this.animId);
    this.loop = this.gameLoop.bind(this);
    this.animId = requestAnimationFrame(this.loop);
  }

  restoreSnapshot(snapshot) {
    const tick = Number(snapshot?.tick);
    const seed = Number(snapshot?.seed);
    const jumps = snapshot?.jumpTicks;
    if (this.gameVersion !== V2_RULES.version || snapshot?.version !== this.gameVersion) throw new Error('지원하지 않는 게임 버전의 복원 데이터입니다.');
    if (!Number.isInteger(seed) || seed < 0 || !Number.isInteger(tick) || tick < 0 || tick >= V2_RULES.maxTicks || !Array.isArray(jumps)) throw new Error('게임 복원 데이터가 올바르지 않습니다.');
    let previousTick = -1;
    const jumpByTick = new Map();
    for (const jump of jumps) {
      const jumpTick = Number(jump?.tick);
      if (!Number.isInteger(jumpTick) || jumpTick < 0 || jumpTick >= tick || jumpTick <= previousTick || typeof jump?.high !== 'boolean') throw new Error('점프 복원 데이터가 올바르지 않습니다.');
      previousTick = jumpTick;
      jumpByTick.set(jumpTick, jump.high);
    }

    this.seed = seed;
    this.prng = new PRNG(seed);
    this.simulation = new V2GameSimulation(seed);
    while (this.simulation.currentTick < tick && !this.simulation.ended) {
      const high = jumpByTick.get(this.simulation.currentTick);
      this.simulation.step(high === undefined ? {} : { jump: true, high });
    }
    if (this.simulation.ended || this.simulation.currentTick !== tick) throw new Error('종료된 게임은 이어할 수 없습니다.');

    this.syncV2State();
    const timeSec = this.currentTick / this.tickRate;
    const stage = this.stages.find((candidate) => timeSec >= candidate.start && timeSec < candidate.end) || this.stages[this.stages.length - 1];
    this.currentStage = stage.stage;
    this.isRunning = false;
    this.isPaused = false;
    this.isHoldingJump = false;
    this.particles = [];
    this.shootingStars = [];
    this.currentEnv = this.getEnvironment(timeSec);
    this.accumulator = 0;
    this.render();
    return {
      score: this.score,
      stage,
      heart: this.simulation.heart,
      summary: this.getSummary(),
    };
  }

  resumeRestored() {
    if (!this.simulation || this.simulation.ended) throw new Error('복원된 게임 상태가 없습니다.');
    this.isRunning = true;
    this.isPaused = false;
    this.lastFrameTime = performance.now();
    cancelAnimationFrame(this.animId);
    this.loop = this.gameLoop.bind(this);
    this.animId = requestAnimationFrame(this.loop);
  }

  getResumeSnapshot() {
    if (!this.simulation || this.simulation.ended) return null;
    return {
      version: this.gameVersion,
      seed: this.seed,
      tick: this.simulation.currentTick,
      jumpTicks: this.simulation.jumpTicks.map((jump) => ({ tick: jump.tick, high: Boolean(jump.high) })),
    };
  }

  getEnvironment(timeSec) {
    if (timeSec <= TIME_KEYFRAMES[0].time) {
      return { ...TIME_KEYFRAMES[0], sunAlpha: 1.0 };
    }
    const lastKf = TIME_KEYFRAMES[TIME_KEYFRAMES.length - 1];
    if (timeSec >= lastKf.time) {
      return { ...lastKf, sunAlpha: 0.0 };
    }

    // Find the two bounding keyframes
    let kf1 = TIME_KEYFRAMES[0];
    let kf2 = TIME_KEYFRAMES[1];
    for (let i = 0; i < TIME_KEYFRAMES.length - 1; i++) {
      if (timeSec >= TIME_KEYFRAMES[i].time && timeSec <= TIME_KEYFRAMES[i + 1].time) {
        kf1 = TIME_KEYFRAMES[i];
        kf2 = TIME_KEYFRAMES[i + 1];
        break;
      }
    }

    const duration = kf2.time - kf1.time;
    const t = Math.max(0, Math.min(1, (timeSec - kf1.time) / duration));

    // Linear interpolation helpers
    const lerpVal = (a, b) => a + (b - a) * t;
    const lerpArr = (a, b) => [
      Math.round(a[0] + (b[0] - a[0]) * t),
      Math.round(a[1] + (b[1] - a[1]) * t),
      Math.round(a[2] + (b[2] - a[2]) * t)
    ];

    const parseHex = (hex) => {
      const clean = hex.replace('#', '');
      const num = parseInt(clean, 16);
      return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
    };

    const c1 = parseHex(kf1.groundColor);
    const c2 = parseHex(kf2.groundColor);
    const groundRgb = lerpArr(c1, c2);

    // Sun alpha fades out as it sets below horizon in stage 4 (45s~56s)
    let sunAlpha = 1.0;
    if (timeSec >= 46) {
      sunAlpha = Math.max(0, 1.0 - (timeSec - 46) / 8);
    }

    return {
      skyTop: lerpArr(kf1.skyTop, kf2.skyTop),
      skyBottom: lerpArr(kf1.skyBottom, kf2.skyBottom),
      sunX: lerpVal(kf1.sunX, kf2.sunX),
      sunY: lerpVal(kf1.sunY, kf2.sunY),
      sunR: lerpVal(kf1.sunR, kf2.sunR),
      sunColor: kf1.sunColor === 'transparent' ? kf2.sunColor : kf1.sunColor,
      sunGlow: kf1.sunGlow === 'transparent' ? kf2.sunGlow : kf1.sunGlow,
      sunAlpha,
      moonX: lerpVal(kf1.moonX, kf2.moonX),
      moonY: lerpVal(kf1.moonY, kf2.moonY),
      moonAlpha: lerpVal(kf1.moonAlpha, kf2.moonAlpha),
      starAlpha: lerpVal(kf1.starAlpha, kf2.starAlpha),
      groundColor: `rgb(${groundRgb.join(',')})`,
      dashColor: kf2.dashColor,
      gridColor: kf2.gridColor,
      dinoGlow: lerpVal(kf1.dinoGlow, kf2.dinoGlow)
    };
  }

  pause() {
    this.isPaused = true;
  }

  resume() {
    this.isPaused = false;
    this.lastFrameTime = performance.now();
    cancelAnimationFrame(this.animId);
    this.animId = requestAnimationFrame(this.loop);
  }

  stop() {
    this.isRunning = false;
    cancelAnimationFrame(this.animId);
    if (this.resizeHandler) {
      window.removeEventListener('resize', this.resizeHandler);
      this.resizeHandler = null;
    }
  }

  /**
   * Jump button pressed (down event: touchstart / mousedown / keydown)
   */
  jumpPress() {
    if (!this.isRunning || this.isPaused) return;

    this.isHoldingJump = true;

    if (this.simulation) {
      const jumped = this.simulation.pressJump(false);
      this.syncV2State();
      if (jumped) {
        audio.playJump();
        this.spawnDust(this.dinoX + 20, this.groundY);
      }
      return;
    }

    if (this.isGrounded) {
      this.dinoVy = this.jumpVelocityLow;
      this.isGrounded = false;
      this.activeJumpTick = this.currentTick;
      this.activeJumpHigh = false;
      this.jumpBufferedUntil = -1;

      audio.playJump();
      this.spawnDust(this.dinoX + 20, this.groundY);
    } else {
      // Buffer jump if pressed near ground (within 6 ticks / 100ms)
      this.jumpBufferedUntil = this.currentTick + 6;
    }
  }

  /**
   * Jump button released (up event: touchend / mouseup / keyup)
   */
  jumpRelease() {
    this.isHoldingJump = false;
  }

  /**
   * Fallback for single-fire jump triggers
   */
  jump() {
    this.jumpPress();
    setTimeout(() => this.jumpRelease(), 120);
  }

  getSpeed(timeSec) {
    for (const s of this.stages) {
      if (timeSec >= s.start && timeSec < s.end) {
        if (s.stage <= 5) {
          const ratio = (timeSec - s.start) / (s.end - s.start);
          return s.spd1 + ratio * (s.spd2 - s.spd1);
        } else {
          const spd = s.spd1 + (timeSec - s.start) * 4.0;
          return Math.min(spd, 880);
        }
      }
    }
    return 880;
  }

  getMinGap(timeSec) {
    for (const s of this.stages) {
      if (timeSec >= s.start && timeSec < s.end) {
        return s.minGap;
      }
    }
    return 0.65;
  }

  getAvailableObstacleIndices(timeSec) {
    if (timeSec < 15) {
      return [0, 0, 0, 1, 2]; // mostly small cactus, occasionally tall or double
    } else if (timeSec < 30) {
      return [0, 1, 2, 0, 1]; // small, tall, double cacti
    } else {
      return [0, 1, 2, 3, 4, 0, 3]; // all obstacles including rhythm low birds
    }
  }

  updateSimulationTick() {
    if (this.simulation) {
      this.updateV2SimulationTick();
      return;
    }
    const timeSec = this.currentTick * this.dt;
    const speed = this.getSpeed(timeSec);

    // 1. Stage update check
    for (const s of this.stages) {
      if (timeSec >= s.start && timeSec < s.end && this.currentStage !== s.stage) {
        this.currentStage = s.stage;
        audio.playStageUp();
        this.onStageChange(s);
        break;
      }
    }

    // 2. Jump buffer execution if grounded
    if (this.isGrounded && this.jumpBufferedUntil >= this.currentTick) {
      this.dinoVy = this.jumpVelocityLow;
      this.isGrounded = false;
      this.activeJumpTick = this.currentTick;
      this.activeJumpHigh = false;
      this.jumpBufferedUntil = -1;

      audio.playJump();
      this.spawnDust(this.dinoX + 20, this.groundY);
    }

    // 3. High Jump Boost check (if button held for 6 ticks / 100ms)
    if (this.isHoldingJump && !this.isGrounded && !this.activeJumpHigh && this.activeJumpTick !== null) {
      if (this.currentTick - this.activeJumpTick === this.holdTicks) {
        this.activeJumpHigh = true;
        this.dinoVy = this.jumpVelocityHighBoost;
        this.spawnHighJumpSparkles(this.dinoX + 32, this.dinoY + 40);
        audio.playHighJump();
      }
    }

    // 4. Physics update for Dino
    if (!this.isGrounded) {
      this.dinoVy += this.gravity * this.dt;
      this.dinoY += this.dinoVy * this.dt;

      if (this.dinoY >= this.groundY - this.dinoH) {
        this.dinoY = this.groundY - this.dinoH;
        this.dinoVy = 0;
        this.isGrounded = true;
        this.spawnDust(this.dinoX + 20, this.groundY);

        // Record completed jump
        if (this.activeJumpTick !== null) {
          this.jumpTicks.push({
            tick: this.activeJumpTick,
            high: this.activeJumpHigh
          });
          this.activeJumpTick = null;
          this.activeJumpHigh = false;
        }
      }
    }

    // 5. Obstacle Spawning (Synchronized with server PRNG)
    if (timeSec >= this.nextSpawnTime) {
      const allowed = this.getAvailableObstacleIndices(timeSec);
      let randPick = Math.floor(this.prng.nextFloat() * allowed.length);
      if (randPick >= allowed.length) randPick = allowed.length - 1;
      const typeDef = this.obstacleTypes[allowed[randPick]];

      let obsY;
      if (typeDef.altitude === 'ground') {
        obsY = this.groundY - typeDef.h;
      } else {
        obsY = this.groundY - (typeDef.offsetFromGround || 85);
      }

      this.obstacles.push({
        x: this.width + 20,
        y: obsY,
        w: typeDef.w,
        h: typeDef.h,
        hb: typeDef.hb,
        type: typeDef.type,
        altitude: typeDef.altitude
      });

      // Consecutive Rhythm Combo & Randomness (always consume 2 floats for deterministic sync)
      const randRoll = this.prng.nextFloat();
      const randExtra = this.prng.nextFloat();

      const isCombo = (!this.lastWasCombo) && (randRoll < 0.35);
      let gap;
      if (isCombo) {
        // Consecutive jump situation!
        if (typeDef.type === 'cactus_tall' || typeDef.type === 'cactus_double') {
          // Landing from high jump (~0.75s)
          gap = 0.88 + randExtra * 0.12; // 0.88s ~ 1.00s
        } else {
          // Landing from low jump (~0.62s)
          gap = 0.68 + randExtra * 0.12; // 0.68s ~ 0.80s
        }
        this.lastWasCombo = true;
      } else {
        let baseInterval = this.getMinGap(timeSec);
        if (this.lastWasCombo) {
          baseInterval = Math.max(baseInterval, 1.15);
        }
        gap = baseInterval + randExtra * 0.45;
        this.lastWasCombo = false;
      }

      this.nextSpawnTime = timeSec + gap;
    }

    // 6. Move obstacles & check collision
    const dinoBox = {
      x: this.dinoX + this.dinoHitbox.offsetX,
      y: this.dinoY + this.dinoHitbox.offsetY,
      w: this.dinoHitbox.width,
      h: this.dinoHitbox.height
    };

    let collided = false;
    const remaining = [];
    for (const obs of this.obstacles) {
      obs.x -= speed * this.dt;

      const obsBox = {
        x: obs.x + obs.hb.offsetX,
        y: obs.y + obs.hb.offsetY,
        w: obs.hb.width,
        h: obs.hb.height
      };

      if (this.checkCollision(dinoBox, obsBox)) {
        collided = true;
        break;
      }

      if (obs.x + obs.w > -60) {
        remaining.push(obs);
      }
    }
    this.obstacles = remaining;

    // 7. Visual updates
    this.groundOffset = (this.groundOffset + speed * this.dt) % 40;
    this.updateParticles();
    this.updateShootingStars(timeSec);

    // 8. Score calculation (10 points / sec)
    this.score = Math.floor((this.currentTick / this.tickRate) * 10);
    this.onScoreUpdate(this.score);

    this.currentTick++;

    if (collided) {
      // Record in-flight jump if any
      if (this.activeJumpTick !== null) {
        this.jumpTicks.push({
          tick: this.activeJumpTick,
          high: this.activeJumpHigh
        });
        this.activeJumpTick = null;
      }
      this.handleCrash();
    }
  }

  syncV2State() {
    const sim = this.simulation;
    if (!sim) return;
    this.currentTick = sim.currentTick;
    this.score = sim.score;
    this.dinoY = sim.dinoY;
    this.dinoVy = sim.dinoVy;
    this.isGrounded = sim.isGrounded;
    this.activeJumpTick = sim.activeJumpTick;
    this.activeJumpHigh = sim.activeJumpHigh;
    this.jumpBufferedUntil = sim.jumpBufferedUntil;
    this.obstacles = sim.obstacles;
    this.items = sim.items;
    this.jumpTicks = sim.jumpTicks;
  }

  updateV2SimulationTick() {
    const previousStage = this.currentStage;
    const events = this.simulation.step({ holding: this.isHoldingJump });
    this.syncV2State();
    const timeSec = this.currentTick / this.tickRate;
    const speed = this.getSpeed(timeSec);
    const stage = this.stages.find((candidate) => timeSec >= candidate.start && timeSec < candidate.end) || this.stages[this.stages.length - 1];
    if (stage.stage !== previousStage) {
      this.currentStage = stage.stage;
      audio.playStageUp();
      this.onStageChange(stage);
    }
    for (const event of events) {
      if (event.type === 'coin') {
        audio.playStageUp();
        this.onCoinCollected({ coin_count: this.simulation.coins, coin_score: this.simulation.coins * V2_RULES.coinScore, score: this.score });
      } else if (event.type === 'heart') {
        this.onHeartChange({ hearts: this.simulation.heart, hearts_collected: this.simulation.hearts, reason: 'collected' });
      } else if (event.type === 'revive') {
        audio.playCollision();
        this.spawnReviveEffect();
        this.onHeartChange({ hearts: 0, hearts_collected: this.simulation.hearts, reason: 'consumed' });
        this.onRevive({ revive_count: this.simulation.revives, hearts: 0, invulnerable_until_tick: event.invulnerableUntilTick });
      }
    }
    this.groundOffset = (this.groundOffset + speed * this.dt) % 40;
    this.updateParticles();
    this.updateShootingStars(timeSec);
    this.onScoreUpdate(this.score);
    if (this.simulation.ended) this.handleCrash(this.simulation.result());
  }

  getSummary() {
    return this.simulation?.result().summary || { coins: 0, coin_score: 0, hearts: 0, revives: 0 };
  }

  checkCollision(a, b) {
    return !(
      a.x + a.w <= b.x ||
      a.x >= b.x + b.w ||
      a.y + a.h <= b.y ||
      a.y >= b.y + b.h
    );
  }

  handleCrash(result = null) {
    this.isRunning = false;
    if (!result || result.end_reason === 'COLLISION') {
      audio.playCollision();
      this.spawnCrashExplosion(this.dinoX + 30, this.dinoY + 30);
    }
    this.render(); // draw crash frame
    this.onGameOver(result || {
      score: this.score,
      ticks: this.currentTick,
      jump_ticks: this.jumpTicks
    });
  }

  gameLoop(timestamp) {
    if (!this.isRunning || this.isPaused) return;

    const frameDelta = Math.min((timestamp - this.lastFrameTime) / 1000.0, 0.1);
    this.lastFrameTime = timestamp;
    this.accumulator += frameDelta;

    while (this.accumulator >= this.dt) {
      this.updateSimulationTick();
      this.accumulator -= this.dt;
      if (!this.isRunning) return;
    }

    this.render();
    this.animId = requestAnimationFrame(this.loop);
  }

  spawnDust(x, y) {
    for (let i = 0; i < 4; i++) {
      this.particles.push({
        x: x + (Math.random() * 20 - 10),
        y: y - Math.random() * 8,
        vx: -(Math.random() * 60 + 20),
        vy: -(Math.random() * 40 + 10),
        size: Math.random() * 4 + 3,
        alpha: 0.6,
        color: '#BDC1C6'
      });
    }
  }

  spawnHighJumpSparkles(x, y) {
    const colors = ['#4285F4', '#EA4335', '#FBBC04', '#34A853'];
    for (let i = 0; i < 10; i++) {
      const angle = Math.random() * Math.PI * 2;
      const spd = Math.random() * 120 + 40;
      this.particles.push({
        x: x + (Math.random() * 20 - 10),
        y: y + (Math.random() * 20 - 10),
        vx: Math.cos(angle) * spd,
        vy: Math.sin(angle) * spd,
        size: Math.random() * 4 + 2,
        alpha: 0.9,
        color: colors[Math.floor(Math.random() * colors.length)]
      });
    }
  }

  spawnCrashExplosion(x, y) {
    const colors = ['#EA4335', '#FBBC04', '#4285F4', '#34A853'];
    for (let i = 0; i < 22; i++) {
      const angle = Math.random() * Math.PI * 2;
      const spd = Math.random() * 220 + 60;
      this.particles.push({
        x, y,
        vx: Math.cos(angle) * spd,
        vy: Math.sin(angle) * spd,
        size: Math.random() * 6 + 4,
        alpha: 1.0,
        color: colors[Math.floor(Math.random() * colors.length)]
      });
    }
  }

  spawnReviveEffect() {
    const count = this.reducedMotion ? 4 : 14;
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count;
      this.particles.push({
        x: this.dinoX + this.dinoW / 2,
        y: this.dinoY + this.dinoH / 2,
        vx: Math.cos(angle) * (this.reducedMotion ? 25 : 100),
        vy: Math.sin(angle) * (this.reducedMotion ? 25 : 100),
        size: this.reducedMotion ? 3 : 5,
        alpha: 0.9,
        color: '#EA4335'
      });
    }
  }

  updateParticles() {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx * this.dt;
      p.y += p.vy * this.dt;
      p.alpha -= 0.035;
      if (p.alpha <= 0) {
        this.particles.splice(i, 1);
      }
    }
  }

  updateShootingStars(timeSec) {
    // Dusk to Midnight (Stage 4, 5, 6: timeSec >= 42)
    if (timeSec >= 42 && Math.random() < 0.022 && this.shootingStars.length < 3) {
      this.shootingStars.push({
        x: Math.random() * (this.width * 0.75) + 50,
        y: Math.random() * 120 + 20,
        len: Math.random() * 65 + 35,
        speed: Math.random() * 380 + 420,
        angle: Math.PI / 4 + (Math.random() * 0.2 - 0.1),
        alpha: 1.0
      });
    }

    for (let i = this.shootingStars.length - 1; i >= 0; i--) {
      const ss = this.shootingStars[i];
      ss.x += Math.cos(ss.angle) * ss.speed * this.dt;
      ss.y += Math.sin(ss.angle) * ss.speed * this.dt;
      ss.alpha -= 0.028;
      if (ss.alpha <= 0 || ss.y > this.groundY - 50) {
        this.shootingStars.splice(i, 1);
      }
    }
  }

  render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    const timeSec = this.currentTick / this.tickRate;
    const env = this.getEnvironment(timeSec);
    this.currentEnv = env;

    // 1. Dynamic Sky Gradient
    const skyGrad = ctx.createLinearGradient(0, 0, 0, this.groundY);
    skyGrad.addColorStop(0, `rgb(${env.skyTop.join(',')})`);
    skyGrad.addColorStop(1, `rgb(${env.skyBottom.join(',')})`);
    ctx.fillStyle = skyGrad;
    ctx.fillRect(0, 0, this.width, this.height);

    // Subtle dynamic grid
    ctx.strokeStyle = env.gridColor;
    ctx.lineWidth = 1;
    for (let x = 0; x < this.width; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, this.height);
      ctx.stroke();
    }
    for (let y = 0; y < this.height; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();
    }

    // Twinkling Stars (appearing during Sunset, Twilight & Starry Night)
    if (env.starAlpha > 0.02) {
      for (const star of this.stars) {
        star.twinklePhase += 0.05;
        const twinkle = 0.5 + 0.5 * Math.sin(star.twinklePhase);
        const starOpacity = env.starAlpha * (0.35 + 0.65 * twinkle);

        ctx.save();
        ctx.globalAlpha = starOpacity;
        ctx.fillStyle = star.color;
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
        ctx.fill();

        // Cross sparkle for larger stars
        if (star.r > 2.0 && starOpacity > 0.6) {
          ctx.strokeStyle = star.color;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(star.x - star.r * 2.2, star.y);
          ctx.lineTo(star.x + star.r * 2.2, star.y);
          ctx.moveTo(star.x, star.y - star.r * 2.2);
          ctx.lineTo(star.x, star.y + star.r * 2.2);
          ctx.stroke();
        }
        ctx.restore();
      }
    }

    // Shooting Stars (별똥별 궤적)
    for (const ss of this.shootingStars) {
      ctx.save();
      ctx.globalAlpha = ss.alpha;
      const tailX = ss.x - Math.cos(ss.angle) * ss.len;
      const tailY = ss.y - Math.sin(ss.angle) * ss.len;
      const grad = ctx.createLinearGradient(tailX, tailY, ss.x, ss.y);
      grad.addColorStop(0, 'rgba(255, 255, 255, 0)');
      grad.addColorStop(1, 'rgba(255, 255, 255, 1)');
      ctx.strokeStyle = grad;
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(tailX, tailY);
      ctx.lineTo(ss.x, ss.y);
      ctx.stroke();

      // Sparkling head
      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.arc(ss.x, ss.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // Setting Sun (낮 -> 늦은 오후 -> 지평선에 걸친 노을)
    if (env.sunAlpha > 0.01 && env.sunY < this.groundY + 80) {
      ctx.save();
      ctx.globalAlpha = env.sunAlpha;

      // Sun Corona / Glow
      const glowGrad = ctx.createRadialGradient(env.sunX, env.sunY, env.sunR * 0.3, env.sunX, env.sunY, env.sunR * 2.6);
      glowGrad.addColorStop(0, env.sunGlow);
      glowGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = glowGrad;
      ctx.beginPath();
      ctx.arc(env.sunX, env.sunY, env.sunR * 2.6, 0, Math.PI * 2);
      ctx.fill();

      // Sun Body
      ctx.fillStyle = env.sunColor;
      ctx.beginPath();
      ctx.arc(env.sunX, env.sunY, env.sunR, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    }

    // Rising Moon (황혼에 서서히 떠올라 밤하늘을 수놓는 달)
    if (env.moonAlpha > 0.02) {
      ctx.save();
      ctx.globalAlpha = env.moonAlpha;

      // Moon Soft Corona Glow
      const moonGlow = ctx.createRadialGradient(env.moonX, env.moonY, 25, env.moonX, env.moonY, 110);
      moonGlow.addColorStop(0, 'rgba(255, 248, 225, 0.4)');
      moonGlow.addColorStop(0.5, 'rgba(138, 180, 248, 0.18)');
      moonGlow.addColorStop(1, 'rgba(138, 180, 248, 0)');
      ctx.fillStyle = moonGlow;
      ctx.beginPath();
      ctx.arc(env.moonX, env.moonY, 110, 0, Math.PI * 2);
      ctx.fill();

      // Moon Body
      ctx.fillStyle = '#FFF9C4';
      ctx.beginPath();
      ctx.arc(env.moonX, env.moonY, 46, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = '#FFE082';
      ctx.stroke();

      // Soft moon craters
      ctx.fillStyle = 'rgba(225, 210, 135, 0.35)';
      ctx.beginPath();
      ctx.arc(env.moonX - 12, env.moonY - 10, 8, 0, Math.PI * 2);
      ctx.arc(env.moonX + 14, env.moonY + 8, 11, 0, Math.PI * 2);
      ctx.arc(env.moonX - 4, env.moonY + 16, 6, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    }

    // 2. Ground Line & Moving Dashes
    ctx.strokeStyle = env.groundColor;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(0, this.groundY);
    ctx.lineTo(this.width, this.groundY);
    ctx.stroke();

    // Moving ground dash marks
    ctx.fillStyle = env.dashColor;
    for (let x = -this.groundOffset; x < this.width; x += 40) {
      ctx.fillRect(x, this.groundY + 8, 18, 3);
      ctx.fillRect(x + 22, this.groundY + 20, 10, 2);
    }

    // 3. Obstacles
    for (const obs of this.obstacles) {
      this.drawObstacle(ctx, obs);
    }

    for (const item of this.items || []) this.drawItem(ctx, item);

    // 4. Dino
    this.drawDino(ctx);

    if (this.simulation && this.currentTick < this.simulation.overlayUntilTick) {
      ctx.save();
      ctx.strokeStyle = 'rgba(234, 67, 53, 0.85)';
      ctx.lineWidth = this.reducedMotion ? 3 : 5;
      ctx.beginPath();
      ctx.arc(this.dinoX + this.dinoW / 2, this.dinoY + this.dinoH / 2, this.dinoW * 0.68, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // 5. Particles
    for (const p of this.particles) {
      ctx.save();
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  drawObstacle(ctx, obs) {
    ctx.save();

    if (obs.type === 'cactus_small') {
      // Small Cactus (36x48)
      ctx.fillStyle = '#34A853';
      ctx.strokeStyle = '#1E8E3E';
      ctx.lineWidth = 2.5;

      // Main trunk
      ctx.beginPath();
      ctx.roundRect(obs.x + 8, obs.y, 20, obs.h, [8, 8, 2, 2]);
      ctx.fill();
      ctx.stroke();

      // Left arm
      ctx.beginPath();
      ctx.roundRect(obs.x, obs.y + 16, 12, 16, [4, 4, 4, 4]);
      ctx.fill();
      ctx.stroke();

      // Right arm
      ctx.beginPath();
      ctx.roundRect(obs.x + 24, obs.y + 12, 12, 18, [4, 4, 4, 4]);
      ctx.fill();
      ctx.stroke();

      // Highlight line
      ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.fillRect(obs.x + 12, obs.y + 6, 3, obs.h - 12);

    } else if (obs.type === 'cactus_tall') {
      // Tall Cactus (44x84) - Clearly distinct height!
      ctx.fillStyle = '#1E8E3E';
      ctx.strokeStyle = '#137333';
      ctx.lineWidth = 3;

      // Tall central trunk
      ctx.beginPath();
      ctx.roundRect(obs.x + 10, obs.y, 24, obs.h, [10, 10, 2, 2]);
      ctx.fill();
      ctx.stroke();

      // Left high branch
      ctx.beginPath();
      ctx.roundRect(obs.x, obs.y + 24, 14, 26, [6, 6, 4, 4]);
      ctx.fill();
      ctx.stroke();

      // Right low branch
      ctx.beginPath();
      ctx.roundRect(obs.x + 30, obs.y + 36, 14, 28, [6, 6, 4, 4]);
      ctx.fill();
      ctx.stroke();

      // Spine markings
      ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
      ctx.fillRect(obs.x + 15, obs.y + 8, 3, obs.h - 18);
      ctx.fillRect(obs.x + 24, obs.y + 14, 3, obs.h - 26);

    } else if (obs.type === 'cactus_double') {
      // Double Cacti cluster (68x64)
      ctx.lineWidth = 2.5;

      // Cactus 1 (Left, taller)
      ctx.fillStyle = '#34A853';
      ctx.strokeStyle = '#1E8E3E';
      ctx.beginPath();
      ctx.roundRect(obs.x + 4, obs.y, 26, obs.h, [8, 8, 2, 2]);
      ctx.fill();
      ctx.stroke();

      // Cactus 2 (Right, slightly shorter)
      ctx.fillStyle = '#1E8E3E';
      ctx.strokeStyle = '#137333';
      ctx.beginPath();
      ctx.roundRect(obs.x + 34, obs.y + 12, 28, obs.h - 12, [8, 8, 2, 2]);
      ctx.fill();
      ctx.stroke();

      // Connecting base
      ctx.fillStyle = '#137333';
      ctx.fillRect(obs.x + 8, obs.y + obs.h - 8, 52, 8);

    } else if (obs.type === 'bird_low' || obs.type === 'bird_high') {
      // Animated Flying Pterodactyl (52x40)
      const isWingUp = Math.floor(this.currentTick / 7) % 2 === 0;
      const timeSec = this.currentTick * this.dt;
      const isWhiteBird = timeSec >= 52; // 밤하늘 진입(Stage 5, 6)부터 깔끔한 화이트로 전환

      // Bird body color
      ctx.fillStyle = isWhiteBird ? '#FFFFFF' : '#3C4043';
      ctx.strokeStyle = isWhiteBird ? '#BDC1C6' : '#202124';
      ctx.lineWidth = 2;

      // Main Torso
      ctx.beginPath();
      ctx.ellipse(obs.x + 26, obs.y + 22, 14, 8, -0.15, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Head and sharp beak
      ctx.beginPath();
      ctx.moveTo(obs.x + 8, obs.y + 18);
      ctx.lineTo(obs.x - 2, obs.y + 20); // beak tip pointing left
      ctx.lineTo(obs.x + 8, obs.y + 24);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Glowing Eye (Gemini Blue)
      ctx.fillStyle = isWhiteBird ? '#1967D2' : '#4285F4';
      ctx.beginPath();
      ctx.arc(obs.x + 6, obs.y + 19, 2.5, 0, Math.PI * 2);
      ctx.fill();

      // Animated Wings
      ctx.fillStyle = isWhiteBird ? '#E8EAED' : '#5F6368';
      ctx.beginPath();
      if (isWingUp) {
        // Wings pointing UP
        ctx.moveTo(obs.x + 22, obs.y + 18);
        ctx.lineTo(obs.x + 30, obs.y + 2); // wing apex
        ctx.lineTo(obs.x + 38, obs.y + 18);
      } else {
        // Wings pointing DOWN
        ctx.moveTo(obs.x + 22, obs.y + 24);
        ctx.lineTo(obs.x + 30, obs.y + 38); // wing tip down
        ctx.lineTo(obs.x + 38, obs.y + 24);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Tail feather
      ctx.beginPath();
      ctx.moveTo(obs.x + 40, obs.y + 20);
      ctx.lineTo(obs.x + 50, obs.y + 18);
      ctx.lineTo(obs.x + 40, obs.y + 24);
      ctx.closePath();
      ctx.fillStyle = isWhiteBird ? '#E8EAED' : '#3C4043';
      ctx.fill();
      ctx.stroke();

      // Airflow cue for High Bird
      if (obs.type === 'bird_high') {
        ctx.strokeStyle = isWhiteBird ? 'rgba(255, 255, 255, 0.65)' : 'rgba(66, 133, 244, 0.4)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(obs.x + 54, obs.y + 20);
        ctx.lineTo(obs.x + 68, obs.y + 20);
        ctx.stroke();
      }
    }

    ctx.restore();
  }

  drawItem(ctx, item) {
    ctx.save();
    const image = item.kind === 'coin' ? this.smileImg : this.heartImg;
    const imageLoaded = item.kind === 'coin' ? this.smileLoaded : this.heartLoaded;
    let imageDrawn = false;
    if (imageLoaded) {
      const sourceWidth = Number(image.naturalWidth || image.width);
      const sourceHeight = Number(image.naturalHeight || image.height);
      if (sourceWidth > 0 && sourceHeight > 0) {
        const scale = Math.min(item.w / sourceWidth, item.h / sourceHeight);
        const width = sourceWidth * scale;
        const height = sourceHeight * scale;
        try {
          ctx.drawImage(image, item.x + (item.w - width) / 2, item.y + (item.h - height) / 2, width, height);
          imageDrawn = true;
        } catch (_) {
          imageDrawn = false;
        }
      }
    }

    if (!imageDrawn && item.kind === 'coin') {
      ctx.fillStyle = '#FBBC04';
      ctx.strokeStyle = '#E37400';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(item.x + item.w / 2, item.y + item.h / 2, item.w / 2 - 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 15px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('G', item.x + item.w / 2, item.y + item.h / 2 + 1);
    } else if (!imageDrawn) {
      ctx.fillStyle = '#EA4335';
      ctx.font = '30px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('♥', item.x + item.w / 2, item.y + item.h / 2);
    }
    ctx.restore();
  }

  drawDino(ctx) {
    ctx.save();

    // Night glow / cyber aura for Dino during twilight & night stages
    if (this.currentEnv && this.currentEnv.dinoGlow > 0) {
      ctx.shadowColor = 'rgba(138, 180, 248, 0.85)';
      ctx.shadowBlur = this.currentEnv.dinoGlow;
    }

    if (this.dinoLoaded) {
      // Gentle bobbing when running on ground
      const bob = this.isGrounded ? Math.sin(this.currentTick * 0.4) * 2 : 0;
      const tilt = !this.isGrounded ? (this.dinoVy < 0 ? -0.12 : 0.08) : 0;

      ctx.translate(this.dinoX + this.dinoW / 2, this.dinoY + this.dinoH / 2 + bob);
      ctx.rotate(tilt);
      ctx.drawImage(this.dinoImg, -this.dinoW / 2, -this.dinoH / 2, this.dinoW, this.dinoH);

      // Show small jump aura when high jump boost is active
      if (this.activeJumpHigh && !this.isGrounded) {
        ctx.strokeStyle = 'rgba(66, 133, 244, 0.6)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(0, 0, this.dinoW * 0.58, 0, Math.PI * 2);
        ctx.stroke();
      }
    } else {
      // Fallback vector dino
      ctx.fillStyle = '#1967D2';
      ctx.beginPath();
      ctx.roundRect(this.dinoX, this.dinoY, this.dinoW, this.dinoH, 8);
      ctx.fill();
    }
    ctx.restore();
  }
}
