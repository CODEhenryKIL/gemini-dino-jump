/** Common UI helpers. User supplied values are assigned with textContent. */
export const ui = {
  showToast(message, duration = 2500) {
    let toast = document.getElementById('toast');
    if (!toast) { toast = document.createElement('div'); toast.id = 'toast'; document.body.appendChild(toast); }
    toast.textContent = String(message || ''); toast.classList.add('show'); clearTimeout(this._toastTimeout);
    this._toastTimeout = setTimeout(() => toast.classList.remove('show'), duration);
  },
  showModal({ title, content, trustedHtml = '', confirmText = '확인', onConfirm, cancelText = null, onCancel }) {
    let overlay = document.getElementById('common-modal-overlay');
    if (!overlay) { overlay = document.createElement('div'); overlay.id = 'common-modal-overlay'; overlay.className = 'modal-overlay'; overlay.innerHTML = '<div class="modal-card"><h3 class="modal-title" style="font-size:18px;font-weight:800;margin-bottom:12px"></h3><div class="modal-body" style="font-size:14px;color:var(--text-sub);margin-bottom:20px;line-height:1.5"></div><div class="modal-actions" style="display:flex;gap:10px"><button class="btn btn-secondary modal-cancel-btn"></button><button class="btn btn-primary modal-confirm-btn"></button></div></div>'; document.body.appendChild(overlay); }
    overlay.querySelector('.modal-title').textContent = String(title || '');
    const body = overlay.querySelector('.modal-body'); body.replaceChildren();
    if (typeof Node !== 'undefined' && content instanceof Node) body.appendChild(content); else if (trustedHtml) body.innerHTML = trustedHtml; else body.textContent = String(content || '');
    const confirm = overlay.querySelector('.modal-confirm-btn'); confirm.textContent = confirmText;
    confirm.onclick = async () => { const close = onConfirm ? await onConfirm() : true; if (close !== false) this.hideModal(); };
    const cancel = overlay.querySelector('.modal-cancel-btn'); cancel.hidden = !cancelText; cancel.textContent = cancelText || ''; cancel.onclick = () => { this.hideModal(); if (onCancel) onCancel(); };
    overlay.classList.add('active');
  },
  hideModal() { document.getElementById('common-modal-overlay')?.classList.remove('active'); },
  setText(root, selector, value) { const node = root.querySelector(selector); if (node) node.textContent = String(value ?? ''); return node; },
  safeImageUrl(value, fallback = '/assets/icons/Picture-Dark.png') { try { const url = new URL(value, window.location.origin); return url.origin === window.location.origin ? url.href : fallback; } catch { return fallback; } }
};
