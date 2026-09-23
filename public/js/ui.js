/**
 * Common UI Utilities (Toast, Modal, Countdown, Loading)
 */

export const ui = {
  showToast(message, duration = 2500) {
    let toast = document.getElementById('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(this._toastTimeout);
    this._toastTimeout = setTimeout(() => {
      toast.classList.remove('show');
    }, duration);
  },

  showModal({ title, content, confirmText = '확인', onConfirm, cancelText = null, onCancel }) {
    let overlay = document.getElementById('common-modal-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'common-modal-overlay';
      overlay.className = 'modal-overlay';
      overlay.innerHTML = `
        <div class="modal-card">
          <h3 class="modal-title" style="font-size: 18px; font-weight: 800; margin-bottom: 12px;"></h3>
          <div class="modal-body" style="font-size: 14px; color: var(--text-sub); margin-bottom: 20px; line-height: 1.5;"></div>
          <div class="modal-actions" style="display: flex; gap: 10px;">
            <button class="btn btn-secondary modal-cancel-btn" style="display: none;"></button>
            <button class="btn btn-primary modal-confirm-btn"></button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
    }

    const titleEl = overlay.querySelector('.modal-title');
    const bodyEl = overlay.querySelector('.modal-body');
    const confirmBtn = overlay.querySelector('.modal-confirm-btn');
    const cancelBtn = overlay.querySelector('.modal-cancel-btn');

    titleEl.textContent = title;
    if (typeof content === 'string') {
      bodyEl.innerHTML = content;
    } else {
      bodyEl.innerHTML = '';
      bodyEl.appendChild(content);
    }

    confirmBtn.textContent = confirmText;
    confirmBtn.onclick = () => {
      overlay.classList.remove('active');
      if (onConfirm) onConfirm();
    };

    if (cancelText) {
      cancelBtn.style.display = 'block';
      cancelBtn.textContent = cancelText;
      cancelBtn.onclick = () => {
        overlay.classList.remove('active');
        if (onCancel) onCancel();
      };
    } else {
      cancelBtn.style.display = 'none';
    }

    overlay.classList.add('active');
  },

  hideModal() {
    const overlay = document.getElementById('common-modal-overlay');
    if (overlay) overlay.classList.remove('active');
  }
};
