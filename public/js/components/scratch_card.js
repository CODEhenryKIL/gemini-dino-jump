/**
 * Canvas Silver Coating Scratch Card Component for v1.1
 * Features: Touch/Mouse drag, Scratch sound, 70% auto-reveal, Instant reveal button, Touch scroll lock
 */

import { audio } from '../game/audio.js';

export class ScratchCard {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d', { willReadFrequently: true });
    this.onReveal = options.onReveal || (() => {});
    this.onStart = options.onStart || (() => {});
    this.onKeyboardReveal = options.onKeyboardReveal || (() => {});
    this.autoRevealThreshold = options.threshold || 0.70; // 70% 긁는 손맛 강화

    this.isDrawing = false;
    this.isRevealed = false;
    this.scratchStrokeCount = 0;
    this.cleanupTasks = [];
    this.started = false;

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

    const startScratch = (e) => {
      if (this.isRevealed) return;
      if (!this.started) {
        this.started = true;
        this.onStart();
      }
      this.isDrawing = true;
      e.preventDefault();
      const pos = getPos(e);
      this.scratch(pos.x, pos.y);
    };

    const moveScratch = (e) => {
      if (!this.isDrawing || this.isRevealed) return;
      e.preventDefault();
      const pos = getPos(e);
      this.scratch(pos.x, pos.y);
    };

    const endScratch = () => {
      this.isDrawing = false;
    };

    this.canvas.addEventListener('mousedown', startScratch);
    window.addEventListener('mousemove', moveScratch);
    window.addEventListener('mouseup', endScratch);

    this.canvas.addEventListener('touchstart', startScratch, { passive: false });
    window.addEventListener('touchmove', moveScratch, { passive: false });
    window.addEventListener('touchend', endScratch);
    const revealWithKeyboard = (event) => {
      if (!['Enter', ' '].includes(event.key) || this.isRevealed) return;
      event.preventDefault();
      if (!this.started) { this.started = true; this.onStart(); }
      this.onKeyboardReveal();
      this.revealInstantly();
    };
    this.canvas.addEventListener('keydown', revealWithKeyboard);
    this.cleanupTasks.push(() => {
      this.canvas.removeEventListener('mousedown', startScratch);
      window.removeEventListener('mousemove', moveScratch);
      window.removeEventListener('mouseup', endScratch);
      this.canvas.removeEventListener('touchstart', startScratch);
      window.removeEventListener('touchmove', moveScratch);
      window.removeEventListener('touchend', endScratch);
      this.canvas.removeEventListener('keydown', revealWithKeyboard);
    });
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

  revealInstantly({ restored = false } = {}) {
    if (this.isRevealed) return;
    if (!restored && !this.started) {
      this.started = true;
      this.onStart();
    }
    this.isRevealed = true;
    this.canvas.classList.add('fade-out');

    // Celebration Haptic Vibration Pattern (Tap-Tap-Boom!)
    if (!restored && typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      try {
        navigator.vibrate([35, 45, 50, 45, 100]);
      } catch (e) {}
    }

    if (!restored) audio.playWin();
    this.revealTimer = setTimeout(() => {
      this.onReveal();
    }, 300);
  }

  destroy() {
    clearTimeout(this.revealTimer);
    for (const cleanup of this.cleanupTasks) cleanup();
    this.cleanupTasks = [];
    this.isDrawing = false;
  }
}
