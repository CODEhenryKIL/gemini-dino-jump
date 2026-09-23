/**
 * Canvas Silver Coating Scratch Card Component for v1.1
 * Features: Touch/Mouse drag, Scratch sound, 50% auto-reveal, Instant reveal button, Touch scroll lock
 */

import { audio } from '../game/audio.js';

export class ScratchCard {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d', { willReadFrequently: true });
    this.onReveal = options.onReveal || (() => {});
    this.autoRevealThreshold = options.threshold || 0.70; // 70% 긁는 손맛 강화

    this.isDrawing = false;
    this.isRevealed = false;
    this.scratchStrokeCount = 0;

    this.setupCanvas();
    this.initCoating();
    this.bindEvents();
  }

  setupCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.width = rect.width || 316;
    this.height = rect.height || 140;
    this.canvas.width = this.width;
    this.canvas.height = this.height;
  }

  initCoating() {
    const ctx = this.ctx;
    ctx.globalCompositeOperation = 'source-over';

    // Metallic silver gradient
    const grad = ctx.createLinearGradient(0, 0, this.width, this.height);
    grad.addColorStop(0, '#C0C0C0');
    grad.addColorStop(0.3, '#E0E0E0');
    grad.addColorStop(0.5, '#F5F5F5');
    grad.addColorStop(0.7, '#D4D4D4');
    grad.addColorStop(1, '#A8A8A8');

    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, this.width, this.height);

    // Decorative sparkles & grid pattern
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    for (let x = 10; x < this.width; x += 20) {
      for (let y = 10; y < this.height; y += 20) {
        ctx.beginPath();
        ctx.arc(x, y, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Centered instruction text
    ctx.fillStyle = '#555555';
    ctx.font = 'bold 15px -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('✨ 살살 긁어서 행운 확인 ✨', this.width / 2, this.height / 2);
  }

  bindEvents() {
    const getPos = (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return {
        x: clientX - rect.left,
        y: clientY - rect.top
      };
    };

    this.startScratchHandler = (e) => {
      if (this.isRevealed) return;
      this.isDrawing = true;
      e.preventDefault();
      const pos = getPos(e);
      this.scratch(pos.x, pos.y);
    };

    this.moveScratchHandler = (e) => {
      if (!this.isDrawing || this.isRevealed) return;
      e.preventDefault();
      const pos = getPos(e);
      this.scratch(pos.x, pos.y);
    };

    this.endScratchHandler = () => {
      this.isDrawing = false;
    };

    this.canvas.addEventListener('mousedown', this.startScratchHandler);
    window.addEventListener('mousemove', this.moveScratchHandler);
    window.addEventListener('mouseup', this.endScratchHandler);

    this.canvas.addEventListener('touchstart', this.startScratchHandler, { passive: false });
    window.addEventListener('touchmove', this.moveScratchHandler, { passive: false });
    window.addEventListener('touchend', this.endScratchHandler);
  }

  scratch(x, y) {
    const ctx = this.ctx;
    ctx.globalCompositeOperation = 'destination-out';

    ctx.beginPath();
    ctx.arc(x, y, 24, 0, Math.PI * 2);
    ctx.fill();

    this.scratchStrokeCount++;
    const now = performance.now();

    // 1. Tactile Haptic Vibration Feedback (Web Vibration API)
    // Fires every 45ms for a realistic physical paper-scratching friction feel
    if (!this.lastVibrateTime || (now - this.lastVibrateTime >= 45)) {
      this.lastVibrateTime = now;
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        try {
          navigator.vibrate(12); // Crisp 12ms coin scratch tick
        } catch (e) {}
      }
    }

    // 2. Realistic Paper Scratch Sound & Area Check
    if (this.scratchStrokeCount % 3 === 0) {
      audio.playScratch();
      this.checkRevealedArea();
    }
  }

  checkRevealedArea() {
    if (this.isRevealed) return;

    // Sample every 4th pixel for high performance calculation
    const imgData = this.ctx.getImageData(0, 0, this.width, this.height);
    const data = imgData.data;
    let transparentPixels = 0;
    const totalSampled = data.length / 16;

    for (let i = 3; i < data.length; i += 16) {
      if (data[i] < 128) {
        transparentPixels++;
      }
    }

    const ratio = transparentPixels / totalSampled;
    if (ratio >= this.autoRevealThreshold) {
      this.revealInstantly();
    }
  }

  revealInstantly() {
    if (this.isRevealed) return;
    this.isRevealed = true;
    this.canvas.classList.add('fade-out');

    // Celebration Haptic Vibration Pattern (Tap-Tap-Boom!)
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      try {
        navigator.vibrate([35, 45, 50, 45, 100]);
      } catch (e) {}
    }

    audio.playWin();
    this.revealTimer = setTimeout(() => {
      this.onReveal();
    }, 300);
  }

  destroy() {
    clearTimeout(this.revealTimer);
    this.revealTimer = null;
    this.canvas.removeEventListener('mousedown', this.startScratchHandler);
    this.canvas.removeEventListener('touchstart', this.startScratchHandler);
    window.removeEventListener('mousemove', this.moveScratchHandler);
    window.removeEventListener('mouseup', this.endScratchHandler);
    window.removeEventListener('touchmove', this.moveScratchHandler);
    window.removeEventListener('touchend', this.endScratchHandler);
    this.isDrawing = false;
    this.onReveal = () => {};
  }
}
