/**
 * 智媒沙盘 - 公共 JavaScript 模块
 * 包含：粒子系统、工具函数、验证码逻辑、Toast、Modal
 */

// ============================================
// 粒子系统
// ============================================
const ParticleSystem = {
  canvas: null,
  ctx: null,
  particles: [],
  animationId: null,
  isAnimating: false,
  frameCount: 0,
  config: {
    particleCount: 42,
    connectionDistance: 95,
    renderConnections: true,
    connectionFrameStep: 2
  },
  resizeTimer: null,

  init(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.applyPerformanceProfile();
    this.bindEvents();
    // 延迟启动，确保 DOM 和样式完全渲染
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.startAnimationWithDelay());
    } else {
      this.startAnimationWithDelay();
    }
  },

  getPerformanceProfile() {
    const area = window.innerWidth * window.innerHeight;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const lowPowerHardware = (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) || area > 3200000;
    const midPowerHardware = area > 2200000;

    if (reducedMotion || lowPowerHardware) {
      return { particleCount: 24, connectionDistance: 78, renderConnections: false, connectionFrameStep: 3 };
    }
    if (midPowerHardware) {
      return { particleCount: 31, connectionDistance: 88, renderConnections: true, connectionFrameStep: 3 };
    }
    return { particleCount: 44, connectionDistance: 100, renderConnections: true, connectionFrameStep: 2 };
  },

  applyPerformanceProfile() {
    this.config = this.getPerformanceProfile();
  },

  resizeCanvas() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  },

  createParticle() {
    return {
      x: Math.random() * this.canvas.width,
      y: Math.random() * this.canvas.height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      radius: Math.random() * 2 + 0.5,
      color: Math.random() > 0.5 ? '#00d4ff' : '#a855f7',
      alpha: Math.random() * 0.4 + 0.1
    };
  },

  initParticles() {
    this.particles = [];
    for (let i = 0; i < this.config.particleCount; i++) {
      this.particles.push(this.createParticle());
    }
  },

  drawParticle(p) {
    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    this.ctx.fillStyle = p.color;
    this.ctx.globalAlpha = p.alpha;
    this.ctx.fill();
    this.ctx.globalAlpha = 1;
  },

  drawConnections() {
    if (!this.config.renderConnections) return;
    const thresholdSq = this.config.connectionDistance * this.config.connectionDistance;
    for (let i = 0; i < this.particles.length; i++) {
      for (let j = i + 1; j < this.particles.length; j++) {
        const dx = this.particles[i].x - this.particles[j].x;
        const dy = this.particles[i].y - this.particles[j].y;
        const distSq = dx * dx + dy * dy;
        if (distSq < thresholdSq) {
          const dist = Math.sqrt(distSq);
          this.ctx.beginPath();
          this.ctx.moveTo(this.particles[i].x, this.particles[i].y);
          this.ctx.lineTo(this.particles[j].x, this.particles[j].y);
          this.ctx.strokeStyle = `rgba(0, 212, 255, ${0.085 * (1 - dist / this.config.connectionDistance)})`;
          this.ctx.lineWidth = 0.9;
          this.ctx.stroke();
        }
      }
    }
  },

  updateParticles() {
    this.particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1;
    });
  },

  animate() {
    if (!this.isAnimating) return;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.frameCount++;
    if (this.frameCount % this.config.connectionFrameStep === 0) {
      this.drawConnections();
    }
    this.particles.forEach(p => this.drawParticle(p));
    this.updateParticles();
    this.animationId = requestAnimationFrame(() => this.animate());
  },

  startAnimationWithDelay() {
    if (this.isAnimating || !this.canvas) return;
    // 使用 setTimeout 确保浏览器已完成布局计算
    setTimeout(() => {
      if (!this.canvas) return;
      this.resizeCanvas();
      this.initParticles();
      this.isAnimating = true;
      this.animate();
    }, 50);
  },

  stopAnimation() {
    this.isAnimating = false;
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
  },

  bindEvents() {
    window.addEventListener('resize', () => {
      clearTimeout(this.resizeTimer);
      this.resizeTimer = setTimeout(() => {
        this.applyPerformanceProfile();
        this.resizeCanvas();
        this.initParticles();
      }, 200);
    });

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.stopAnimation();
      } else {
        this.startAnimationWithDelay();
      }
    });
  }
};

// ============================================
// 密码哈希工具（使用 PBKDF2）
// ============================================
const PasswordHash = {
  // 生成随机盐值
  generateSalt() {
    const array = new Uint8Array(16);
    crypto.getRandomValues(array);
    return Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
  },

  // 将字符串转换为 ArrayBuffer
  stringToBuffer(str) {
    return new TextEncoder().encode(str);
  },

  // 将 ArrayBuffer 转换为十六进制字符串
  bufferToHex(buffer) {
    return Array.from(new Uint8Array(buffer), b => b.toString(16).padStart(2, '0')).join('');
  },

  // 使用 PBKDF2 哈希密码
  async hashPassword(password, salt) {
    const saltBuffer = this.stringToBuffer(salt);
    const passwordBuffer = this.stringToBuffer(password);
    
    // 导入密钥
    const key = await crypto.subtle.importKey(
      'raw',
      passwordBuffer,
      'PBKDF2',
      false,
      ['deriveBits']
    );

    // 派生 100000 次
    const derivedBits = await crypto.subtle.deriveBits(
      {
        name: 'PBKDF2',
        salt: saltBuffer,
        iterations: 100000,
        hash: 'SHA-256'
      },
      key,
      256
    );

    return this.bufferToHex(derivedBits);
  },

  // 哈希并存储密码（异步）
  async hashAndStore(password) {
    const salt = this.generateSalt();
    const hash = await this.hashPassword(password, salt);
    return {
      salt,
      hash,
      // 存储格式：salt:hash
      storedValue: `${salt}:${hash}`
    };
  },

  // 验证密码（异步）
  async verifyPassword(password, storedValue) {
    try {
      const [salt, originalHash] = storedValue.split(':');
      if (!salt || !originalHash) return false;
      const inputHash = await this.hashPassword(password, salt);
      return inputHash === originalHash;
    } catch {
      return false;
    }
  },

  // 检查是否是旧格式（未哈希的密码）
  isLegacyPassword(password) {
    // 旧格式没有冒号分隔符
    return !password.includes(':');
  }
};

// ============================================
// 工具函数
// ============================================
const Utils = {
  isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  },

  redirectToMain() {
    window.location.href = 'main.html';
    setTimeout(() => window.location.assign('main.html'), 30);
    setTimeout(() => window.location.replace('main.html'), 80);
  },

  clearInput(inputId) {
    const input = document.getElementById(inputId);
    if (input) {
      input.value = '';
      input.focus();
    }
  },

  togglePassword(inputId, button) {
    const input = document.getElementById(inputId);
    const icon = button ? button.querySelector('svg') : document.getElementById('eye-icon');
    if (!input || !icon) return;

    if (input.type === 'password') {
      input.type = 'text';
      icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>';
    } else {
      input.type = 'password';
      icon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
    }
  }
};

// ============================================
// Toast 提示
// ============================================
const Toast = {
  show(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
    if (!toast || !toastMessage) return;

    toast.className = 'toast ' + type;
    toastMessage.textContent = message;

    const iconSvg = type === 'success'
      ? '<path d="M20 6L9 17l-5-5"/>'
      : '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>';
    toast.querySelector('svg').innerHTML = iconSvg;

    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
  }
};

// ============================================
// Modal 弹窗
// ============================================
const Modal = {
  open(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('active');
  },

  close(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
  },

  init() {
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('active');
      });
    });
  }
};

// ============================================
// Tab 切换
// ============================================
const Tabs = {
  init(containerSelector) {
    const container = document.querySelector(containerSelector);
    if (!container) return;

    container.querySelectorAll('.tab-item').forEach(tab => {
      tab.addEventListener('click', () => {
        const tabGroup = tab.closest('.tabs');
        const panelGroup = tabGroup ? tabGroup.nextElementSibling : null;

        tabGroup.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        if (panelGroup) {
          panelGroup.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
          const panelId = tab.dataset.tab + '-panel';
          const panel = document.getElementById(panelId);
          if (panel) panel.classList.add('active');
        }
      });
    });
  }
};

// ============================================
// 验证码系统
// ============================================
const VerificationCode = {
  SMTP_API_BASE: window.location.protocol === 'file:' ? 'http://127.0.0.1:5500' : window.location.origin,
  timers: {},

  getApiUrls() {
    if (window.location.protocol === 'file:') {
      return [`${this.SMTP_API_BASE}/api/send-code`];
    }
    // 优先命中邮件专用路由，兼容旧版 /api/send-code。
    return [
      `${this.SMTP_API_BASE}/mail-api/send-code`,
      `${this.SMTP_API_BASE}/api/send-code`
    ];
  },

  async verify(email, code, scene) {
    const payload = JSON.stringify({ email, code, scene });
    const apiUrls =
      window.location.protocol === 'file:'
        ? [`${this.SMTP_API_BASE}/api/verify-code`]
        : [`${this.SMTP_API_BASE}/mail-api/verify-code`, `${this.SMTP_API_BASE}/api/verify-code`];

    for (const url of apiUrls) {
      try {
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload
        });
        if (resp.ok) return { ok: true };

        let data = null;
        try {
          data = await resp.json();
        } catch {
          data = null;
        }
        if (data && data.message) {
          return { ok: false, message: data.message };
        }
      } catch {
        // try next endpoint
      }
    }
    return { ok: false, message: '验证码校验失败，请稍后重试' };
  },

  startTimer(buttonId, seconds = 60) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;

    let left = seconds;
    btn.disabled = true;
    btn.textContent = `${left}秒后重发`;

    const timer = setInterval(() => {
      left--;
      if (left <= 0) {
        clearInterval(timer);
        btn.disabled = false;
        btn.textContent = '发送验证码';
        delete this.timers[buttonId];
      } else {
        btn.textContent = `${left}秒后重发`;
      }
    }, 1000);

    this.timers[buttonId] = timer;
  },

  async sendByApi(email, scene) {
    const payload = JSON.stringify({ toEmail: email, scene });
    const apiUrls = this.getApiUrls();
    let lastError = null;

    for (const url of apiUrls) {
      try {
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload
        });
        if (resp.ok) return { ok: true };
        lastError = { reason: `http_${resp.status}` };
      } catch {
        lastError = { reason: 'network_error' };
      }
    }
    return { ok: false, ...(lastError || { reason: 'unknown_error' }) };
  },

  async send(email, scene, buttonId) {
    if (!Utils.isValidEmail(email)) {
      Toast.show('请输入有效的邮箱地址', 'error');
      return;
    }

    const result = await this.sendByApi(email, scene);

    if (result.ok) {
      Toast.show('验证码已发送，请检查邮箱', 'success');
      if (this.timers[buttonId]) clearInterval(this.timers[buttonId]);
      this.startTimer(buttonId, 60);
    } else {
      const reason = result.reason ? `（${result.reason}）` : '';
      Toast.show(`邮件发送失败，请稍后重试${reason}`, 'error');
    }
  }
};

// ============================================
// 清除按钮自动显示
// ============================================
function initClearButtons() {
  document.querySelectorAll('.input-wrapper input').forEach(input => {
    input.addEventListener('input', () => {
      const clearBtn = input.parentElement.querySelector('.clear-btn');
      if (clearBtn) {
        clearBtn.classList.toggle('visible', input.value.length > 0);
      }
    });
  });
}

// ============================================
// 导出到全局
// ============================================
window.AppParticles = ParticleSystem;
window.AppUtils = Utils;
window.AppToast = Toast;
window.AppModal = Modal;
window.AppTabs = Tabs;
window.AppVerification = VerificationCode;
window.initClearButtons = initClearButtons;
