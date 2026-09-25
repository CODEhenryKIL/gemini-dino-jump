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
    const overlay = document.createElement('div');
    overlay.id = 'common-modal-overlay';
    overlay.className = 'modal-overlay active';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    const card = document.createElement('div');
    card.className = 'modal-card';
    const heading = document.createElement('h3');
    heading.className = 'modal-title';
    heading.textContent = title;
    const body = document.createElement('div');
    body.className = 'modal-body';
    if (content instanceof Node) body.appendChild(content);
    else body.textContent = String(content || '');
    const actions = document.createElement('div');
    actions.className = 'modal-actions';
    if (cancelText) {
      const cancel = document.createElement('button');
      cancel.className = 'btn btn-secondary';
      cancel.textContent = cancelText;
      cancel.onclick = () => { this.hideModal(); onCancel?.(); };
      actions.appendChild(cancel);
    }
    const confirm = document.createElement('button');
    confirm.className = 'btn btn-primary';
    confirm.textContent = confirmText;
    confirm.onclick = async () => {
      confirm.disabled = true;
      try {
        const shouldClose = await onConfirm?.();
        if (shouldClose !== false) this.hideModal();
      } finally {
        if (document.body.contains(confirm)) confirm.disabled = false;
      }
    };
    actions.appendChild(confirm);
    card.append(heading, body, actions);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    queueMicrotask(() => confirm.focus());
  },
  hideModal() { document.getElementById('common-modal-overlay')?.remove(); },
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
