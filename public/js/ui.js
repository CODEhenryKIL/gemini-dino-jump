/** DOM helpers. Dynamic and user-provided content is always assigned through textContent. */
export const ui = {
  text(element, value) {
    if (element) element.textContent = value == null ? '' : String(value);
    return element;
  },
  showToast(message, duration = 2500) {
    let toast = document.getElementById('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.textContent = String(message || '');
    toast.classList.add('show');
    clearTimeout(this._toastTimeout);
    this._toastTimeout = setTimeout(() => toast.classList.remove('show'), duration);
  },
  showModal({ title, content, confirmText = '확인', onConfirm, cancelText = null, onCancel }) {
    this.hideModal();
    const opener = document.activeElement;
    const app = document.getElementById('app-container');
    const previousInert = app?.inert;
    if (app) app.inert = true;
    const overlay = document.createElement('div');
    overlay.id = 'common-modal-overlay';
    overlay.className = 'modal-overlay active';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'common-modal-title');
    const card = document.createElement('div');
    card.className = 'modal-card';
    card.tabIndex = -1;
    const heading = document.createElement('h3');
    heading.id = 'common-modal-title';
    heading.className = 'modal-title';
    heading.textContent = title;
    const body = document.createElement('div');
    body.className = 'modal-body';
    if (content instanceof Node) body.appendChild(content);
    else body.textContent = String(content || '');
    const actions = document.createElement('div');
    actions.className = 'modal-actions';
    let cancel = null;
    if (cancelText) {
      cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'btn btn-secondary';
      cancel.textContent = cancelText;
      cancel.onclick = () => { this.hideModal(); onCancel?.(); };
      actions.appendChild(cancel);
    }
    const confirm = document.createElement('button');
    confirm.type = 'button';
    confirm.className = 'btn btn-primary';
    confirm.textContent = confirmText;
    confirm.onclick = async () => {
      if (confirm.disabled) return;
      confirm.disabled = true;
      try {
        const shouldClose = await onConfirm?.();
        if (shouldClose !== false && document.getElementById('common-modal-overlay') === overlay) this.hideModal();
      } finally {
        if (document.body.contains(confirm)) confirm.disabled = false;
      }
    };
    actions.appendChild(confirm);
    card.append(heading, body, actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    const focusable = () => [...card.querySelectorAll('button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])')]
      .filter((element) => element.getClientRects().length > 0);
    overlay.onkeydown = (event) => {
      if (event.key === 'Escape' && cancel) {
        event.preventDefault();
        cancel.onclick();
      } else if (event.key === 'Tab') {
        const controls = focusable();
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first) { event.preventDefault(); card.focus(); return; }
        const active = document.activeElement;
        if (!card.contains(active) || (event.shiftKey ? active === first : active === last)) {
          event.preventDefault();
          (event.shiftKey ? last : first).focus();
        }
      }
    };
    this._modalCleanup = () => {
      overlay.onkeydown = null;
      if (app) app.inert = previousInert;
      if (opener && document.body.contains(opener)) opener.focus();
    };
    queueMicrotask(() => {
      if (!document.body.contains(confirm)) return;
      const input = focusable().find((element) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName));
      (input || confirm).focus({ preventScroll: true });
    });
  },
  hideModal() {
    document.getElementById('common-modal-overlay')?.remove();
    const cleanup = this._modalCleanup;
    this._modalCleanup = null;
    cleanup?.();
  },
  formField(labelText, type, name, { required = true, maxlength = 80, autocomplete = 'off' } = {}) {
    const label = document.createElement('label');
    label.className = 'form-field';
    const text = document.createElement('span');
    text.textContent = labelText;
    const input = document.createElement('input');
    input.type = type;
    input.name = name;
    input.required = required;
    input.maxLength = maxlength;
    input.autocomplete = autocomplete;
    label.append(text, input);
    return { label, input };
  },
};
