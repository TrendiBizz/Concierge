// Official A2UI v0.8 processor + Lit component catalog; no HTML from the agent.
import {Data} from '@a2ui/lit/0.8';
import {Context, Surface, TextField, DateTimeInput, Text} from '@a2ui/lit/ui';
import {html} from 'lit';
Surface.prototype.render = function () {
  return html`<a2ui-root .surfaceId=${this.surfaceId} .processor=${this.processor} .childComponents=${this.surface?.componentTree ? [this.surface.componentTree] : null} .enableCustomElements=${false}></a2ui-root>`;
};

// Native semantics live in the Lit template so a signal update cannot reset email/required.
Text.prototype.render = function () {
  const value = this.text?.path ? this.processor?.getData(this.component, this.text.path, this.surfaceId) || '' : this.text?.literalString || '';
  return this.usageHint === 'h3' ? html`<h3>${value}</h3>` : html`<span>${value}</span>`;
};
function fieldTemplate(control, binding, label, type) {
  const value = binding?.path ? control.processor?.getData(control.component, binding.path, control.surfaceId) || '' : binding?.literalString || '';
  return html`<section><label for="data">${label}</label><input id="data" name=${control.id}
    type=${type} required maxlength="1000" autocomplete=${control.id === 'email' ? 'email' : 'off'}
    .value=${value} @input=${event => control.processor.setData(control.component, binding.path, event.target.value, control.surfaceId)}></section>`;
}
TextField.prototype.render = function () {
  return fieldTemplate(this, this.text, this.label?.literalString || '', this.id === 'email' ? 'email' : 'text');
};
DateTimeInput.prototype.render = function () {
  return fieldTemplate(this, this.value, 'Preferred date and time (required)', 'datetime-local');
};

const css = new CSSStyleSheet();
css.replaceSync(`:host{font:16px/1.5 system-ui;min-width:0;color:inherit}:host(a2ui-surface){color:#241238}*{box-sizing:border-box}section{width:100%}input,button{font:inherit;min-height:48px;border-radius:8px;padding:10px;width:100%}input{border:1px solid #767676;background:white;color:#241238}button{background:#6d28d9;color:white;border:0;cursor:pointer}button:disabled{opacity:.6}label{display:block;margin-bottom:4px}input:focus-visible,button:focus-visible{outline:3px solid #5b21b6;outline-offset:2px}input:user-invalid{border:2px solid #b91c1c}slot{white-space:normal}a2ui-column{gap:12px}section{gap:12px}h3{font-size:1.1rem;margin:0}p{margin:0 0 8px}:host(a2ui-card){background:#fff;border:1px solid #c4b5fd;border-radius:12px;padding:16px}`);

function descendants(root) {
  const out = [];
  for (const node of root.querySelectorAll('*')) {
    out.push(node);
    if (node.shadowRoot) out.push(...descendants(node.shadowRoot));
  }
  return out;
}

window.ConciergeA2UI = {
  create(container, submit) {
    const theme = {components: {Card:{},Column:{},Button:{},Text:{all:{},h3:{}},TextField:{container:{},label:{},element:{}},DateTimeInput:{container:{},label:{},element:{}}}};
    container.addEventListener('context-request', event => {
      if (event.context === Context.theme) { event.stopPropagation(); event.callback(theme); }
    });
    const processor = Data.createSignalA2uiMessageProcessor();
    const surfaces = new Map();
    const finished = new Set();
    const pending = new Set();
    function enhance() {
      for (const node of descendants(container)) {
        if (node.shadowRoot && !node.shadowRoot.adoptedStyleSheets.includes(css)) {
          node.shadowRoot.adoptedStyleSheets = [...node.shadowRoot.adoptedStyleSheets, css];
        }
        if (node.matches('input')) {
          const host = node.getRootNode().host;
          const key = host?.id;
          node.required = true;
          node.maxLength = 1000;
          node.name = key || 'value';
          if (key === 'email') { node.type = 'email'; node.autocomplete = 'email'; }
          if (key === 'timezone') node.autocomplete = 'off';
          if (key === 'when') {
            const label = node.getRootNode().querySelector('label');
            if (label && label.textContent !== 'Preferred date and time (required)') label.textContent = 'Preferred date and time (required)';
          }
          const sid = host?.surfaceId;
          node.disabled = finished.has(sid) || pending.has(sid);
        }
        if (node.matches('button')) {
          const sid = node.getRootNode().host?.surfaceId;
          node.type = 'button';
          node.disabled = finished.has(sid) || pending.has(sid);
        }
      }
    }
    const observer = new MutationObserver(enhance);
    observer.observe(container, {childList: true, subtree: true});
    // Lit's updates take place inside nested shadow roots; observe each after it renders.
    async function settle() {
      for (let i = 0; i < 12; i++) {
        const nodes = descendants(container);
        await Promise.all(nodes.filter(n => n.updateComplete).map(n => n.updateComplete));
        for (const n of nodes) if (n.shadowRoot) observer.observe(n.shadowRoot, {childList:true, subtree:true});
        enhance();
      }
    }
    async function receive(message) {
      processor.processMessages([message]);
      for (const [sid, surface] of processor.getSurfaces()) {
        let node = surfaces.get(sid);
        if (!node) {
          node = document.createElement('a2ui-surface');
          node.dataset.surfaceId = sid;
          node.surfaceId = sid;
          node.processor = processor;
          node.enableCustomElements = false;
          surfaces.set(sid, node);
          container.append(node);
        }
        node.surface = surface;
        node.requestUpdate();
      }
      for (const [sid, node] of surfaces) if (!processor.getSurfaces().has(sid)) { node.remove(); surfaces.delete(sid); }
      await settle();
    }
    container.addEventListener('a2uiaction', async event => {
      const detail = event.detail;
      if (detail.eventType !== 'a2ui.action') return;
      const surface = event.composedPath().find(n => n.localName === 'a2ui-surface');
      if (!surface || finished.has(surface.surfaceId) || pending.has(surface.surfaceId)) return;
      const inputs = descendants(surface.shadowRoot).filter(n => n.matches('input'));
      for (const input of inputs) if (!input.reportValidity()) { input.focus(); return; }
      const context = {};
      for (const entry of detail.action.context || []) {
        context[entry.key] = entry.value.path ? processor.getData(detail.sourceComponent, entry.value.path, surface.surfaceId) : entry.value.literalString;
      }
      pending.add(surface.surfaceId); enhance();
      try {
        await submit({userAction: {name: detail.action.name, surfaceId: surface.surfaceId,
          sourceComponentId: detail.sourceComponentId, timestamp: new Date().toISOString(), context}});
        finished.add(surface.surfaceId);
      } catch { /* submit reports its own error; keep the form available for retry. */ } finally { pending.delete(surface.surfaceId); enhance(); }
    });
    return {receive};
  }
};
