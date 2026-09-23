/* ==========================================================================
       Team Gemini - Gate Runner Pro (Alive Running Physics & Dynamic Enemy Rush)
       ========================================================================== */
    (function() {
      const canvas = document.getElementById('runner-canvas');
      const ctx = canvas.getContext('2d');
      const viewport = document.getElementById('viewport');
      const armyCountText = document.getElementById('army-count-text');
      const stageBadge = document.getElementById('stage-badge');
      const hintBanner = document.getElementById('hint-banner');
      const stageToast = document.getElementById('stage-toast');
      const toastText = document.getElementById('toast-text');
      const resultModal = document.getElementById('result-modal');
      const btnRestart = document.getElementById('btn-restart');

      let width = 0;
      let height = 0;
      let dpr = 1;

      function resize() {
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = viewport.clientWidth;
        height = viewport.clientHeight;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);
      }
      window.addEventListener('resize', () => { resize(); updateArmyOffsets(); });
      resize();

      // 사운드 합성 (Web Audio API)
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      let audioCtx = null;

      function initAudio() {
        if (!AudioCtx || muted) return;
        if (!audioCtx) audioCtx = new AudioCtx();
        if (audioCtx.state === 'suspended') audioCtx.resume();
      }

      function playSound(type) {
        if (!audioCtx || muted) return;
        try {
          const now = audioCtx.currentTime;
          if (type === 'gate_good') {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(440, now);
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.14);
            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.14);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.14);
          } else if (type === 'hit') {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'square';
            osc.frequency.setValueAtTime(140, now);
            osc.frequency.exponentialRampToValueAtTime(45, now + 0.08);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.08);
          } else if (type === 'enemy_destroy') {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(260, now);
            osc.frequency.exponentialRampToValueAtTime(560, now + 0.18);
            gain.gain.setValueAtTime(0.3, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.18);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.18);
          } else if (type === 'gate_bad') {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(180, now);
            osc.frequency.exponentialRampToValueAtTime(80, now + 0.18);
            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.18);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start(now);
            osc.stop(now + 0.18);
          } else if (type === 'stage_clear') {
            [440, 554, 659, 880].forEach((freq, i) => {
              const osc = audioCtx.createOscillator();
              const gain = audioCtx.createGain();
              osc.frequency.setValueAtTime(freq, now + i * 0.08);
              gain.gain.setValueAtTime(0.22, now + i * 0.08);
              gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.08 + 0.22);
              osc.connect(gain);
              gain.connect(audioCtx.destination);
              osc.start(now + i * 0.08);
              osc.stop(now + i * 0.08 + 0.22);
            });
          }
        } catch(e){}
      }

      function vibrate(pattern) {
        if (navigator.vibrate) {
          try { navigator.vibrate(pattern); } catch(e){}
        }
      }

      // 이미지 에셋 및 자동 누끼(Chroma-Key Flood Fill) 고화질 스프라이트 캐시
      const rawImages = {
        dino: new Image(),
        claude: new Image()
      };
      const sprites = {
        dino: null,
        claude: null,
        loaded: false
      };

      // 🤖 공식 Claude Code(클로드 코드) 로고 기반 고화질 3D 픽셀 로봇 스프라이트 즉시 생성
      function createClaudeCodeSprite(targetSize = 320) {
        const off = document.createElement('canvas');
        off.width = targetSize;
        off.height = targetSize;
        const octx = off.getContext('2d');

        // SVG viewBox: 0 0 24 24
        // Path spans x: 0..24 (width 24), y: 5..20 (height 15)
        // Center: x = 12, y = 12.5
        const scale = (targetSize * 0.82) / 24;
        octx.save();
        octx.translate(targetSize * 0.5, targetSize * 0.54);
        octx.scale(scale, scale);
        octx.translate(-12, -12.5);

        // 공식 Claude Code SVG 경로 (Retro 8-Bit Cyber Monster Robot)
        const pathStr = "M20.998 10.949H24v3.102h-3v3.028h-1.487V20H18v-2.921h-1.487V20H15v-2.921H9V20H7.488v-2.921H6V20H4.487v-2.921H3V14.05H0V10.95h3V5h17.998v5.949zM6 10.949h1.488V8.102H6v2.847zm10.51 0H18V8.102h-1.49v2.847z";
        const path = new Path2D(pathStr);

        // 1. 3D 입체 그림자 압출 (Bevel Extrusion Shadow)
        octx.save();
        octx.translate(0.55, 0.75);
        octx.fillStyle = '#80341e'; // 깊이감 있는 짙은 테라코타
        octx.fill(path);
        octx.restore();

        // 2. 메인 바디 그라데이션 (Anthropic 시그니처 테라코타 오렌지)
        const grad = octx.createLinearGradient(0, 5, 0, 20);
        grad.addColorStop(0, '#ea8667');
        grad.addColorStop(0.4, '#d97757');
        grad.addColorStop(1, '#be5736');
        octx.fillStyle = grad;
        octx.fill(path);

        // 3. 선명한 픽셀 아웃라인
        octx.strokeStyle = '#9c3d21';
        octx.lineWidth = 0.38;
        octx.stroke(path);

        // 4. 눈동자 컷아웃 내부의 빛나는 사이버 블루 LED 안구 (Glowing Cyber Eyes)
        octx.fillStyle = '#38bdf8';
        octx.shadowColor = '#00e5ff';
        octx.shadowBlur = 4;
        octx.fillRect(6.2, 8.3, 1.1, 2.4);
        octx.fillRect(16.7, 8.3, 1.1, 2.4);
        octx.shadowBlur = 0;

        // 안구 화이트 하이라이트
        octx.fillStyle = '#ffffff';
        octx.fillRect(6.4, 8.6, 0.65, 0.95);
        octx.fillRect(16.9, 8.6, 0.65, 0.95);

        // 5. 이마 터미널 코드 매트릭스 도트 (< / > 느낌의 레트로 픽셀 질감)
        octx.fillStyle = 'rgba(255, 255, 255, 0.2)';
        for (let gx = 5; gx <= 19; gx += 2) {
          for (let gy = 5.6; gy <= 7.4; gy += 0.9) {
            octx.fillRect(gx, gy, 0.9, 0.5);
          }
        }

        // 6. 가슴 중앙 Claude 공식 Asterisk 심볼 양각 각인
        octx.fillStyle = 'rgba(255, 255, 255, 0.38)';
        octx.beginPath();
        octx.arc(12, 13.5, 0.7, 0, Math.PI * 2);
        octx.fill();
        for (let a = 0; a < 6; a++) {
          const rad = (a * Math.PI) / 3;
          octx.fillRect(12 + Math.cos(rad) * 1.4 - 0.35, 13.5 + Math.sin(rad) * 1.4 - 0.35, 0.7, 0.7);
        }

        octx.restore();
        return off;
      }

      // 초기화 즉시 공식 Claude Code 3D 픽셀 로봇 스프라이트 생성
      sprites.claude = createClaudeCodeSprite(320);
      rawImages.claude.onload = () => { sprites.claude = rawImages.claude; };
      rawImages.claude.src = '/assets/icons/gate-claude-v2.png';

      rawImages.dino.onload = () => {
        sprites.dino = rawImages.dino;
        sprites.loaded = true;
      };
      rawImages.dino.onerror = () => {
        if (!rawImages.dino.src.endsWith('Dino-Dark.png')) {
          rawImages.dino.src = '/assets/icons/Dino-Dark.png';
        }
      };
      rawImages.dino.src = '/assets/icons/Dino-Dark.png';

      // 지능형 외곽 Flood-Fill & Alpha Feathering 배경 제거기 (원형 뱃지 탈피 -> 100% 온전한 전신 캐릭터 추출!)
      function createKeyedSprite(img, targetDim = 384) {
        const nw = img.naturalWidth || img.width || 1024;
        const nh = img.naturalHeight || img.height || 1024;
        const aspect = nh / nw;
        const w = targetDim;
        const h = Math.round(targetDim * aspect);

        const off = document.createElement('canvas');
        off.width = w;
        off.height = h;
        const octx = off.getContext('2d');
        octx.drawImage(img, 0, 0, w, h);

        const imgData = octx.getImageData(0, 0, w, h);
        const data = imgData.data;
        const total = w * h;
        const visited = new Uint8Array(total);
        const queue = new Int32Array(total);
        let qHead = 0;
        let qTail = 0;

        function isBgPixel(idx) {
          const r = data[idx];
          const g = data[idx + 1];
          const b = data[idx + 2];
          // 순백색 및 스튜디오 고광택 조명 배경 감지
          if (r > 230 && g > 230 && b > 230) return true;
          const maxVal = Math.max(r, g, b);
          const minVal = Math.min(r, g, b);
          if (minVal > 200 && (maxVal - minVal) < 22) return true;
          return false;
        }

        // 이미지 외곽 둘레(Perimeter)에서 배경 후보 탐색
        for (let x = 0; x < w; x++) {
          const top = x;
          if (isBgPixel(top * 4)) { visited[top] = 1; queue[qTail++] = top; }
          const bot = (h - 1) * w + x;
          if (isBgPixel(bot * 4) && !visited[bot]) { visited[bot] = 1; queue[qTail++] = bot; }
        }
        for (let y = 0; y < h; y++) {
          const left = y * w;
          if (isBgPixel(left * 4) && !visited[left]) { visited[left] = 1; queue[qTail++] = left; }
          const right = y * w + (w - 1);
          if (isBgPixel(right * 4) && !visited[right]) { visited[right] = 1; queue[qTail++] = right; }
        }

        // BFS Flood-Fill로 외부 배경만 정확하게 확장 (캐릭터 내부 흰색 이빨/운동화/하이라이트는 완벽 보호!)
        while (qHead < qTail) {
          const curr = queue[qHead++];
          const cx = curr % w;
          const cy = (curr / w) | 0;

          const n1 = cx > 0 ? curr - 1 : -1;
          const n2 = cx < w - 1 ? curr + 1 : -1;
          const n3 = cy > 0 ? curr - w : -1;
          const n4 = cy < h - 1 ? curr + w : -1;

          if (n1 !== -1 && !visited[n1] && isBgPixel(n1 * 4)) { visited[n1] = 1; queue[qTail++] = n1; }
          if (n2 !== -1 && !visited[n2] && isBgPixel(n2 * 4)) { visited[n2] = 1; queue[qTail++] = n2; }
          if (n3 !== -1 && !visited[n3] && isBgPixel(n3 * 4)) { visited[n3] = 1; queue[qTail++] = n3; }
          if (n4 !== -1 && !visited[n4] && isBgPixel(n4 * 4)) { visited[n4] = 1; queue[qTail++] = n4; }
        }

        // 배경 픽셀 투명화
        for (let i = 0; i < total; i++) {
          if (visited[i]) {
            data[i * 4 + 3] = 0;
          }
        }

        // 경계선 1픽셀 부드러운 안티앨리어싱(Feathering)
        for (let y = 1; y < h - 1; y++) {
          for (let x = 1; x < w - 1; x++) {
            const idx = y * w + x;
            if (!visited[idx]) {
              const hasBg = visited[idx - 1] || visited[idx + 1] || visited[idx - w] || visited[idx + w];
              if (hasBg) {
                const b = (data[idx * 4] + data[idx * 4 + 1] + data[idx * 4 + 2]) / 3;
                if (b > 195) {
                  data[idx * 4 + 3] = Math.max(0, Math.min(255, Math.round(((255 - b) / 60) * 220 + 35)));
                }
              }
            }
          }
        }

        octx.putImageData(imgData, 0, 0);
        return off;
      }

      // ==========================================
      // 스테이지가 높아질수록 판단 시간이 짧아지는 가속 러닝
      // ==========================================
      const STAGE_CONFIGS = [
        {
          trackLength: 3200, forwardSpeed: 155,
          gates: [
            {"dist": 350, "left": {"op": "add", "val": 9}, "right": {"op": "add", "val": 6}},
            {"dist": 1100, "left": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 3}]}, "right": {"op": "add", "val": 5}},
            {"dist": 1950, "left": {"op": "sub", "val": 2}, "right": {"op": "div", "val": 2}},
            {"dist": 2700, "left": {"op": "set", "val": 14}, "right": {"op": "mul", "val": 2}}
          ],
          enemies: [
            {"dist": 650, "x": -0.3, "count": 3, "widthSpan": 0.42, "label": "1관문 Claude 순찰대", "speed": 22},
            {"dist": 1450, "x": 0.32, "count": 4, "widthSpan": 0.42, "label": "1관문 Claude 추격대", "speed": 26},
            {"dist": 2350, "x": -0.15, "count": 2, "widthSpan": 0.42, "label": "1관문 Claude 요격대", "speed": 20},
            {"dist": 3000, "x": 0, "count": 9, "widthSpan": 0.85, "label": "1관문 Claude 수문장", "speed": 0}
          ]
        },
        {
          trackLength: 3500, forwardSpeed: 195,
          gates: [
            {"dist": 400, "left": {"op": "add", "val": 12}, "right": {"op": "mul", "val": 2}},
            {"dist": 1200, "left": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 8}]}, "right": {"op": "add", "val": 3}, "swapPeriod": 1.74},
            {"dist": 2000, "left": {"op": "sub", "val": 3}, "right": {"op": "div", "val": 2}},
            {"dist": 2850, "left": {"op": "set", "val": 20}, "right": {"op": "add", "val": 10}}
          ],
          enemies: [
            {"dist": 700, "x": -0.3, "count": 5, "widthSpan": 0.42, "label": "2관문 Claude 순찰대", "speed": 25},
            {"dist": 1550, "x": 0.32, "count": 6, "widthSpan": 0.42, "label": "2관문 Claude 추격대", "speed": 29},
            {"dist": 2400, "x": -0.15, "count": 3, "widthSpan": 0.42, "label": "2관문 Claude 요격대", "speed": 23},
            {"dist": 3300, "x": 0, "count": 14, "widthSpan": 0.85, "label": "2관문 Claude 수문장", "speed": 0}
          ]
        },
        {
          trackLength: 3800, forwardSpeed: 245,
          gates: [
            {"dist": 400, "left": {"op": "mul", "val": 3}, "right": {"op": "add", "val": 60}},
            {"dist": 1250, "left": {"op": "set", "val": 100}, "right": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 8}]}, "swapPeriod": 1.5799999999999998},
            {"dist": 2150, "left": {"op": "div", "val": 2}, "right": {"op": "sub", "val": 20}},
            {"dist": 3050, "left": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 10}]}, "right": {"op": "set", "val": 80}}
          ],
          enemies: [
            {"dist": 750, "x": -0.3, "count": 12, "widthSpan": 0.42, "label": "3관문 Claude 순찰대", "speed": 28},
            {"dist": 1650, "x": 0.32, "count": 16, "widthSpan": 0.42, "label": "3관문 Claude 추격대", "speed": 32},
            {"dist": 2550, "x": -0.15, "count": 14, "widthSpan": 0.42, "label": "3관문 Claude 요격대", "speed": 26},
            {"dist": 3600, "x": 0, "count": 30, "widthSpan": 0.85, "label": "3관문 Claude 수문장", "speed": 0}
          ]
        },
        {
          trackLength: 4000, forwardSpeed: 300,
          gates: [
            {"dist": 400, "left": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 10}]}, "right": {"op": "add", "val": 90}},
            {"dist": 1300, "left": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 20}]}, "right": {"op": "set", "val": 210}, "swapPeriod": 1.42},
            {"dist": 2250, "left": {"op": "sub", "val": 100}, "right": {"op": "div", "val": 2}},
            {"dist": 3200, "left": {"op": "set", "val": 180}, "right": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 20}]}, "swapPeriod": 1.42}
          ],
          enemies: [
            {"dist": 800, "x": -0.3, "count": 20, "widthSpan": 0.42, "label": "4관문 Claude 순찰대", "speed": 31},
            {"dist": 1750, "x": 0.32, "count": 30, "widthSpan": 0.42, "label": "4관문 Claude 추격대", "speed": 35},
            {"dist": 2700, "x": -0.15, "count": 20, "widthSpan": 0.42, "label": "4관문 Claude 요격대", "speed": 29},
            {"dist": 3800, "x": 0, "count": 55, "widthSpan": 0.85, "label": "4관문 Claude 수문장", "speed": 0}
          ]
        },
        {
          trackLength: 4200, forwardSpeed: 360,
          gates: [
            {"dist": 400, "left": {"op": "add", "val": 150}, "right": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 10}]}},
            {"dist": 1350, "left": {"op": "chain", "steps": [{"op": "mul", "val": 2}, {"op": "sub", "val": 40}]}, "right": {"op": "set", "val": 360}, "swapPeriod": 1.2599999999999998},
            {"dist": 2350, "left": {"op": "sub", "val": 180}, "right": {"op": "sub", "val": 100}},
            {"dist": 3350, "left": {"op": "sub", "val": 150}, "right": {"op": "div", "val": 2}}
          ],
          enemies: [
            {"dist": 800, "x": -0.3, "count": 35, "widthSpan": 0.42, "label": "5관문 Claude 순찰대", "speed": 34},
            {"dist": 1800, "x": 0.32, "count": 45, "widthSpan": 0.42, "label": "5관문 Claude 추격대", "speed": 38},
            {"dist": 2800, "x": -0.15, "count": 35, "widthSpan": 0.42, "label": "5관문 Claude 요격대", "speed": 32},
            {"dist": 4000, "x": 0, "count": 125, "widthSpan": 0.85, "label": "5관문 Claude 수문장", "speed": 0, "isBoss": true}
          ]
        }
      ];

      // 게임 기본 제어
      let currentStageIndex = 0;
      let state = 'ready';
      let muted = false;
      let worldTime = 0;
      let stageClearRemaining = 0;
      let resumeState = 'playing';
      const keys = new Set();
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      let distance = 0;
      const MAX_VISIBLE_ARMY = 81;
      let screenShake = 0;

      // 플레이어 군단
      let playerArmy = [];
      let playerTargetX = 0;
      let playerCurrentX = 0;

      // 발밑 먼지 및 스파크 파티클
      let dustParticles = [];

      // 3D 지면 충격파 링 (Shockwave Rings)
      let shockwaves = [];

      // 올 클리어 축하 컨페티(꽃가루) 폭죽
      let confettiParticles = [];

      // 길가 배경 오브젝트 (가로수 & 바람에 펄럭이는 구글 4색 깃발)
      let roadsideProps = [];
      function generateRoadsideProps(trackLen) {
        roadsideProps = [];
        for (let d = 100; d < trackLen + 1500; d += 180) {
          roadsideProps.push({ dist: d, side: -1, type: Math.floor(d / 80) % 2 === 0 ? 'tree' : 'flag' });
          roadsideProps.push({ dist: d, side: 1, type: Math.floor(d / 80) % 2 === 0 ? 'flag' : 'tree' });
        }
      }

      // 현재 스테이지 인스턴스
      let activeGates = [];
      let activeEnemies = [];
      let popups = [];

      function initStage(stageIdx, carryOverArmy = null) {
        currentStageIndex = stageIdx;
        const cfg = STAGE_CONFIGS[stageIdx];
        distance = 0;
        playerTargetX = 0;
        playerCurrentX = 0;
        state = 'playing';
        screenShake = 0;
        dustParticles = [];
        shockwaves = [];
        confettiParticles = [];
        popups = [];
        stageClearRemaining = 0;
        keys.clear();
        isDragging = false;

        generateRoadsideProps(cfg.trackLength);

        if (carryOverArmy && carryOverArmy.length > 0) {
          playerArmy = carryOverArmy;
        } else {
          playerArmy = [{ type: 'dino', offsetX: 0, offsetY: 0, animSeed: 0, spawnProgress: 1 }];
        }

        activeGates = cfg.gates.map(g => ({
          dist: g.dist,
          passed: false,
          punch: 1.0,
          phase: 0,
          locked: false,
          swapPeriod: g.swapPeriod || 0,
          left: { ...g.left },
          right: { ...g.right }
        }));

        activeEnemies = cfg.enemies.map(e => ({
          dist: e.dist,
          initialDist: e.dist,
          x: e.x,
          totalCount: e.count,
          currentCount: e.count,
          widthSpan: e.widthSpan,
          label: e.label,
          speed: e.speed || 0,
          isBoss: !!e.isBoss,
          destroyed: false
        }));

        stageBadge.textContent = `STAGE ${stageIdx + 1} / 5`;
        document.getElementById('environment-name').textContent = ENVIRONMENTS[stageIdx].name;
        document.getElementById('stage-progress').style.width = '0%';
        document.getElementById('distance-text').textContent = '0%';
        updateArmyOffsets();
        for (const unit of playerArmy.slice(0, MAX_VISIBLE_ARMY)) unit.followX = 0;
      }

      // Individual followers keep their own stride and ease into a loose flock.
      function updateArmyOffsets() {
        armyCountText.textContent = playerArmy.length;
        const count = Math.min(playerArmy.length, MAX_VISIBLE_ARMY);
        const spread = Math.min(width * 0.24, 12 * Math.sqrt(count));
        const depth = Math.min(height * 0.17, 11 * Math.sqrt(count));
        for (let i = 0; i < count; i++) {
          const unit = playerArmy[i];
          const radius = Math.sqrt((i + 0.5) / count);
          const angle = i * 2.3999632297;
          unit.targetOffsetX = count === 1 ? 0 : Math.cos(angle) * radius * spread;
          unit.targetOffsetY = count === 1 ? 0 : (Math.sin(angle) * radius + 1) * depth / 2;
          unit.offsetX ??= 0;
          unit.offsetY ??= 0;
          unit.followX ??= playerCurrentX;
          unit.animSeed ??= i * 1.73;
          unit.spawnProgress ??= 1;
        }
      }

      function updateArmyMotion(dt) {
        const count = Math.min(playerArmy.length, MAX_VISIBLE_ARMY);
        const spread = Math.min(width * 0.24, 12 * Math.sqrt(count));
        const depth = Math.min(height * 0.17, 11 * Math.sqrt(count));
        for (let i = 0; i < count; i++) {
          const unit = playerArmy[i];
          const seed = unit.animSeed;
          const freedom = count > 1 && !reducedMotion ? 1 : 0;
          const wanderX = Math.sin(worldTime * 1.7 + seed * 3) * 6 * freedom;
          const wanderY = Math.cos(worldTime * 2.1 + seed * 2) * 4 * freedom;
          const ease = 1 - Math.exp(-(4 + (i % 5) * 0.55) * dt);
          unit.offsetX += (unit.targetOffsetX + wanderX - unit.offsetX) * ease;
          unit.offsetY += (unit.targetOffsetY + wanderY - unit.offsetY) * ease;
          unit.followX += (playerCurrentX - unit.followX) * (1 - Math.exp(-(6 + i % 4) * dt));
          unit.spawnProgress = Math.min(1, unit.spawnProgress + dt * 2.8);
        }
        // Soft separation: neighbours make room instead of moving as a rigid grid.
        const separation = Math.min(0.24, dt * 8);
        for (let i = 0; i < count; i++) {
          for (let j = i + 1; j < count; j++) {
            const a = playerArmy[i], b = playerArmy[j];
            const dx = b.offsetX - a.offsetX, dy = (b.offsetY - a.offsetY) * 1.5;
            const gap = Math.hypot(dx, dy);
            if (gap > 0.01 && gap < 19) {
              const push = (19 - gap) / gap * separation;
              a.offsetX -= dx * push; b.offsetX += dx * push;
              a.offsetY -= dy / 1.5 * push; b.offsetY += dy / 1.5 * push;
            }
          }
        }
        for (let i = 0; i < count; i++) {
          const unit = playerArmy[i];
          unit.offsetX = Math.max(-spread - 6, Math.min(spread + 6, unit.offsetX));
          unit.offsetY = Math.max(-5, Math.min(depth + 5, unit.offsetY));
        }
      }

      // 조작 핸들러 (드래그 & 무빙 부드럽게)
      let isDragging = false;
      let activePointer = null;
      let startClientX = 0;
      let startPlayerX = 0;

      function updateTarget(clientX) {
        const rect = canvas.getBoundingClientRect();
        const rel = (clientX - rect.left) / rect.width;
        playerTargetX = Math.max(-0.8, Math.min(0.8, (rel - 0.5) * 2.0));
        hintBanner.style.opacity = '0';
      }

      canvas.addEventListener('pointerdown', (e) => {
        if (state !== 'playing' || isDragging || (e.pointerType === 'mouse' && e.button !== 0)) return;
        initAudio();
        canvas.focus({ preventScroll: true });
        isDragging = true;
        activePointer = e.pointerId;
        startClientX = e.clientX;
        startPlayerX = playerTargetX;
        canvas.setPointerCapture(e.pointerId);
        if (e.pointerType === 'mouse') { updateTarget(e.clientX); startPlayerX = playerTargetX; }
      });
      canvas.addEventListener('pointermove', (e) => {
        if (!isDragging || state !== 'playing' || e.pointerId !== activePointer) return;
        playerTargetX = Math.max(-0.78, Math.min(0.78,
          startPlayerX + (e.clientX - startClientX) * (2.4 / width)));
        hintBanner.style.opacity = '0';
      });
      ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(event => {
        canvas.addEventListener(event, (e) => {
          if (e.pointerId === activePointer) { isDragging = false; activePointer = null; }
        });
      });
      function setPaused(paused) {
        if (paused && (state === 'playing' || state === 'stage_cleared')) {
          resumeState = state;
          state = 'paused';
          keys.clear();
          isDragging = false;
          document.getElementById('pause-screen').hidden = false;
          document.getElementById('btn-pause').setAttribute('aria-pressed', 'true');
          document.getElementById('btn-resume').focus();
        } else if (!paused && state === 'paused') {
          state = resumeState;
          document.getElementById('pause-screen').hidden = true;
          document.getElementById('btn-pause').setAttribute('aria-pressed', 'false');
          lastTime = performance.now();
          canvas.focus({ preventScroll: true });
        }
      }
      document.getElementById('btn-start').addEventListener('click', () => {
        document.getElementById('start-screen').hidden = true;
        initAudio();
        state = 'playing';
        canvas.focus({ preventScroll: true });
      });
      document.getElementById('btn-pause').addEventListener('click', () => setPaused(state !== 'paused'));
      document.getElementById('btn-resume').addEventListener('click', () => setPaused(false));
      document.getElementById('btn-sound').addEventListener('click', () => {
        muted = !muted;
        const button = document.getElementById('btn-sound');
        button.setAttribute('aria-pressed', String(muted));
        button.setAttribute('aria-label', muted ? '소리 켜기' : '소리 끄기');
        button.dataset.muted = String(muted);
        if (audioCtx) { if (muted) audioCtx.suspend(); else audioCtx.resume(); }
        else if (!muted) initAudio();
      });
      [['btn-left','arrowleft',-.28],['btn-right','arrowright',.28]].forEach(([id,key,step]) => {
        const button=document.getElementById(id);
        button.addEventListener('pointerdown', e => {
          if(state!=='playing')return;
          e.preventDefault();button.setPointerCapture(e.pointerId);keys.add(key);
          hintBanner.style.opacity='0';initAudio();
        });
        ['pointerup','pointercancel','lostpointercapture'].forEach(type => button.addEventListener(type,()=>keys.delete(key)));
        button.addEventListener('click', e => {
          // Keyboard and assistive-technology clicks move one deliberate step.
          if(state==='playing' && e.detail===0)playerTargetX=Math.max(-.78,Math.min(.78,playerTargetX+step));
        });
      });
      window.addEventListener('keydown', (e) => {
        if (['ArrowLeft', 'ArrowRight', 'a', 'A', 'd', 'D'].includes(e.key) && state === 'playing') {
          e.preventDefault(); keys.add(e.key.toLowerCase()); hintBanner.style.opacity = '0';
        }
        if ((e.key === 'Escape' || e.key.toLowerCase() === 'p') && !e.repeat) setPaused(state !== 'paused');
      });
      window.addEventListener('keyup', e => keys.delete(e.key.toLowerCase()));
      window.addEventListener('blur', () => setPaused(true));
      document.addEventListener('visibilitychange', () => { if (document.hidden) setPaused(true); });

      function addPopup(text, color, screenX, screenY) {
        popups.push({ text, color, x: screenX, y: screenY, vy: -60, life: 0.8, alpha: 1.0 });
      }

      function evaluateGateCount(count, option) {
        let result = count;
        switch (option.op) {
          case 'add': result += option.val; break;
          case 'sub': result -= option.val; break;
          case 'mul': result = Math.round(result * option.val); break;
          case 'div': result = Math.floor(result / option.val); break;
          case 'set': result = option.val; break;
          case 'chain':
            for (const step of option.steps) result = evaluateGateCount(result, step);
            break;
        }
        return Math.max(0, Math.min(500, result));
      }

      function formatGateOption(option) {
        if (option.op === 'chain') return option.steps.map(formatGateOption).join(' ');
        return ({ add: '+', sub: '−', mul: '×', div: '÷', set: '→' }[option.op] || '') + option.val;
      }

      function getGateChoices(gate) {
        const swapped = gate.swapPeriod > 0 && Math.floor((gate.phase || 0) / gate.swapPeriod) % 2 === 1;
        return swapped ? { left: gate.right, right: gate.left } : { left: gate.left, right: gate.right };
      }

      function updateGateMotion(gate, dt) {
        if (gate.passed || gate.locked || !gate.swapPeriod) return;
        // At least 2/3 second of stable choice even in the fastest stage.
        if (gate.dist - distance <= 240) { gate.locked = true; return; }
        gate.phase += dt;
      }

      function applyGate(gate, gateSide, screenX, screenY) {
        const curr = playerArmy.length;
        let nextCount = evaluateGateCount(curr, gateSide);
        const gain = nextCount >= curr;
        gate.punch = 1.35;
        shockwaves.push({ trackX: playerCurrentX, dist: distance, radius: 12, maxRadius: 55,
          color: gain ? '#1a73e8' : '#ea4335', alpha: 0.85 });
        const loss = curr - nextCount;
        addPopup(`${gain ? '+' : '−'}${Math.abs(loss)} · ${curr}→${nextCount}`, gain ? '#1a73e8' : '#ea4335', width / 2, screenY - 30);
        if (loss >= 100 && !reducedMotion) {
          screenShake = 6;
          const origin = project3D(playerCurrentX, 0);
          for (let i = 0; i < 14; i++) {
            dustParticles.push({ sprite: 'dino', x: origin.x + (Math.random() - .5) * 80,
              y: origin.y + Math.random() * 30, vx: (i % 2 ? 1 : -1) * (60 + Math.random() * 70),
              vy: -50 - Math.random() * 50, life: .65, size: 28 });
          }
        }
        playSound(gain ? 'gate_good' : 'gate_bad');
        vibrate(gain ? 20 : 40);

        nextCount = Math.min(500, nextCount);
        if (nextCount > curr) {
          const diff = nextCount - curr;
          for (let i = 0; i < diff; i++) {
            playerArmy.push({
              type: 'dino',
              offsetX: 0,
              offsetY: 0,
              followX: playerCurrentX,
              spawnProgress: 0,
              animSeed: Math.random() * 10
            });
          }
        } else if (nextCount < curr) {
          playerArmy = playerArmy.slice(0, nextCount);
        }

        if (playerArmy.length <= 0) {
          triggerGameOver('게이트 계산 착오로 공룡 군단이 전멸했습니다!');
        } else {
          updateArmyOffsets();
        }
      }

      // 적과 실시간 1:1 충돌 교전 (지면 충격파, 넉백 스파크, 거대 보스 레이드)
      function handleEnemyBattle(enemy, dt) {
        if (enemy.destroyed || enemy.currentCount <= 0) return;

        enemy.battleTime = (enemy.battleTime || 0) + dt * (enemy.isBoss ? 24 : 18);
        const kill = Math.min(enemy.currentCount, playerArmy.length, Math.floor(enemy.battleTime + 1e-8));
        if (kill < 1) return;
        enemy.battleTime -= kill;
        enemy.currentCount -= kill;
        playerArmy.splice(0, kill);
        updateArmyOffsets();

        screenShake = enemy.isBoss ? 7 : 4.5;
        playSound('hit');
        vibrate(enemy.isBoss ? 25 : 14);

        const proj = project3D(enemy.x, enemy.dist - distance);

        // 충격파 링 생성 (부딪힐 때마다 바닥에 촥 퍼짐)
        if (Math.random() < 0.6) {
          shockwaves.push({
            trackX: enemy.x,
            dist: enemy.dist,
            radius: 8,
            maxRadius: enemy.isBoss ? 55 : 35,
            color: enemy.isBoss ? '#ef4444' : (Math.random() > 0.5 ? '#d97757' : '#1a73e8'),
            alpha: 0.85
          });
        }

        // 전투 스파크 파티클 (구글 블루 vs 클로드 테라코타 오렌지)
        for (let i = 0; i < (enemy.isBoss ? 5 : 3); i++) {
          dustParticles.push({
            x: proj.x + (Math.random() - 0.5) * (enemy.isBoss ? 50 : 26),
            y: proj.y + (Math.random() - 0.5) * 20,
            vx: (Math.random() - 0.5) * 140,
            vy: -Math.random() * 120,
            life: 0.35,
            color: Math.random() > 0.5 ? '#d97757' : '#1a73e8',
            size: 4 + Math.random() * 3
          });
        }

        if (playerArmy.length <= 0) {
          triggerGameOver(`'${enemy.label}'(${enemy.totalCount}마리)에 막혀 공룡 군단이 전멸했습니다!`);
          return;
        }

        if (enemy.currentCount <= 0) {
          enemy.destroyed = true;
          addPopup(enemy.isBoss ? '👑 CLAUDE CODE 격파!!' : '💥 Claude Code 격파!', '#d97757', proj.x, proj.y);
          playSound('enemy_destroy');
          vibrate([40, 60, 50, 80]);

          // 보스 격파 시 대형 축하 쇼크웨이브
          if (enemy.isBoss) {
            for (let k = 0; k < 4; k++) {
              shockwaves.push({
                trackX: enemy.x,
                dist: enemy.dist,
                radius: 10 + k * 10,
                maxRadius: 70 + k * 15,
                color: '#f59e0b',
                alpha: 0.95
              });
            }
          }
        }
      }

      function handleStageClear() {
        state = 'stage_cleared';
        playSound('stage_clear');
        vibrate([50, 80, 50, 100]);

        // 화려한 축하 컨페티(꽃가루) 폭죽 쇼!
        for (let i = 0; i < 70; i++) {
          confettiParticles.push({
            x: width * Math.random(),
            y: height * 0.15 + Math.random() * 40,
            vx: (Math.random() - 0.5) * 260,
            vy: -150 - Math.random() * 220,
            w: 7 + Math.random() * 6,
            h: 5 + Math.random() * 5,
            color: ['#4285F4', '#EA4335', '#FBBC04', '#34A853', '#A142F4', '#FF7043'][Math.floor(Math.random() * 6)],
            rotation: Math.random() * Math.PI * 2,
            rotSpeed: (Math.random() - 0.5) * 12,
            life: 2.2 + Math.random() * 0.8
          });
        }

        if (currentStageIndex < STAGE_CONFIGS.length - 1) {
          toastText.textContent = `STAGE ${currentStageIndex + 1} 클리어! (${playerArmy.length}마리 이월) 🚀`;
          stageToast.style.display = 'flex';

          stageClearRemaining = 1.6;
        } else {
          showResultModal(true);
        }
      }

      function triggerGameOver(reason) {
        state = 'gameover';
        playSound('gate_bad');
        vibrate(250);
        showResultModal(false, reason);
      }

      function showResultModal(isSuccess, reason = '') {
        state = isSuccess ? 'won' : 'gameover';
        resultModal.style.display = 'flex';
        btnRestart.focus();
        const resEmoji = document.getElementById('res-emoji');
        const resTitle = document.getElementById('res-title');
        const resSub = document.getElementById('res-subtitle');
        const resCount = document.getElementById('res-final-count');
        const resStageVal = document.getElementById('res-stage-val');

        if (isSuccess) {
          resEmoji.textContent = '👑';
          resTitle.textContent = '5단계 최종 정복!';
          resSub.textContent = `축하합니다! ${playerArmy.length}마리의 막강한 공룡 군단으로 거대 Claude Code Opus 요새를 함락시켰습니다!`;
          resCount.textContent = `${playerArmy.length}마리`;
          resStageVal.textContent = '5 / 5 ALL CLEAR';
        } else {
          resEmoji.textContent = '💥';
          resTitle.textContent = '공룡 군단 전멸...';
          resSub.textContent = reason || '클로드 코드(Claude Code) 군단의 방어선이 강력합니다! 게이트에서 공룡을 더 모아보세요!';
          resCount.textContent = '0마리';
          resStageVal.textContent = `${currentStageIndex + 1} / 5 STAGE`;
        }
      }

      btnRestart.addEventListener('click', () => {
        resultModal.style.display = 'none';
        initAudio();
        initStage(0, null);
        canvas.focus({ preventScroll: true });
      });

      // 3D 투영 좌표계 (원거리 시야 1500, 부드러운 하이퍼캐주얼 원근)
      function project3D(trackX, zRel) {
        const horizonY = height * 0.15;
        const playerScreenY = height * 0.73;
        const depthFactor = 330 / (330 + Math.max(-120, zRel));
        const roadWidth = width * 0.86 * depthFactor;
        return { x: width / 2 + trackX * roadWidth / 2,
          y: horizonY + (playerScreenY - horizonY) * depthFactor,
          scale: depthFactor, roadWidth };
      }

      let lastTime = performance.now();

      function update(dt) {
        if (state === 'paused' || state === 'ready') return;
        worldTime += dt;
        if (state === 'stage_cleared' && stageClearRemaining > 0) {
          stageClearRemaining -= dt;
          if (stageClearRemaining <= 0) {
            stageToast.style.display = 'none';
            initStage(currentStageIndex + 1, playerArmy);
          }
        }
        const direction = Number(keys.has('arrowright') || keys.has('d')) - Number(keys.has('arrowleft') || keys.has('a'));
        playerTargetX = Math.max(-0.78, Math.min(0.78, playerTargetX + direction * dt * 1.8));
        playerCurrentX += (playerTargetX - playerCurrentX) * (1 - Math.exp(-12 * dt));

        if (screenShake > 0) {
          screenShake -= dt * 16;
          if (screenShake < 0) screenShake = 0;
        }

        if (state === 'playing') {
          for (const enemy of activeEnemies) updateEnemyMotion(enemy, dt);
          const fighting = activeEnemies.find(e => !e.destroyed && e.currentCount > 0 &&
            Math.abs(e.dist - distance) <= 24 && (e.speed === 0 || Math.abs(playerCurrentX - e.x) <= e.widthSpan / 2 + 0.22));
          const cfg = STAGE_CONFIGS[currentStageIndex];
          if (!fighting) distance += cfg.forwardSpeed * dt;

          // 1. 발밑 먼지 파티클 생성
          const pCenter = project3D(playerCurrentX, 0);
          if (Math.random() < 0.65) {
            dustParticles.push({
              x: pCenter.x + (Math.random() - 0.5) * 22,
              y: pCenter.y + 10,
              vx: (Math.random() - 0.5) * 30,
              vy: -15 - Math.random() * 20,
              life: 0.4,
              color: 'rgba(255, 255, 255, 0.65)',
              size: 4 + Math.random() * 4
            });
          }

          // 2. 적 군단 마주 달려오기
          activeEnemies.forEach(enemy => {
            if (enemy.destroyed || enemy.currentCount <= 0) return;
            if (state !== 'playing') return;
            if (enemy.speed > 0 && enemy !== fighting) {
              enemy.dist -= enemy.speed * dt;
            }

            const rel = enemy.dist - distance;
            if (rel <= 24 && rel >= -24) {
              const overlap = enemy.speed === 0 || Math.abs(playerCurrentX - enemy.x) <= (enemy.widthSpan / 2 + 0.22);
              if (overlap) {
                handleEnemyBattle(enemy, dt);
              }
            }
          });

          // 3. 게이트 판정
          activeGates.forEach(gate => {
            updateGateMotion(gate, dt);
            const rel = gate.dist - distance;
            if (state === 'playing' && !gate.passed && rel <= 10 && rel >= -25) {
              gate.passed = true;
              const pProj = project3D(playerCurrentX, 0);
              const choices = getGateChoices(gate);
              if (playerCurrentX < 0) {
                applyGate(gate, choices.left, pProj.x - 30, pProj.y);
              } else {
                applyGate(gate, choices.right, pProj.x + 30, pProj.y);
              }
            }
          });

          // 4. 결승선
          if (state === 'playing' && distance >= cfg.trackLength) {
            handleStageClear();
          }
        }

        updateArmyMotion(dt);

        const progress = Math.min(100, Math.round(distance / STAGE_CONFIGS[currentStageIndex].trackLength * 100));
        document.getElementById('stage-progress').style.width = progress + '%';
        document.getElementById('distance-text').textContent = progress + '%';

        // 지면 충격파 링 업데이트
        for (let i = shockwaves.length - 1; i >= 0; i--) {
          const sw = shockwaves[i];
          sw.radius += dt * 110;
          sw.alpha -= dt * 2.2;
          if (sw.alpha <= 0 || sw.radius >= sw.maxRadius) {
            shockwaves.splice(i, 1);
          }
        }

        // 먼지 파티클 업데이트
        for (let i = dustParticles.length - 1; i >= 0; i--) {
          const pt = dustParticles[i];
          pt.x += pt.vx * dt;
          pt.y += pt.vy * dt;
          pt.life -= dt;
          if (pt.life <= 0) dustParticles.splice(i, 1);
        }

        // 축하 컨페티 업데이트
        for (let i = confettiParticles.length - 1; i >= 0; i--) {
          const c = confettiParticles[i];
          c.x += c.vx * dt;
          c.y += c.vy * dt;
          c.vy += 320 * dt;
          c.rotation += c.rotSpeed * dt;
          c.life -= dt;
          if (c.life <= 0 || c.y > height + 50) {
            confettiParticles.splice(i, 1);
          }
        }

        // 팝업 파티클 업데이트
        for (let i = popups.length - 1; i >= 0; i--) {
          const p = popups[i];
          p.y += p.vy * dt;
          p.life -= dt;
          p.alpha = Math.max(0, p.life / 0.8);
          if (p.life <= 0) popups.splice(i, 1);
        }
      }

      // Classic Dino Jump sky palette, extended into a layered perspective world.
      const ENVIRONMENTS = [
        { name:'맑은 하늘', top:'#d3eaff', bottom:'#ffffff', far:'#9fbfdc', mid:'#74a99f', land:'#b9d9ba', water:'#8acee1', road:'#e4eefc', end:'#ffffff', light:'#fbbc04', accent:'#1967d2', night:0 },
        { name:'골든 아워', top:'#ffe8cd', bottom:'#fff6ec', far:'#debcab', mid:'#c5b6a0', land:'#ebd7b7', water:'#c2dce2', road:'#f5e8dc', end:'#fffcf5', light:'#f9ab00', accent:'#d78b30', night:0 },
        { name:'분홍빛 노을', top:'#8e55a8', bottom:'#ffb39c', far:'#9d86b6', mid:'#8d91ad', land:'#c5abc1', water:'#bea5d9', road:'#dcd9ee', end:'#f8eff7', light:'#ffcf8c', accent:'#ab71c8', night:0.12 },
        { name:'보랏빛 황혼', top:'#241a48', bottom:'#a53e70', far:'#55496f', mid:'#5a5d83', land:'#737993', water:'#6c82b1', road:'#8394bc', end:'#dce4f9', light:'#fff0c5', accent:'#ad9ced', night:0.65 },
        { name:'별이 빛나는 밤', top:'#0c1430', bottom:'#1c2646', far:'#293955', mid:'#344766', land:'#405472', water:'#476a9b', road:'#607eac', end:'#c0d7f1', light:'#fff9c4', accent:'#8ab4f8', night:1 }
      ];
      function getEnvironment(stageIndex, progress) {
        const index = Math.max(0, Math.min(4, stageIndex));
        const current = ENVIRONMENTS[index], next = ENVIRONMENTS[Math.min(4,index+1)];
        const amount = Math.max(0, Math.min(1,(progress-.45)/.55));
        const t = amount*amount*(3-2*amount);
        const result = { name:current.name, night:current.night+(next.night-current.night)*t };
        for(const key of ['top','bottom','far','mid','land','water','road','end','light','accent']) {
          const c = [1,3,5].map(i => {
            const a=parseInt(current[key].slice(i,i+2),16), b=parseInt(next[key].slice(i,i+2),16);
            return Math.round(a+(b-a)*t);
          });
          result[key] = `rgb(${c.join(',')})`;
        }
        return result;
      }

      function draw() {
        ctx.save();
        ctx.clearRect(0, 0, width, height);

        if (screenShake > 0 && !reducedMotion && state !== 'paused') {
          const ox = (Math.random() - 0.5) * screenShake * 2;
          const oy = (Math.random() - 0.5) * screenShake * 2;
          ctx.translate(ox, oy);
        }

        const env = getEnvironment(currentStageIndex, distance / STAGE_CONFIGS[currentStageIndex].trackLength);
        drawSky(env);
        drawSoftClouds(env);
        drawLandscape(env);

        // 2. 하이퍼캐주얼 런웨이 트랙 (엠보싱 타일 & 3D 튜브 가드레일)
        const pTL = project3D(-1.0, 1500);
        const pTR = project3D(1.0, 1500);
        const pBL = project3D(-1.0, -120);
        const pBR = project3D(1.0, -120);

        // 트랙 바닥
        const roadGrad = ctx.createLinearGradient(0, pTL.y, 0, pBL.y);
        roadGrad.addColorStop(0, env.road);
        roadGrad.addColorStop(1, env.end);
        ctx.fillStyle = roadGrad;
        ctx.beginPath();
        ctx.moveTo(pTL.x, pTL.y);
        ctx.lineTo(pTR.x, pTR.y);
        ctx.lineTo(pBR.x, pBR.y);
        ctx.lineTo(pBL.x, pBL.y);
        ctx.closePath();
        ctx.fill();

        // 런웨이 엠보싱 타일 스트라이프 (속도감 & 공간 깊이감 극대화)
        for (let z = -80 - (distance % 80); z < 1500; z += 80) {
          const p1L = project3D(-1.0, z);
          const p1R = project3D(1.0, z);
          const p2L = project3D(-1.0, z + 36);
          const p2R = project3D(1.0, z + 36);

          ctx.fillStyle = 'rgba(66, 133, 244, 0.045)';
          ctx.beginPath();
          ctx.moveTo(p1L.x, p1L.y);
          ctx.lineTo(p1R.x, p1R.y);
          ctx.lineTo(p2R.x, p2R.y);
          ctx.lineTo(p2L.x, p2L.y);
          ctx.closePath();
          ctx.fill();
        }

        // 도로 중앙 점선 (차분한 네온 블루 톤)
        ctx.strokeStyle = 'rgba(66, 133, 244, 0.35)';
        ctx.lineWidth = 2.5;
        ctx.setLineDash([14, 20]);
        ctx.beginPath();
        const centerTop = project3D(0, 1500);
        const centerBottom = project3D(0, -120);
        ctx.moveTo(centerTop.x, centerTop.y);
        ctx.lineTo(centerBottom.x, centerBottom.y);
        ctx.stroke();
        ctx.setLineDash([]);

        // 3D 입체 원통형 튜브 가드레일 (Cylindrical Tube Guardrails)
        draw3DTubeGuardrail(pTL, pBL, env);
        draw3DTubeGuardrail(pTR, pBR, env);

        // 3. 지면 충격파 링 (Shockwave Rings on Track Floor)
        shockwaves.forEach(sw => {
          const rel = sw.dist - distance;
          if (rel > -50 && rel < 1400) {
            const p = project3D(sw.trackX, rel);
            ctx.save();
            ctx.strokeStyle = sw.color;
            ctx.globalAlpha = Math.max(0, sw.alpha);
            ctx.lineWidth = Math.max(1.5, 4 * p.scale);
            ctx.beginPath();
            // 바닥에 밀착된 3D 타원형 충격파 링
            ctx.ellipse(p.x, p.y, sw.radius * p.scale * 2.2, sw.radius * p.scale * 0.85, 0, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        });

        // 4. 길가 배경 오브젝트 (야자수 & 바람에 펄럭이는 깃발)
        drawRoadsideProps(env);

        const objects = [];
        activeEnemies.forEach(enemy => {
          const rel = enemy.dist - distance;
          if (!enemy.destroyed && enemy.currentCount > 0 && rel > -45 && rel < 1400)
            objects.push({rel, draw: () => drawEnemyArmy(enemy, rel)});
        });
        activeGates.forEach(gate => {
          const rel = gate.dist - distance;
          if (!gate.passed && rel > -45 && rel < 1400)
            objects.push({rel, draw: () => drawMobControlGate(gate, rel)});
        });
        const finishRel = STAGE_CONFIGS[currentStageIndex].trackLength - distance;
        if (finishRel > -100 && finishRel < 1400)
          objects.push({rel: finishRel, draw: () => drawFinishArch(finishRel)});
        objects.sort((a, b) => b.rel - a.rel).forEach(object => object.draw());

        // 8. 발밑 먼지 파티클
        dustParticles.forEach(pt => {
          ctx.save();
          if (pt.sprite === 'dino' && sprites.dino) {
            ctx.globalAlpha = Math.max(0, pt.life / .65);
            ctx.drawImage(sprites.dino, pt.x - pt.size / 2, pt.y - pt.size, pt.size, pt.size);
            ctx.restore();
            return;
          }
          ctx.fillStyle = pt.color;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, Math.max(1, pt.size * (pt.life / 0.4)), 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        });

        // 9. 플레이어 공룡 군단 (전신 3D 누끼 캐릭터 달리기!)
        drawPlayerArmy();

        // 10. 축하 컨페티(꽃가루) 폭죽
        confettiParticles.forEach(c => {
          ctx.save();
          ctx.translate(c.x, c.y);
          ctx.rotate(c.rotation);
          ctx.fillStyle = c.color;
          ctx.globalAlpha = Math.min(1.0, c.life);
          ctx.fillRect(-c.w / 2, -c.h / 2, c.w, c.h);
          ctx.restore();
        });

        // 11. 3D 팝업 텍스트
        popups.forEach(p => {
          ctx.save();
          ctx.font = '900 20px -apple-system, Pretendard, sans-serif';
          ctx.fillStyle = p.color;
          ctx.globalAlpha = p.alpha;
          ctx.textAlign = 'center';
          ctx.shadowColor = 'rgba(255, 255, 255, 0.95)';
          ctx.shadowBlur = 6;
          ctx.fillText(p.text, p.x, p.y);
          ctx.restore();
        });

        ctx.restore();
      }

      // 3D 입체 원통형 튜브 가드레일 (외곽 파이프 음영 + 상단 반사광)
      function draw3DTubeGuardrail(pTop, pBot, env) {
        ctx.save();
        ctx.lineCap = 'round';
        ctx.strokeStyle = '#b5cbdc'; ctx.lineWidth = 9;
        ctx.beginPath(); ctx.moveTo(pTop.x, pTop.y + 4); ctx.lineTo(pBot.x, pBot.y + 4); ctx.stroke();
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 7;
        ctx.beginPath(); ctx.moveTo(pTop.x, pTop.y); ctx.lineTo(pBot.x, pBot.y); ctx.stroke();
        ctx.strokeStyle = env.accent; ctx.lineWidth = 2;
        ctx.stroke(); ctx.restore();
      }

      // 부드러운 하늘 구름
      function drawSky(env) {
        const sky=ctx.createLinearGradient(0,0,0,height*.58);
        sky.addColorStop(0,env.top);sky.addColorStop(1,env.bottom);
        ctx.fillStyle=sky;ctx.fillRect(0,0,width,height);
        const atmosphere = ctx.createRadialGradient(width*.72,height*.29,0,width*.72,height*.29,width*.65);
        atmosphere.addColorStop(0,env.night>.4?'rgba(145,152,233,.18)':'rgba(255,216,161,.4)');
        atmosphere.addColorStop(1,'rgba(255,230,201,0)');
        ctx.fillStyle=atmosphere;ctx.fillRect(0,0,width,height*.55);
        if(env.night>.35) {
          // Broad translucent ribbons stay behind the stars and the HUD.
          ctx.save();ctx.globalAlpha=(env.night-.35)*.35;
          for(let band=0;band<3;band++) {
            const y=height*(.12+band*.048), drift=reducedMotion?0:Math.sin(worldTime*.16+band)*12;
            const ribbon=ctx.createLinearGradient(0,y,0,y+height*.16);
            ribbon.addColorStop(0,'rgba(121,242,215,0)');ribbon.addColorStop(.5,band%2?'#9da9ff':'#78dfd3');ribbon.addColorStop(1,'rgba(135,172,255,0)');
            ctx.fillStyle=ribbon;ctx.beginPath();ctx.moveTo(-20,y+drift);
            ctx.bezierCurveTo(width*.25,y+height*.12,width*.55,y-height*.07,width+20,y+height*.06);
            ctx.lineTo(width+20,y+height*.14);
            ctx.bezierCurveTo(width*.55,y+height*.03,width*.25,y+height*.2,-20,y+height*.07+drift);ctx.closePath();ctx.fill();
          }ctx.restore();
        }
        // The classic game's notebook grid stays almost invisible behind the scenery.
        ctx.strokeStyle=env.night>.4?'rgba(190,211,255,.045)':'rgba(25,103,210,.035)';ctx.lineWidth=.6;
        for(let x=0;x<width;x+=24){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height*.4);ctx.stroke();}
        for(let y=0;y<height*.4;y+=24){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
        if(env.night>0) {
          ctx.save();
          for(let i=0;i<65;i++) {
            const x=((i*137.508)%997)/997*width, y=((i*73.79)%491)/491*height*.36;
            const alpha=env.night*(.4+.4*Math.sin(i+worldTime*(reducedMotion?0:.8)));
            ctx.globalAlpha=Math.max(0,alpha);ctx.fillStyle=i%4===0?'#b8d6ff':'#fff9db';
            const radius=i%9===0?1.4:.7;
            ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.fill();
            if(i%9===0){ctx.fillRect(x-3,y-.35,6,.7);ctx.fillRect(x-.35,y-3,.7,6);}
          }
          ctx.restore();
        }
        const sx=width*.77, sy=height*(.17+.08*(1-env.night)), r=width*.061;
        const halo=ctx.createRadialGradient(sx,sy,r*.4,sx,sy,r*3.7);
        halo.addColorStop(0,env.night>.4?'rgba(199,211,255,.3)':'rgba(255,217,132,.5)');
        halo.addColorStop(1,'rgba(255,220,160,0)');ctx.fillStyle=halo;
        ctx.beginPath();ctx.arc(sx,sy,r*3.7,0,Math.PI*2);ctx.fill();
        ctx.fillStyle=env.light;ctx.beginPath();ctx.arc(sx,sy,r,0,Math.PI*2);ctx.fill();
        if(env.night>.4){
          ctx.save();ctx.globalAlpha=env.night*.16;ctx.fillStyle='#9e9bc3';
          [[-.3,-.25,.18],[.3,.12,.25],[-.1,.5,.1]].forEach(([x,y,size])=>{ctx.beginPath();ctx.arc(sx+r*x,sy+r*y,r*size,0,Math.PI*2);ctx.fill();});ctx.restore();
        }
      }

      function drawSoftClouds(env) {
        ctx.save();
        const time=reducedMotion?0:worldTime;
        const drift=time*1.5;
        [[.13,.16,23],[.49,.095,13],[.98,.25,18]].forEach(([x,y,r],i)=>{
          const cx=((width*x+drift*(1+i*.3))%(width+100))-35, cy=height*y;
          ctx.globalAlpha=.75-env.night*.53;
          ctx.fillStyle=env.night>.3?'#eedbe9':'#fff';
          ctx.beginPath();ctx.ellipse(cx,cy,r*2.1,r*.47,0,0,Math.PI*2);ctx.fill();
          ctx.beginPath();ctx.arc(cx-r*.4,cy-r*.2,r*.64,0,Math.PI*2);ctx.fill();
          ctx.beginPath();ctx.arc(cx+r*.45,cy-r*.3,r*.8,0,Math.PI*2);ctx.fill();
        });
        // Small distant birds belong to the original runner's outdoor world.
        ctx.globalAlpha=.28*(1-env.night);ctx.strokeStyle='#5675a0';ctx.lineWidth=1.2;
        for(let i=0;i<3;i++){
          const x=width*.23+i*14+Math.sin(time*.1)*10,y=height*.27+Math.sin(i*2)*5;
          const wing=2+Math.sin(time*2+i)*1.2;
          ctx.beginPath();ctx.moveTo(x-4,y-wing);ctx.quadraticCurveTo(x-1,y-2,x,y);ctx.quadraticCurveTo(x+2,y-2,x+4,y-wing);ctx.stroke();
        }
        ctx.restore();
      }

      function drawLandscape(env) {
        ctx.save();
        const horizon=height*.36, time=reducedMotion?0:worldTime;
        const camera=reducedMotion?0:playerCurrentX;
        // Successively darker ridges make the scale of the valley readable.
        for(let layer=0;layer<3;layer++) {
          const shift=-camera*(4+layer*7), base=horizon+layer*height*.021;
          ctx.globalAlpha=.48+layer*.23;ctx.fillStyle=layer===2?env.mid:env.far;
          ctx.beginPath();ctx.moveTo(-40,base);
          for(let i=-1;i<9;i++) {
            const x=i*width*.17+shift;
            const peak=base-height*(.075+Math.sin(i*2.7+layer)*.035)*(1-layer*.15);
            ctx.lineTo(x,peak+height*.026);ctx.lineTo(x+width*.065,peak);ctx.lineTo(x+width*.12,peak+height*.036);
          }
          ctx.lineTo(width+40,base+60);ctx.lineTo(-40,base+60);ctx.closePath();ctx.fill();
        }
        ctx.globalAlpha=1;
        // Hero peaks: faceted rock, a lit face and a small snow cap.
        for(const [px,py,span] of [[.1,.235,.24],[.86,.215,.3]]) {
          const x=width*px-camera*13, y=height*py, w=width*span, base=horizon+height*.06;
          const rock=ctx.createLinearGradient(x,y,x,base);rock.addColorStop(0,env.far);rock.addColorStop(1,env.mid);
          ctx.fillStyle=rock;ctx.beginPath();ctx.moveTo(x-w*.64,base);ctx.lineTo(x-w*.07,y+8);ctx.lineTo(x+w*.12,y);ctx.lineTo(x+w*.9,base);ctx.closePath();ctx.fill();
          ctx.fillStyle='rgba(255,255,255,.2)';ctx.beginPath();ctx.moveTo(x-w*.07,y+8);ctx.lineTo(x+w*.12,y);ctx.lineTo(x+w*.38,base);ctx.lineTo(x-w*.18,base);ctx.closePath();ctx.fill();
          ctx.fillStyle=env.night>.4?'#94a9cb':'#f1f8ff';ctx.globalAlpha=.75;
          ctx.beginPath();ctx.moveTo(x-w*.2,y+height*.033);ctx.lineTo(x-w*.07,y+8);ctx.lineTo(x+w*.12,y);ctx.lineTo(x+w*.3,y+height*.04);ctx.lineTo(x+w*.12,y+height*.029);ctx.lineTo(x+w*.035,y+height*.035);ctx.closePath();ctx.fill();ctx.globalAlpha=1;
        }
        const mist=ctx.createLinearGradient(0,horizon-height*.02,0,horizon+height*.11);
        mist.addColorStop(0,'rgba(235,244,255,0)');mist.addColorStop(.55,env.night>.4?'rgba(137,163,213,.14)':'rgba(244,251,255,.5)');mist.addColorStop(1,'rgba(235,244,255,0)');
        ctx.fillStyle=mist;ctx.fillRect(0,horizon-height*.02,width,height*.13);
        // The track crosses a glassy alpine lake.
        const lake=ctx.createLinearGradient(0,horizon,0,height);
        lake.addColorStop(0,env.water);lake.addColorStop(.65,env.mid);lake.addColorStop(1,env.water);
        ctx.fillStyle=lake;ctx.fillRect(0,horizon+height*.045,width,height);
        const shimmer=ctx.createLinearGradient(0,horizon,0,height*.8);
        shimmer.addColorStop(0,'rgba(255,244,208,0)');shimmer.addColorStop(.35,env.night>.4?'rgba(213,228,255,.19)':'rgba(255,248,217,.42)');shimmer.addColorStop(1,'rgba(255,244,208,0)');
        ctx.fillStyle=shimmer;ctx.beginPath();ctx.moveTo(width*.76,horizon);ctx.lineTo(width*.56,height*.9);ctx.lineTo(width*1.05,height*.9);ctx.lineTo(width*.79,horizon);ctx.closePath();ctx.fill();
        for(let i=0;i<45;i++) {
          const depth=i/45, y=horizon+height*.055+depth*depth*height*.55;
          const x=((i*137.5+time*(2+depth*4))%(width+50))-25;
          ctx.strokeStyle=i%3===0?'rgba(255,245,216,.48)':'rgba(222,242,255,.28)';ctx.lineWidth=.7+depth;
          ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+5+depth*22,y);ctx.stroke();
        }
        // Shore terraces and waterfalls flank the clear central play corridor.
        [-1,1].forEach(side=>{
          const x=side<0?width*.055-camera*19:width*.94-camera*19;
          const y=horizon+height*(side<0?.08:.12), w=width*.28;
          ctx.fillStyle=env.far;ctx.beginPath();ctx.ellipse(x,y+height*.058,w*.55,height*.026,0,0,Math.PI*2);ctx.fill();
          ctx.fillStyle=env.mid;ctx.beginPath();ctx.moveTo(x-w*.58,y);ctx.lineTo(x+w*.55,y);ctx.lineTo(x+w*.38,y+height*.062);ctx.lineTo(x-w*.45,y+height*.071);ctx.closePath();ctx.fill();
          ctx.fillStyle='rgba(24,49,78,.16)';ctx.beginPath();ctx.moveTo(x+w*.13,y);ctx.lineTo(x+w*.55,y);ctx.lineTo(x+w*.38,y+height*.062);ctx.lineTo(x+w*.05,y+height*.06);ctx.closePath();ctx.fill();
          ctx.fillStyle=env.land;ctx.beginPath();ctx.ellipse(x,y,w*.58,height*.025,0,0,Math.PI*2);ctx.fill();
          const fallsX=x+side*width*.025, fallsY=y+height*.006, fallHeight=height*.075;
          const falls=ctx.createLinearGradient(0,fallsY,0,fallsY+fallHeight);
          falls.addColorStop(0,'rgba(237,251,255,.85)');falls.addColorStop(1,'rgba(165,225,248,.14)');ctx.fillStyle=falls;
          ctx.beginPath();ctx.moveTo(fallsX-4,fallsY);ctx.lineTo(fallsX+5,fallsY);ctx.lineTo(fallsX+10,fallsY+fallHeight);ctx.lineTo(fallsX-8,fallsY+fallHeight);ctx.closePath();ctx.fill();
          ctx.strokeStyle='rgba(241,253,255,.6)';ctx.lineWidth=1;
          for(let j=0;j<3;j++){const yy=fallsY+(j*.025*height+time*14)%fallHeight;ctx.beginPath();ctx.moveTo(fallsX-2+j*2,yy);ctx.lineTo(fallsX-2+j*2,Math.min(fallsY+fallHeight,yy+7));ctx.stroke();}
          ctx.fillStyle='rgba(219,245,255,.4)';ctx.beginPath();ctx.ellipse(fallsX,fallsY+fallHeight,15,3,0,0,Math.PI*2);ctx.fill();
          for(let j=0;j<7;j++) {
            const tx=x+(j-3)*w*.11, ty=y-3+Math.sin(j*2)*3, size=9+(j%3)*4;
            ctx.fillStyle=env.night>.4?'#344f69':'#4f9487';ctx.fillRect(tx-1,ty-6,2,7);
            ctx.beginPath();ctx.moveTo(tx,ty-size*1.6);ctx.lineTo(tx-size*.5,ty-2);ctx.lineTo(tx+size*.5,ty-2);ctx.closePath();ctx.fill();
            ctx.fillStyle='rgba(216,255,232,.18)';ctx.beginPath();ctx.moveTo(tx,ty-size*1.6);ctx.lineTo(tx,ty-2);ctx.lineTo(tx-size*.5,ty-2);ctx.closePath();ctx.fill();
          }
        });
        // Tiny lakeside observatory gives the world a recognisable landmark.
        const ox=width*.9-camera*8, oy=horizon+height*.035, r=width*.026;
        ctx.fillStyle=env.night>.4?'#657d9f':'#edf6fa';ctx.fillRect(ox-r,oy-r,r*2,r);
        ctx.beginPath();ctx.arc(ox,oy-r,r,Math.PI,Math.PI*2);ctx.fill();
        ctx.fillStyle=env.night>.4?'#ffe0a1':'#7badc8';ctx.fillRect(ox-r*.5,oy-r*.75,r*.35,r*.5);ctx.fillRect(ox+r*.2,oy-r*.75,r*.35,r*.5);
        if(env.night<.4) {
          const bx=width*.18-camera*4+Math.sin(time*.08)*8, by=height*.2+Math.sin(time*.3)*3, br=width*.024;
          ctx.strokeStyle='#93a3b6';ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(bx-br*.5,by+br*.5);ctx.lineTo(bx-2,by+br*1.6);ctx.moveTo(bx+br*.5,by+br*.5);ctx.lineTo(bx+2,by+br*1.6);ctx.stroke();
          ctx.fillStyle='#f3b875';ctx.beginPath();ctx.ellipse(bx,by,br,br*1.2,0,0,Math.PI*2);ctx.fill();
          ctx.fillStyle='#fff1d5';ctx.beginPath();ctx.ellipse(bx,by,br*.35,br*1.2,0,0,Math.PI*2);ctx.fill();
          ctx.fillStyle='#b69372';ctx.fillRect(bx-2.5,by+br*1.5,5,4);
        }
        ctx.restore();
      }

      // 길가 가로수 및 바람에 펄럭이는 구글 4색 깃발
      function drawRoadsideProps(env) {
        const time = worldTime * (reducedMotion ? 0 : 3);
        [...roadsideProps].reverse().forEach(prop => {
          const rel = prop.dist - distance;
          if (rel < -100 || rel > 1400) return;
          const p = project3D(prop.side * 1.3, rel), sc = p.scale;
          const seed = Math.abs(Math.floor(prop.dist / 90));
          const darkLeaves = env.night > .4;
          ctx.save();

          // Low planted banks and faceted stones anchor every prop to the terrain.
          ctx.fillStyle=darkLeaves?'rgba(40,66,87,.28)':'rgba(63,128,91,.22)';
          ctx.beginPath();ctx.ellipse(p.x,p.y+2*sc,24*sc,7*sc,0,0,Math.PI*2);ctx.fill();
          ctx.fillStyle=darkLeaves?'#61778c':'#79b68a';
          ctx.beginPath();ctx.ellipse(p.x-3*sc,p.y,19*sc,5*sc,0,0,Math.PI*2);ctx.fill();
          ctx.fillStyle=darkLeaves?'#71839a':'#8fa7a0';
          ctx.beginPath();ctx.moveTo(p.x-18*sc,p.y+1*sc);ctx.lineTo(p.x-13*sc,p.y-7*sc);ctx.lineTo(p.x-5*sc,p.y+2*sc);ctx.closePath();ctx.fill();
          ctx.fillStyle='rgba(255,255,255,.24)';
          ctx.beginPath();ctx.moveTo(p.x-13*sc,p.y-7*sc);ctx.lineTo(p.x-9*sc,p.y-2*sc);ctx.lineTo(p.x-5*sc,p.y+2*sc);ctx.closePath();ctx.fill();

          if (prop.type === 'tree') {
            const sway = Math.sin(time * .55 + seed) * 1.4 * sc;
            ctx.fillStyle=darkLeaves?'#746e69':'#8c745f';
            roundRect(ctx,p.x-3*sc,p.y-39*sc,6*sc,39*sc,2*sc);ctx.fill();
            ctx.fillStyle='rgba(255,255,255,.2)';
            roundRect(ctx,p.x-2*sc,p.y-37*sc,1.5*sc,30*sc,1*sc);ctx.fill();

            if (seed % 3 === 0) {
              const pineLayers=[[p.y-67*sc,20],[p.y-55*sc,25],[p.y-42*sc,29]];
              pineLayers.forEach(([y,half],index)=>{
                ctx.fillStyle=darkLeaves
                  ? ['#7791a7','#5f7d96','#476983'][index]
                  : ['#a4d9ae','#79bd94','#55a77f'][index];
                ctx.beginPath();ctx.moveTo(p.x+sway,y);ctx.lineTo(p.x-half*sc,y+28*sc);ctx.lineTo(p.x+half*sc,y+28*sc);ctx.closePath();ctx.fill();
                ctx.fillStyle='rgba(255,255,255,.16)';
                ctx.beginPath();ctx.moveTo(p.x+sway,y+2*sc);ctx.lineTo(p.x-half*sc,y+28*sc);ctx.lineTo(p.x-4*sc,y+22*sc);ctx.closePath();ctx.fill();
              });
            } else {
              const leaf=ctx.createLinearGradient(p.x-22*sc,0,p.x+22*sc,0);
              leaf.addColorStop(0,darkLeaves?'#7894ab':'#a6d9b2');
              leaf.addColorStop(.52,darkLeaves?'#5c7893':'#75bd95');
              leaf.addColorStop(1,darkLeaves?'#405f7b':'#50a27c');ctx.fillStyle=leaf;
              [[-11,-49,14],[8,-53,16],[0,-64,14]].forEach(([x,y,r])=>{
                ctx.beginPath();ctx.arc(p.x+x*sc+sway,p.y+y*sc,r*sc,0,Math.PI*2);ctx.fill();
              });
              ctx.fillStyle='rgba(255,255,255,.22)';
              ctx.beginPath();ctx.arc(p.x-8*sc+sway,p.y-62*sc,6*sc,0,Math.PI*2);ctx.fill();
            }
          } else {
            const colors=['#4285f4','#eaaa41','#67b58b','#dc8770'];
            const flutter=Math.sin(time+prop.dist*.02)*2*sc;
            ctx.fillStyle=darkLeaves?'#d8e3ec':'#fff';roundRect(ctx,p.x-1.5*sc,p.y-49*sc,3*sc,49*sc,1.5*sc);ctx.fill();
            [0,1].forEach(i=>{
              const y=p.y-(47-i*13)*sc;
              ctx.fillStyle=colors[(seed+i)%4];
              ctx.beginPath();ctx.moveTo(p.x,y);ctx.lineTo(p.x+(18-i*3)*sc,y+3*sc+flutter*(i?-.5:1));ctx.lineTo(p.x,y+9*sc);ctx.closePath();ctx.fill();
              ctx.fillStyle='rgba(255,255,255,.2)';ctx.beginPath();ctx.moveTo(p.x+2*sc,y+2*sc);ctx.lineTo(p.x+12*sc,y+4*sc+flutter*.35);ctx.lineTo(p.x+2*sc,y+5*sc);ctx.closePath();ctx.fill();
            });
          }

          if (sc > .28 && seed % 2 === 0) {
            ['#fff5c7','#f3a7b9','#d4c2ff'].forEach((color,index)=>{
              const fx=p.x+(6+index*6)*sc*(prop.side<0?-1:1),fy=p.y-(2+index%2)*sc;
              ctx.strokeStyle=darkLeaves?'#77958a':'#4f9d72';ctx.lineWidth=Math.max(.6,sc);ctx.beginPath();ctx.moveTo(fx,fy+4*sc);ctx.lineTo(fx,fy);ctx.stroke();
              ctx.fillStyle=color;ctx.beginPath();ctx.arc(fx,fy,1.8*sc,0,Math.PI*2);ctx.fill();
            });
          }

          if(env.night>.12 && seed % 2 === 1) {
            const lx=p.x-12*sc*(prop.side<0?-1:1), ly=p.y-24*sc;
            ctx.globalAlpha=env.night;
            ctx.fillStyle='#4d6175';roundRect(ctx,lx-1.25*sc,ly,2.5*sc,24*sc,1.2*sc);ctx.fill();
            const flicker=reducedMotion?1:.92+Math.sin(time*2.2+seed)*.08;
            const glow=ctx.createRadialGradient(lx,ly,0,lx,ly,18*sc);
            glow.addColorStop(0,`rgba(255,224,154,${.72*flicker})`);glow.addColorStop(1,'rgba(255,217,139,0)');
            ctx.fillStyle=glow;ctx.beginPath();ctx.arc(lx,ly,18*sc,0,Math.PI*2);ctx.fill();
            ctx.fillStyle='#44596d';roundRect(ctx,lx-4*sc,ly-5*sc,8*sc,8*sc,2*sc);ctx.fill();
            ctx.fillStyle='#fff0b8';roundRect(ctx,lx-2.5*sc,ly-3.5*sc,5*sc,5*sc,1.5*sc);ctx.fill();
          }
          ctx.restore();
        });
      }

      // ==========================================
      // Mob Control 시그니처 3D 아치 게이트 (Arch Gate Overhaul)
      // 메탈릭 3D 기둥, 반투명 네온 에너지 실드, 스캐닝 라이트 펄스, 3D 압출 볼드 타이포그래피
      // ==========================================
      function drawMobControlGate(gate, relDist) {
        const left = project3D(-.95, relDist), right = project3D(.95, relDist);
        const sc = left.scale, gap = 8 * sc, w = (right.x-left.x-gap)/2, h = 115*sc;
        ctx.save();
        ctx.fillStyle='rgba(54,83,124,.1)';
        ctx.beginPath();ctx.ellipse(width/2,left.y+5*sc,(right.x-left.x)/2,12*sc,0,0,Math.PI*2);ctx.fill();
        const choices = getGateChoices(gate);
        drawGateHalf(left.x,left.y-h,w,h,choices.left,sc,relDist);
        drawGateHalf(left.x+w+gap,left.y-h,w,h,choices.right,sc,relDist);
        if (gate.swapPeriod && sc > .26) {
          const seconds = Math.max(0, gate.swapPeriod - gate.phase % gate.swapPeriod).toFixed(1);
          const status = gate.locked ? '선택 고정' : `↔ ${seconds}s 후 교대`;
          const badgeWidth = 122 * sc;
          ctx.fillStyle = '#f4f8ff'; ctx.strokeStyle = '#287ce4'; ctx.lineWidth = Math.max(1, sc);
          roundRect(ctx, width/2-badgeWidth/2, left.y-h-24*sc, badgeWidth, 20*sc, 6*sc);ctx.fill();ctx.stroke();
          ctx.fillStyle='#2465b7';ctx.textAlign='center';ctx.textBaseline='middle';
          ctx.font=`800 ${Math.max(8,10*sc)}px sans-serif`;
          ctx.fillText(status,width/2,left.y-h-14*sc);
        }
        ctx.restore();
      }

      // 게이트 절반 (홀로그램 에너지 실드 & 스캐닝 라이트 & 3D 볼드 폰트)
      function drawGateHalf(x, y, w, h, data, scale, relDist) {
        ctx.save();
        const color = '#287ce4';
        const lower = '#d8eaff';
        // Thick softly bevelled frame, tinted clear interior, oversized arithmetic.
        ctx.fillStyle='#aac7e8';
        roundRect(ctx,x+3*scale,y+5*scale,w,h,10*scale);ctx.fill();
        const glass=ctx.createLinearGradient(0,y,0,y+h);
        glass.addColorStop(0,'#ffffff');glass.addColorStop(1,lower);
        ctx.fillStyle=glass;roundRect(ctx,x,y,w,h,10*scale);ctx.fill();
        ctx.strokeStyle=color;ctx.lineWidth=Math.max(1,3*scale);ctx.stroke();
        ctx.fillStyle=color;roundRect(ctx,x,y,w,23*scale,[9*scale,9*scale,0,0]);ctx.fill();
        ctx.textAlign='center';ctx.textBaseline='middle';
        if(scale > .35) {
          ctx.fillStyle='#fff';ctx.font=`700 ${Math.max(7,9*scale)}px sans-serif`;
          ctx.fillText(data.op === 'chain' ? '연속 계산' : data.op === 'set' ? '인원 고정' : 'GATE',x+w/2,y+12*scale);
        }
        ctx.font=`900 ${Math.max(11,(data.op === 'chain' ? 27 : 39)*scale)}px -apple-system, sans-serif`;
        ctx.fillStyle=color;
        ctx.fillText(formatGateOption(data),x+w/2,y+h*.55);
        if(scale>.45) {
          ctx.font=`600 ${10*scale}px sans-serif`;ctx.fillStyle='#5884b7';
          ctx.fillText(data.op === 'chain' ? '왼쪽부터 차례로' : data.op === 'set' ? '현재 인원과 교체' : '공룡 수 계산',x+w/2,y+h*.82);
        }
        ctx.strokeStyle='rgba(255,255,255,.85)';ctx.lineWidth=2*scale;
        ctx.beginPath();ctx.moveTo(x+7*scale,y+29*scale);ctx.lineTo(x+7*scale,y+h-12*scale);ctx.stroke();
        ctx.restore();
      }

      // 메탈릭 3D 원통형 기둥 & 상단 발광 돔 LED
      function drawMetallicPillar(x, y, w, h, isGood, scale) {
        ctx.save();
        const halfW = w / 2;

        // 원통 메탈릭 그라데이션
        const pGrad = ctx.createLinearGradient(x - halfW, 0, x + halfW, 0);
        pGrad.addColorStop(0, '#0f172a');
        pGrad.addColorStop(0.35, '#94a3b8');
        pGrad.addColorStop(0.7, '#cbd5e1');
        pGrad.addColorStop(1, '#1e293b');

        ctx.fillStyle = pGrad;
        roundRect(ctx, x - halfW, y, w, h, 3);
        ctx.fill();

        // 상단 돔 LED 캡 (보너스는 청록 보석, 패널티는 레드 보석)
        ctx.fillStyle = isGood ? '#38bdf8' : '#ef4444';
        ctx.beginPath();
        ctx.arc(x, y, halfW * 1.15, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.2 * scale;
        ctx.stroke();
        ctx.restore();
      }

      // Claude units patrol independently, then make a readable lateral pursuit
      // when the player gets close. Contact locks their lane so combat stays fair.
      function updateEnemyMotion(enemy, dt) {
        if (!enemy || enemy.destroyed || enemy.currentCount <= 0) return;

        if (!Number.isFinite(enemy.motionOriginX)) enemy.motionOriginX = enemy.x;
        if (!Number.isFinite(enemy.motionPhase)) {
          enemy.motionPhase = ((enemy.initialDist || enemy.dist || 0) * 0.013 + enemy.motionOriginX * 5) % (Math.PI * 2);
        }
        if (!Number.isFinite(enemy.motionTargetX)) enemy.motionTargetX = enemy.x;

        const rel = enemy.dist - distance;
        const contactLocked = Math.abs(rel) <= 60;
        if (contactLocked) {
          enemy.motionMode = 'contact';
          enemy.motionTargetX = enemy.x;
          return;
        }

        const guardian = enemy.speed === 0;
        const phaseSpeed = guardian ? 0.72 : 0.9 + currentStageIndex * 0.06;
        enemy.motionPhase += dt * phaseSpeed;

        const patrolRadius = guardian ? 0.2 : Math.min(0.2, 0.1 + enemy.widthSpan * 0.08);
        let desiredX = enemy.motionOriginX + Math.sin(enemy.motionPhase) * patrolRadius;
        enemy.motionMode = guardian ? 'guardian' : 'patrol';

        if (!guardian && rel > 60 && rel < 800) {
          const pursuitLimit = 0.9;
          const pursuedX = Math.max(
            enemy.motionOriginX - pursuitLimit,
            Math.min(enemy.motionOriginX + pursuitLimit, playerCurrentX)
          );
          // Blend pursuit in over distance so the lane change telegraphs instead of snapping.
          const pursuitWeight = Math.max(0, Math.min(1, (800 - rel) / 540));
          desiredX += (pursuedX - desiredX) * pursuitWeight;
          enemy.motionMode = 'pursuit';
        }

        desiredX = Math.max(-0.62, Math.min(0.62, desiredX));
        const targetEase = 1 - Math.exp(-dt * (guardian ? 1.25 : 1.7));
        const moveEase = 1 - Math.exp(-dt * (guardian ? 1.7 : 2.25));
        enemy.motionTargetX += (desiredX - enemy.motionTargetX) * targetEase;
        enemy.x += (enemy.motionTargetX - enemy.x) * moveEase;
        enemy.x = Math.max(-0.62, Math.min(0.62, enemy.x));
      }

      // 🤖 Anthropic Claude 적군 (전신 나노바나나 로봇 군단 & 거대 보스 레이드!)
      function drawEnemyArmy(enemy, relDist) {
        const p = project3D(enemy.x, relDist), sc=p.scale, count=enemy.currentCount;
        const time = worldTime * (reducedMotion ? 0 : 9);
        ctx.save();
        const visible=Math.min(count,21), cols=Math.min(7,visible), rows=Math.ceil(visible/cols);
        const units=[];
        if (enemy.isBoss) {
          units.push({x:p.x,y:p.y,size:112*sc,phase:Math.sin(time),boss:true});
          const escorts=Math.min(6,Math.max(0,visible-1));
          for(let i=0;i<escorts;i++) {
            const side=i%2===0?-1:1, rank=Math.floor(i/2)+1;
            const stride=Math.sin(time*.83+i*1.71);
            units.push({
              x:p.x+side*(43+rank*18+stride*3)*sc,
              y:p.y+(8+rank*7+Math.cos(time*.7+i)*3)*sc,
              size:(34+rank)*sc,phase:stride,boss:false
            });
          }
        } else {
          for(let i=0;i<visible;i++) {
            const row=Math.floor(i/cols), n=Math.min(cols,visible-row*cols);
            const col=i%cols, seed=(i+1)*1.618+(enemy.motionPhase||0);
            const stride=Math.sin(time*(.82+(i%3)*.06)+seed);
            const looseX=Math.sin(seed*2.13)*5+stride*2.5;
            const looseY=Math.cos(seed*1.47)*3+Math.abs(stride)*2;
            units.push({
              x:p.x+(col-(n-1)/2)*25*sc+looseX*sc,
              y:p.y+(row-(rows-1))*16*sc+looseY*sc,
              size:(39+(i%4))*sc,phase:stride,boss:false
            });
          }
        }
        units.sort((a,b)=>a.y-b.y).forEach(unit =>
          drawClaudeEnemyUnit(unit.x,unit.y,unit.size,unit.phase,unit.boss));
        const by=p.y-(enemy.isBoss?112:52+(rows-1)*17)*sc;
        const bw=(enemy.isBoss?174:136)*sc, bh=24*sc;
        ctx.fillStyle='#fff8f3';ctx.strokeStyle='#d58c72';ctx.lineWidth=Math.max(1,1.5*sc);
        roundRect(ctx,p.x-bw/2,by,bw,bh,8*sc);ctx.fill();ctx.stroke();
        ctx.fillStyle='#a45036';ctx.textAlign='center';ctx.textBaseline='middle';
        ctx.font=`800 ${Math.max(8,12*sc)}px sans-serif`;
        const motionLabel=enemy.motionMode==='pursuit'?'추격':enemy.motionMode==='guardian'?'수문장':enemy.motionMode==='contact'?'교전':'순찰';
        ctx.fillText((enemy.isBoss?'BOSS  ':'CLAWD  ')+count+' · '+motionLabel,p.x,by+bh/2);
        const barW=bw-10*sc;
        ctx.fillStyle='#efd4c7';roundRect(ctx,p.x-barW/2,by+bh+4*sc,barW,4*sc,2*sc);ctx.fill();
        ctx.fillStyle='#d97757';roundRect(ctx,p.x-barW/2,by+bh+4*sc,barW*count/enemy.totalCount,4*sc,2*sc);ctx.fill();
        ctx.restore();
      }

      // 🤖 공식 Claude Code 3D 픽셀 로봇 캐릭터 스프라이트 렌더러
      function drawClaudeEnemyUnit(x, y, size, runPhase, isBoss = false) {
        ctx.save();
        const bounce=Math.abs(runPhase)*size*.08;
        ctx.fillStyle='rgba(117,67,44,.13)';ctx.beginPath();ctx.ellipse(x,y+2,size*.43,size*.13,0,0,Math.PI*2);ctx.fill();
        ctx.translate(x,y-bounce);ctx.rotate(runPhase*.04);
        const sprite=sprites.claude;
        const ratio=(sprite.naturalHeight||sprite.height)/(sprite.naturalWidth||sprite.width);
        const w=size*1.25,h=w*ratio;
        ctx.drawImage(sprite,-w/2,-h*.88,w,h);
        if(isBoss) {
          // Draw the crown as geometry, consistent across platforms.
          ctx.fillStyle='#f4bb44';ctx.strokeStyle='#c88824';ctx.lineWidth=1.5;
          ctx.beginPath();ctx.moveTo(-size*.2,-h*.85);ctx.lineTo(-size*.25,-h*1.07);
          ctx.lineTo(-size*.08,-h*.98);ctx.lineTo(0,-h*1.13);ctx.lineTo(size*.09,-h*.98);
          ctx.lineTo(size*.25,-h*1.07);ctx.lineTo(size*.2,-h*.85);ctx.closePath();ctx.fill();ctx.stroke();
        }
        ctx.restore();
      }

      function drawFinishArch(relDist) {
        const pL = project3D(-1.0, relDist);
        const pR = project3D(1.0, relDist);
        const pC = project3D(0, relDist);
        const archH = 120 * pC.scale;

        ctx.save();
        ctx.fillStyle = '#FBBC04';
        ctx.fillRect(pL.x - 3, pL.y - archH, 6 * pC.scale, archH);
        ctx.fillRect(pR.x - 3, pR.y - archH, 6 * pC.scale, archH);

        ctx.fillStyle = '#1a73e8';
        ctx.fillRect(pL.x, pL.y - archH, pR.x - pL.x, 30 * pC.scale);

        ctx.fillStyle = '#ffffff';
        ctx.font = `bold ${Math.max(9, 16 * pC.scale)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🏁 FINISH 🏁', pC.x, pL.y - archH + (15 * pC.scale));
        ctx.restore();
      }

      // Depth-sort the flock while each dinosaur follows its own path.
      function drawPlayerArmy() {
        const count = Math.min(playerArmy.length, MAX_VISIBLE_ARMY);
        if (!count) return;
        const p = project3D(playerCurrentX, 0);
        const size = count === 1 ? 76 : count < 8 ? 51 : count < 24 ? 43 : count < 50 ? 36 : 30;
        const margin = (count === 1 ? 0 : Math.min(width * 0.24, 12 * Math.sqrt(count))) + size / 2 + 12;
        const units = playerArmy.slice(0, count).map(unit => {
          const anchor = project3D(unit.followX, 0);
          const centerX = Math.max(margin, Math.min(width - margin, anchor.x));
          return { unit, x: centerX + unit.offsetX,
            y: p.y + unit.offsetY };
        }).sort((a, b) => a.y - b.y);
        ctx.save();
        for (const {unit, x, y} of units) {
          const phase = reducedMotion ? 0 : worldTime * (10 + currentStageIndex * 1.3) + unit.animSeed;
          const growth = reducedMotion ? 1 : 0.4 + 0.6 * unit.spawnProgress;
          ctx.globalAlpha = 0.35 + 0.65 * unit.spawnProgress;
          drawRunningDino(x, y, size * growth, phase);
        }
        ctx.globalAlpha = 1;
        const cx = Math.max(margin, Math.min(width - margin, p.x));
        const by = p.y - (count === 1 ? 98 : 74), label = String(playerArmy.length), bw = 58 + label.length * 7;
        ctx.fillStyle='#2475df';roundRect(ctx,cx-bw/2,by,bw,27,13);ctx.fill();
        ctx.fillStyle='#fff';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='800 15px sans-serif';
        ctx.fillText(label,cx,by+14);
        ctx.beginPath();ctx.moveTo(cx-4,by+26);ctx.lineTo(cx,by+31);ctx.lineTo(cx+4,by+26);ctx.fill();
        ctx.restore();
      }

      // Original blue pixel dinosaur, with individual footfall and body sway.
      function drawRunningDino(x, y, size, runPhase) {
        ctx.save();

        const bounce = Math.abs(Math.sin(runPhase)) * (size * 0.09);
        const waddle = Math.sin(runPhase) * 0.08;
        const groundY = y;
        const charY = y - bounce;

        // 발밑 소프트 타원 그림자
        const shadowScale = Math.max(0.6, 1.0 - (bounce / (size * 0.5)));
        ctx.fillStyle = 'rgba(26, 115, 232, 0.24)';
        ctx.beginPath();
        ctx.ellipse(x, groundY + 2, size * 0.42 * shadowScale, size * 0.16 * shadowScale, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.translate(x, charY);
        ctx.rotate(waddle);

        if (sprites.loaded && sprites.dino) {
          // 전신 공룡 누끼 스프라이트!
          const w = size;
          const h = size;
          ctx.drawImage(sprites.dino, -w * 0.5, -h * 0.96, w, h);
        } else {
          // Blue pixel silhouette while the original asset loads.
          ctx.fillStyle = '#1a8cff';
          roundRect(ctx, -size * 0.4, -size * 0.8, size * 0.8, size * 0.8, 6);
          ctx.fill();
        }

        ctx.restore();
      }

      function drawRunningHeart(x, y, size, runPhase) {
        ctx.save();
        const bounce = Math.abs(Math.sin(runPhase)) * 3;
        const groundY = y;
        const charY = y - bounce;

        // 그림자
        ctx.fillStyle = 'rgba(233, 30, 99, 0.2)';
        ctx.beginPath();
        ctx.ellipse(x, groundY + 2, 8, 3, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.translate(x, charY);
        ctx.font = `${Math.floor(size)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('❤️', 0, -size * 0.4);

        ctx.restore();
      }

      function roundRect(ctx, x, y, width, height, radius) {
        let r = radius;
        if (typeof r === 'number') {
          r = [r, r, r, r];
        } else if (Array.isArray(r) && r.length === 2) {
          r = [r[0], r[1], r[0], r[1]];
        }
        r = r.map(value => Math.max(0, Math.min(value, width / 2, height / 2)));
        ctx.beginPath();
        ctx.moveTo(x + r[0], y);
        ctx.lineTo(x + width - r[1], y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + r[1]);
        ctx.lineTo(x + width, y + height - r[2]);
        ctx.quadraticCurveTo(x + width, y + height, x + width - r[2], y + height);
        ctx.lineTo(x + r[3], y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - r[3]);
        ctx.lineTo(x, y + r[0]);
        ctx.quadraticCurveTo(x, y, x + r[0], y);
        ctx.closePath();
      }

      function loop(now) {
        const dt = Math.min((now - lastTime) / 1000, 0.1);
        lastTime = now;
        const steps = Math.max(1, Math.ceil(dt * 60));
        for (let i = 0; i < steps; i++) update(dt / steps);
        draw();
        requestAnimationFrame(loop);
      }
      requestAnimationFrame(loop);

      initStage(0, null);
      state = 'ready';
      new ResizeObserver(() => { resize(); updateArmyOffsets(); }).observe(viewport);
    })();
