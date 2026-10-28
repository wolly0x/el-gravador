/* El Gravador 18 Pro Max — interface web (JavaScript puro, sem etapa de build). */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  data: null,
  tab: 'fluxo',
  selected: null,
  booted: false,
  fatalShown: false,
  fatalModal: null,
  pollBusy: false,
  pollTimer: null,
  stepSignature: '',
  paletteSignature: '',
  configRendered: false,
  logKey: '',
  lastMessageKey: '',
  pendingConfig: {},
  configTimer: null,
  configSaving: false,
  modalStack: [],
  dragging: null,
  logFilter: '',
};

const CATEGORY_LABELS = {
  'ação': 'Ações de mouse e teclado',
  imagem: 'Busca por imagem',
  estrutura: 'Estrutura e lógica',
  outro: 'Outros',
};
const CATEGORY_ORDER = ['ação', 'imagem', 'estrutura', 'outro'];

const TYPE_ICONS = {
  clicar: 'mouse',
  mover: 'move',
  arrastar: 'grip',
  rolar: 'scroll',
  digitar: 'keyboard',
  atalho: 'sparkles',
  tecla: 'key',
  pausa: 'clock',
  imagem_clicar: 'image',
  imagem_esperar: 'eye',
  imagem_desaparecer: 'crosshair',
  bloco_inicio: 'repeat',
  bloco_fim: 'flag',
  comentario: 'message',
};

const STATUS_COLORS = {
  info: '',
  ok: 'ok',
  aviso: 'warn',
  erro: 'err',
  rec: 'rec',
  exec: '',
};

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function iconMarkup(name, cls = 'icon') {
  return `<span class="${cls}" aria-hidden="true"><svg viewBox="0 0 24 24"><use href="#i-${esc(name)}"></use></svg></span>`;
}

function applyIcons(root = document) {
  $$('[data-icon]', root).forEach((el) => {
    if (!el.dataset.iconDone) {
      el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-${el.dataset.icon}"></use></svg>`;
      el.dataset.iconDone = '1';
    }
  });
}

function numberValue(value, fallback = 0) {
  const n = Number(String(value ?? '').replace(',', '.'));
  return Number.isFinite(n) ? n : fallback;
}

function intValue(value, fallback = 0) {
  return Math.trunc(numberValue(value, fallback));
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const min = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${min}m ${rest}s` : `${min}m`;
}

function hexToRgb(hex) {
  const value = String(hex || '').trim().replace('#', '');
  const full = value.length === 3 ? value.split('').map((c) => c + c).join('') : value;
  if (!/^[0-9a-f]{6}$/i.test(full)) return { r: 20, g: 20, b: 25 };
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

function rgba(hex, alpha) {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function luminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

function shade(hex, amount) {
  const { r, g, b } = hexToRgb(hex);
  const adjust = (c) => Math.max(0, Math.min(255, Math.round(c + 255 * amount)));
  return `rgb(${adjust(r)}, ${adjust(g)}, ${adjust(b)})`;
}

function typeIcon(tipo) {
  return TYPE_ICONS[tipo] || 'flow';
}

function categoryLabel(cat) {
  return CATEGORY_LABELS[cat] || cat || 'Outro';
}

function estimateSeconds(passos) {
  let total = 0;
  for (const passo of passos) {
    const p = passo.params || {};
    if (passo.tipo === 'pausa') total += numberValue(p.segundos, 1);
    else if (passo.tipo === 'mover' || passo.tipo === 'clicar') total += numberValue(p.duracao, 1.2) + 0.25;
    else if (passo.tipo === 'arrastar') total += numberValue(p.duracao, 1) + 0.3;
    else if (passo.tipo === 'digitar') {
      const intervalo = p.intervalo == null ? 0.08 : numberValue(p.intervalo, 0.08);
      total += String(p.texto || '').length * intervalo + 0.3;
    } else if (passo.tipo === 'imagem_clicar') total += numberValue(p.timeout, 15) * 0.2 + 0.5;
    else if (passo.tipo === 'imagem_esperar' || passo.tipo === 'imagem_desaparecer') total += numberValue(p.timeout, 15) * 0.5;
    else total += 0.45;
  }
  return total;
}

/* ------------------------------------------------------------------ */
/* Ponte com o Python                                                  */
/* ------------------------------------------------------------------ */
function bridge() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

async function callBackend(comando, args = {}, timeout = 60) {
  const api = bridge();
  if (!api) throw new Error('A ponte com o aplicativo ainda não está pronta.');
  const resposta = await api.backend_command(comando, args || {});
  if (!resposta || resposta.ok !== true) {
    throw new Error((resposta && resposta.erro) || 'O aplicativo não respondeu.');
  }
  return resposta.data;
}

async function getState() {
  const api = bridge();
  if (!api) throw new Error('A ponte com o aplicativo ainda não está pronta.');
  const resposta = await api.state();
  if (!resposta || resposta.ok !== true) {
    throw new Error((resposta && resposta.erro) || 'Não foi possível ler o estado.');
  }
  return resposta.data;
}

function absorb(resposta) {
  if (!resposta) return null;
  const snapshot = resposta.state || (resposta.projeto ? resposta : null);
  if (snapshot) applyState(snapshot);
  return resposta;
}

/* ------------------------------------------------------------------ */
/* Tema e tipografia                                                   */
/* ------------------------------------------------------------------ */
function applyTheme(data) {
  if (!data || !data.paleta || !data.config) return;
  const cfg = data.config;
  const p = data.paleta;
  const root = document.documentElement;
  const dark = luminance(p.c_bg || '#0B0B0F') < 0.5;
  root.dataset.theme = dark ? 'dark' : 'light';
  root.style.colorScheme = dark ? 'dark' : 'light';

  const surface = p.c_surface || (dark ? '#141419' : '#FFFFFF');
  const surfaceAlt = p.c_surface_alt || p.c_current || surface;
  const border = p.c_border || (dark ? '#2C2C34' : '#DFE1E8');
  const accent = p.c_accent || p.c_cyan || '#0A84FF';

  const vars = {
    '--bg': p.c_bg || '#0B0B0F',
    '--bg-soft': p.c_current || p.c_bg || '#121218',
    '--surface': surface,
    '--surface-2': surfaceAlt,
    '--surface-3': p.c_action || (dark ? '#26262E' : '#E8E8ED'),
    '--text': p.c_fg || (dark ? '#F5F5F7' : '#1D1D1F'),
    '--muted': p.c_text_sub || p.c_comment || (dark ? '#A1A1A6' : '#6E6E73'),
    '--faint': p.c_comment || (dark ? '#6E6E73' : '#92929A'),
    '--border': border,
    '--border-strong': p.c_border_strong || border,
    '--accent': accent,
    '--accent-hover': p.c_accent_hover || accent,
    '--accent-soft': p.c_accent_soft || rgba(accent, dark ? 0.18 : 0.12),
    '--on-accent': p.c_on_accent || '#FFFFFF',
    '--green': p.c_green || p.c_success || '#30D158',
    '--orange': p.c_orange || p.c_warning || '#FF9F0A',
    '--red': p.c_red || p.c_danger || '#FF453A',
    '--pink': p.c_pink || '#BF5AF2',
    '--glass': rgba(surface, dark ? 0.58 : 0.7),
    '--glass-strong': rgba(surface, dark ? 0.86 : 0.92),
    '--glass-border': dark ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.92)',
    '--shadow': dark
      ? '0 22px 60px rgba(0,0,0,0.42)'
      : '0 22px 60px rgba(54,63,92,0.14)',
    '--shadow-soft': dark
      ? '0 8px 26px rgba(0,0,0,0.24)'
      : '0 8px 24px rgba(54,63,92,0.09)',
    '--log-bg': dark ? shade(p.c_bg || '#0B0B0F', 0.02) : '#101117',
    '--log-text': dark ? '#C8C8D2' : '#D8D9E2',
    '--ambient-opacity': dark ? '0.7' : '0.62',
    '--row-hover': dark ? 'rgba(255,255,255,0.05)' : 'rgba(20,30,60,0.04)',
    '--row-active': rgba(accent, dark ? 0.16 : 0.1),
    '--font': `"${String(cfg.fonte || 'Segoe UI').replace(/["']/g, '')}", "Segoe UI", Inter, system-ui, sans-serif`,
    '--mono': '"Cascadia Code", "Consolas", "SFMono-Regular", monospace',
  };
  for (const [key, value] of Object.entries(vars)) root.style.setProperty(key, value);

  const base = Math.max(15, Math.min(22, Math.round(numberValue(cfg.escala_web, 15))));
  root.style.setProperty('--base-size', `${base}px`);
}

/* ------------------------------------------------------------------ */
/* Estado                                                              */
/* ------------------------------------------------------------------ */
function applyState(data, initial = false) {
  if (!data || !data.projeto) return;
  const previous = state.data;
  state.data = data;
  applyTheme(data);
  syncHeader(data);
  updateWarnings(data);
  updateStatus(data);
  updateMessages(data, initial);

  if (!previous || initial || state.tab === 'fluxo') {
    const signature = data.projeto.passos
      .map((p) => `${p.id}:${p.tipo}:${p.ativo}:${JSON.stringify(p.params)}`)
      .join('|');
    if (signature !== state.stepSignature || initial) {
      state.stepSignature = signature;
      renderSteps(data);
    } else {
      updateCurrentStep(data);
      updateSelection();
    }
    renderPalette(data);
  }

  if (state.tab === 'config') {
    if (!state.configRendered) renderConfig();
    else syncConfig();
  }
  if (state.tab === 'log') renderLogs();
  hideBoot();
}

function hideBoot() {
  document.body.dataset.ready = '1';
  const boot = document.getElementById('boot');
  if (!boot || boot.classList.contains('is-done')) return;
  boot.classList.add('is-done');
  setTimeout(() => boot.remove(), 320);
}

function syncHeader(data) {
  const projeto = data.projeto || {};
  const passos = projeto.passos || [];
  const nome = projeto.nome || 'novo_projeto';
  const input = $('#project-name');
  if (input && document.activeElement !== input) input.value = nome;
  const sidebarName = $('#sidebar-project-name');
  if (sidebarName) sidebarName.textContent = nome;
  const dirty = Boolean(projeto.alterado);
  const dot = $('#sidebar-dirty');
  if (dot) dot.classList.toggle('is-dirty', dirty);
  $('#dirty-badge')?.classList.toggle('is-on', dirty);
  const path = $('#project-path');
  if (path) {
    path.textContent = projeto.caminho || 'Ainda não salvo';
    path.title = projeto.caminho || 'O projeto será salvo automaticamente';
  }

  const repeat = $('#repeat-input');
  if (repeat && document.activeElement !== repeat) repeat.value = projeto.repeticoes ?? 1;
  const simulate = $('#simulate-switch');
  if (simulate) simulate.checked = Boolean(data.simular);

  const count = passos.length;
  const repeticoes = Number(projeto.repeticoes ?? 1);
  const repeticoesTexto = repeticoes === 0 ? '∞' : repeticoes;
  $('#nav-step-count').textContent = String(count);
  $('#stat-steps').textContent = String(count);
  $('#stat-time').textContent = `≈ ${formatDuration(estimateSeconds(passos))}`;
  $('#steps-subtitle').textContent = count
    ? `${count} passo${count === 1 ? '' : 's'} · ${repeticoesTexto}× repetição`
    : 'Nenhum passo ainda';
  $('#steps-footer-count').textContent = `${count} passo${count === 1 ? '' : 's'}`;

  const gravando = Boolean(data.gravando);
  const executando = Boolean(data.executando);
  const recordBtn = $('#record-btn');
  const recordLabel = $('#record-label');
  if (recordBtn) {
    recordBtn.classList.toggle('is-recording', gravando);
    recordBtn.disabled = executando;
  }
  if (recordLabel) recordLabel.textContent = gravando ? 'Parar' : 'Gravar';
  const executeBtn = $('#execute-btn');
  if (executeBtn) {
    executeBtn.disabled = gravando;
    const label = executeBtn.querySelector('span:last-child');
    if (label) label.textContent = executando ? 'Executando…' : 'Executar';
  }
  const navLive = $('#nav-log-live');
  if (navLive) navLive.classList.toggle('is-on', gravando || executando);
}

function updateStatus(data) {
  let kind = data.status_tipo || 'info';
  let label = 'Pronto';
  let hint = 'F9 gravar · Ctrl+R executar';
  if (data.gravando) {
    kind = 'rec';
    label = data.pausado ? 'Gravação pausada' : 'Gravando';
    hint = 'F9 parar · F10 pausar · ESC descartar';
  } else if (data.executando) {
    kind = data.pausado ? 'aviso' : 'ok';
    label = data.pausado ? 'Execução pausada' : 'Executando';
    hint = 'F8 pausar/retomar · ESC parar';
  } else if (kind === 'erro') label = 'Atenção';
  else if (kind === 'aviso') label = 'Aviso';
  else if (kind === 'ok') label = 'Pronto';

  const dot = $('#status-dot');
  if (dot) {
    dot.className = 'status-dot';
    const cor = STATUS_COLORS[kind];
    if (cor) dot.classList.add(cor);
    if (kind === 'rec') dot.classList.add('rec');
  }
  const text = $('#status-text');
  if (text) text.textContent = data.status || 'Pronto';
  const hintEl = $('#status-hint');
  if (hintEl) hintEl.textContent = hint;
  const version = $('#status-version');
  if (version) version.textContent = `El Gravador ${data.versao || '18 Pro Max'}`;

  const sideDot = $('#sidebar-status-dot');
  if (sideDot) {
    const cor = STATUS_COLORS[kind];
    sideDot.className = cor ? `status-dot ${cor}` : 'status-dot';
    if (kind === 'rec') sideDot.classList.add('rec');
  }
  $('#sidebar-status-label').textContent = label;
  const detail = $('#sidebar-status-detail');
  if (detail) {
    const status = data.status || 'Pronto';
    detail.textContent = status.length > 34 ? status.slice(0, 32) + '…' : status;
  }
  document.body.dataset.activity = data.gravando ? 'recording' : data.executando ? 'executing' : 'idle';
}

function updateWarnings(data) {
  const problemas = data.projeto?.problemas || [];
  const strip = $('#flow-warning');
  if (!strip) return;
  strip.hidden = problemas.length === 0;
  const text = $('#flow-warning-text');
  if (text && problemas.length) {
    text.textContent = `${problemas.length} ponto${problemas.length === 1 ? '' : 's'} de atenção no fluxo.`;
  }
}

function updateMessages(data, initial = false) {
  const mensagens = data.mensagens || [];
  const last = mensagens[mensagens.length - 1];
  if (!last) return;
  const key = `${mensagens.length}:${last.nivel}:${last.titulo}:${last.texto}`;
  if (initial) {
    state.lastMessageKey = key;
    return;
  }
  if (key === state.lastMessageKey) return;
  state.lastMessageKey = key;
  const type = last.nivel === 'erro' ? 'err' : last.nivel === 'aviso' ? 'warn' : 'info';
  toast(last.titulo || 'Aviso do aplicativo', last.texto || '', type, 6500);
}

/* ------------------------------------------------------------------ */
/* Fluxo                                                               */
/* ------------------------------------------------------------------ */
function renderSteps(data) {
  const lista = $('#steps-list');
  const vazio = $('#steps-empty');
  if (!lista) return;
  const passos = data.projeto.passos || [];
  const scroll = $('#steps-scroll');
  const top = scroll ? scroll.scrollTop : 0;
  if (!passos.length) {
    lista.innerHTML = '';
    vazio?.classList.remove('is-hidden');
    return;
  }
  vazio?.classList.add('is-hidden');
  lista.innerHTML = passos.map((passo, index) => {
    const selecionado = state.selected === index;
    const atual = data.atual === index;
    const off = !passo.ativo;
    return `
      <div class="step-row ${selecionado ? 'is-selected' : ''} ${atual ? 'is-current' : ''} ${off ? 'is-off' : ''}"
           data-index="${index}" data-cat="${esc(passo.categoria)}" draggable="true" tabindex="0"
           title="Duplo clique para editar">
        <span class="step-grip" title="Arraste para reordenar">${iconMarkup('grip')}</span>
        <span class="step-index">${index + 1}</span>
        <span class="step-type-icon">${iconMarkup(typeIcon(passo.tipo))}</span>
        <span class="step-main">
          <span class="step-title-line">
            <span class="step-title">${esc(passo.titulo)}</span>
            <span class="step-cat">${esc(passo.categoria)}</span>
          </span>
          <span class="step-desc">${esc(passo.rotulo)}</span>
        </span>
        <span class="step-actions">
          <button class="icon-btn small" data-step-action="toggle" title="${off ? 'Reativar passo' : 'Desativar passo'}" aria-label="Alternar passo">${iconMarkup(off ? 'eye' : 'check')}</button>
          <button class="icon-btn small" data-step-action="duplicate" title="Duplicar" aria-label="Duplicar">${iconMarkup('copy')}</button>
          <button class="icon-btn small" data-step-action="edit" title="Editar" aria-label="Editar">${iconMarkup('edit')}</button>
          <button class="icon-btn small" data-step-action="delete" title="Excluir" aria-label="Excluir">${iconMarkup('trash')}</button>
        </span>
      </div>`;
  }).join('');
  if (scroll) scroll.scrollTop = top;
  applyIcons(lista);
}

function updateCurrentStep(data) {
  $$('#steps-list .step-row').forEach((row) => {
    row.classList.toggle('is-current', Number(row.dataset.index) === data.atual);
  });
}

function updateSelection() {
  $$('#steps-list .step-row').forEach((row) => {
    row.classList.toggle('is-selected', Number(row.dataset.index) === state.selected);
  });
}

function selectStep(index, scroll = false) {
  const passos = state.data?.projeto?.passos || [];
  if (index == null || index < 0 || index >= passos.length) state.selected = null;
  else state.selected = index;
  updateSelection();
  if (scroll && state.selected != null) {
    const row = $(`#steps-list .step-row[data-index="${state.selected}"]`);
    row?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

function renderPalette(data) {
  const lista = $('#palette-list');
  if (!lista) return;
  const tipos = data.tipos || {};
  const signature = Object.keys(tipos).map((k) => `${k}:${tipos[k].titulo}:${tipos[k].categoria}`).join('|');
  if (signature === state.paletteSignature) return;
  state.paletteSignature = signature;
  const grupos = {};
  for (const [tipo, info] of Object.entries(tipos)) {
    const cat = info.categoria || 'outro';
    (grupos[cat] ||= []).push({ tipo, ...info });
  }
  lista.innerHTML = CATEGORY_ORDER.filter((cat) => grupos[cat]?.length)
    .map((cat) => `
      <div class="palette-group">
        <h4>${esc(CATEGORY_LABELS[cat] || cat)}</h4>
        ${grupos[cat].map((info) => `
          <button class="palette-item" data-add-type="${esc(info.tipo)}" data-cat="${esc(cat)}" title="Adicionar ${esc(info.titulo)}">
            <span class="icon">${iconMarkup(typeIcon(info.tipo), '')}</span>
            <span>${esc(info.titulo)}</span>
          </button>`).join('')}
      </div>`).join('');
  applyIcons(lista);
}

/* ------------------------------------------------------------------ */
/* Modais, avisos e confirmações                                      */
/* ------------------------------------------------------------------ */
function openModal(opts = {}) {
  const focoAnterior = document.activeElement;
  const layer = document.createElement('div');
  layer.className = 'modal-layer';
  const size = opts.size || 'md';
  layer.innerHTML = `
    <div class="modal-backdrop"></div>
    <div class="modal size-${esc(size)}" role="dialog" aria-modal="true" aria-label="${esc(opts.title || 'Janela')}">
      <button class="icon-btn ghost modal-close" data-modal-close aria-label="Fechar">${iconMarkup('x')}</button>
      <div class="modal-head">
        ${opts.kicker ? `<div class="modal-kicker">${esc(opts.kicker)}</div>` : ''}
        <h2>${esc(opts.title || '')}</h2>
        ${opts.subtitle ? `<p>${esc(opts.subtitle)}</p>` : ''}
      </div>
      <div class="modal-body">${opts.body || ''}</div>
      <div class="modal-actions"></div>
    </div>`;
  document.getElementById('modal-root').appendChild(layer);
  const modal = $('.modal', layer);
  const body = $('.modal-body', layer);
  const actions = $('.modal-actions', layer);
  let closed = false;

  const ctx = {
    layer,
    modal,
    body,
    actions,
    close() {
      if (closed) return;
      closed = true;
      layer.remove();
      state.modalStack = state.modalStack.filter((item) => item !== ctx);
      if (!state.modalStack.length) document.body.classList.remove('modal-open');
      if (focoAnterior instanceof HTMLElement && focoAnterior.isConnected) {
        focoAnterior.focus({ preventScroll: true });
      }
      try {
        opts.onClose?.();
      } catch (error) {
        console.error(error);
      }
    },
  };

  if (opts.dismissible !== false) {
    $('.modal-backdrop', layer).addEventListener('click', () => ctx.close());
    $('[data-modal-close]', layer).addEventListener('click', () => ctx.close());
  } else {
    $('[data-modal-close]', layer)?.remove();
  }

  const botoes = opts.actions || [{ label: 'Fechar', kind: 'soft' }];
  for (const acao of botoes) {
    const botao = document.createElement('button');
    botao.className = `btn ${acao.kind || 'soft'}`;
    botao.textContent = acao.label || 'OK';
    if (acao.disabled) botao.disabled = true;
    botao.addEventListener('click', async () => {
      if (botao.disabled) return;
      const original = botao.textContent;
      try {
        if (acao.onClick) {
          botao.disabled = true;
          botao.textContent = 'Aguarde…';
          const manter = await acao.onClick(ctx);
          if (manter === false) {
            botao.disabled = false;
            botao.textContent = original;
            return;
          }
        }
        ctx.close();
      } catch (error) {
        botao.disabled = false;
        botao.textContent = original;
        toast('Não foi possível concluir', error.message || String(error), 'err');
      }
    });
    actions.appendChild(botao);
  }

  state.modalStack.push(ctx);
  document.body.classList.add('modal-open');
  requestAnimationFrame(() => {
    const focusable = $('input, textarea, select, button', body);
    focusable?.focus();
    opts.onMount?.(ctx);
  });
  return ctx;
}

function closeTopModal() {
  const top = state.modalStack[state.modalStack.length - 1];
  if (top) top.close();
  return Boolean(top);
}

function closeAllModals() {
  while (state.modalStack.length) state.modalStack[state.modalStack.length - 1].close();
}

function toast(titulo, mensagem = '', tipo = 'info', duracao = 4800) {
  const host = $('#toasts');
  if (!host) return;
  const icon = tipo === 'ok' ? 'check-circle' : tipo === 'warn' ? 'alert' : tipo === 'err' ? 'alert' : 'info';
  const el = document.createElement('div');
  el.className = `toast ${tipo}`;
  el.innerHTML = `
    <span class="toast-icon">${iconMarkup(icon)}</span>
    <span class="toast-copy"><strong>${esc(titulo)}</strong><span>${esc(mensagem)}</span></span>
    <button class="toast-x" aria-label="Fechar">×</button>`;
  host.appendChild(el);
  while (host.children.length > 4) host.firstElementChild?.remove();
  const remover = () => {
    if (!el.isConnected) return;
    el.classList.add('is-out');
    setTimeout(() => el.remove(), 190);
  };
  $('.toast-x', el).addEventListener('click', remover);
  if (duracao) setTimeout(remover, duracao);
}

function ehCancelamento(mensagem) {
  return /cancel|abort|desist|nenhum[ao]? (ponto|regi)/i.test(String(mensagem || ''));
}

function promptText({
  title = 'Informar valor',
  kicker = '',
  subtitle = '',
  label = 'Valor',
  value = '',
  placeholder = '',
  confirmLabel = 'Confirmar',
} = {}) {
  return new Promise((resolve) => {
    let resolvido = false;
    const modal = openModal({
      title,
      kicker,
      subtitle,
      size: 'sm',
      body: `<div class="form-grid"><div class="form-field full"><label for="prompt-value">${esc(label)}</label><input id="prompt-value" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off"></div></div>`,
      actions: [
        { label: 'Cancelar', kind: 'soft', onClick: () => { resolvido = true; resolve(null); return true; } },
        {
          label: confirmLabel,
          kind: 'primary',
          onClick: (ctx) => {
            const texto = $('input', ctx.body)?.value ?? '';
            resolvido = true;
            resolve(texto);
            return true;
          },
        },
      ],
      onClose: () => { if (!resolvido) resolve(null); },
    });
    const input = $('input', modal.body);
    input?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        $('.modal-actions .btn.primary', modal.layer)?.click();
      }
    });
  });
}

function confirmDialog({
  title = 'Confirmar',
  message = '',
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  danger = false,
  kicker = '',
} = {}) {
  return new Promise((resolve) => {
    let resolvido = false;
    openModal({
      title,
      kicker,
      size: 'sm',
      body: `<p class="form-note" style="white-space:pre-wrap; font-size: var(--fs-sm); line-height:1.6">${esc(message)}</p>`,
      actions: [
        { label: cancelLabel, kind: 'soft', onClick: () => { resolvido = true; resolve(false); return true; } },
        { label: confirmLabel, kind: danger ? 'danger-soft' : 'primary', onClick: () => { resolvido = true; resolve(true); return true; } },
      ],
      onClose: () => { if (!resolvido) resolve(false); },
    });
  });
}

function askSaveChanges() {
  return new Promise((resolve) => {
    let resolvido = false;
    openModal({
      title: 'Alterações não salvas',
      kicker: 'PROJETO',
      subtitle: 'O que deseja fazer antes de continuar?',
      size: 'sm',
      body: '<p class="form-note">Se você descartar, as alterações desde o último salvamento serão perdidas. O salvamento automático também pode ter criado uma cópia recente.</p>',
      actions: [
        { label: 'Cancelar', kind: 'soft', onClick: () => { resolvido = true; resolve('cancel'); return true; } },
        { label: 'Descartar', kind: 'danger-soft', onClick: () => { resolvido = true; resolve('discard'); return true; } },
        { label: 'Salvar', kind: 'primary', onClick: () => { resolvido = true; resolve('save'); return true; } },
      ],
      onClose: () => { if (!resolvido) resolve('cancel'); },
    });
  });
}

function openAddStepModal() {
  const data = state.data;
  if (!data || edicaoBloqueada()) return;
  const tipos = data.tipos || {};
  const grupos = {};
  for (const [tipo, info] of Object.entries(tipos)) {
    const cat = info.categoria || 'outro';
    (grupos[cat] ||= []).push({ tipo, ...info });
  }
  const body = CATEGORY_ORDER.filter((cat) => grupos[cat]?.length).map((cat) => `
    <div class="palette-group">
      <h4>${esc(CATEGORY_LABELS[cat] || cat)}</h4>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px">
        ${grupos[cat].map((info) => `
          <button class="palette-item" data-pick-type="${esc(info.tipo)}" data-cat="${esc(cat)}" style="padding:8px 9px">
            <span class="icon">${iconMarkup(typeIcon(info.tipo), '')}</span>
            <span>${esc(info.titulo)}</span>
          </button>`).join('')}
      </div>
    </div>`).join('');
  const modal = openModal({
    title: 'Adicionar passo',
    kicker: 'BIBLIOTECA',
    subtitle: 'Escolha um bloco para começar. Você poderá ajustar todos os detalhes.',
    size: 'lg',
    body,
    actions: [{ label: 'Cancelar', kind: 'soft' }],
  });
  modal.layer.addEventListener('click', (event) => {
    const botao = event.target.closest('[data-pick-type]');
    if (!botao) return;
    modal.close();
    addStep(botao.dataset.pickType);
  });
  applyIcons(modal.layer);
}

/* ------------------------------------------------------------------ */
/* Ações de passos                                                     */
/* ------------------------------------------------------------------ */
function edicaoBloqueada() {
  if (!state.data?.executando && !state.data?.gravando) return false;
  toast('Fluxo em uso', 'Pare a execução/gravação antes de editar os passos.', 'warn', 3200);
  return true;
}

function addStep(tipo) {
  if (edicaoBloqueada()) return;
  const info = state.data?.tipos?.[tipo];
  if (!info) return;
  const params = JSON.parse(JSON.stringify(info.padrao || {}));
  openStepEditor(tipo, params, null);
}

function editStep(index) {
  if (edicaoBloqueada()) return;
  const passo = state.data?.projeto?.passos?.[index];
  if (!passo) return;
  openStepEditor(passo.tipo, JSON.parse(JSON.stringify(passo.params || {})), index);
}

async function deleteStep(index) {
  if (edicaoBloqueada()) return;
  const passo = state.data?.projeto?.passos?.[index];
  if (!passo) return;
  const ok = await confirmDialog({
    title: 'Excluir passo',
    message: `Remover o passo ${index + 1} — ${passo.titulo}?\n\n${passo.rotulo}`,
    confirmLabel: 'Excluir',
    danger: true,
  });
  if (!ok) return;
  try {
    const resposta = await callBackend('delete_step', { indice: index });
    applyState(resposta);
    const total = resposta.projeto?.passos?.length || 0;
    state.selected = total ? Math.min(index, total - 1) : null;
    updateSelection();
    toast('Passo removido', passo.titulo, 'ok');
  } catch (error) {
    toast('Falha ao excluir', error.message, 'err');
  }
}

async function duplicateStep(index) {
  if (edicaoBloqueada()) return;
  try {
    const resposta = await callBackend('duplicate_step', { indice: index });
    applyState(resposta);
    state.selected = Math.min(index + 1, (resposta.projeto?.passos?.length || 1) - 1);
    updateSelection();
    toast('Passo duplicado', '', 'ok');
  } catch (error) {
    toast('Falha ao duplicar', error.message, 'err');
  }
}

async function toggleStep(index) {
  if (edicaoBloqueada()) return;
  try {
    const resposta = await callBackend('toggle_step', { indice: index });
    applyState(resposta);
    const ativo = resposta.projeto?.passos?.[index]?.ativo;
    toast(ativo ? 'Passo reativado' : 'Passo desativado', '', 'ok', 2400);
  } catch (error) {
    toast('Falha ao alternar', error.message, 'err');
  }
}

async function moveStep(origem, destino) {
  if (origem === destino || origem == null || destino == null) return;
  if (edicaoBloqueada()) return;
  try {
    const resposta = await callBackend('move_step', { origem, destino });
    applyState(resposta);
    state.selected = destino;
    updateSelection();
  } catch (error) {
    toast('Falha ao mover', error.message, 'err');
  }
}

/* ------------------------------------------------------------------ */
/* Editor de passos                                                    */
/* ------------------------------------------------------------------ */
function fieldHtml(name, label, value, opts = {}) {
  const type = opts.type || 'text';
  const step = opts.step ? ` step="${esc(opts.step)}"` : '';
  const min = opts.min != null ? ` min="${esc(opts.min)}"` : '';
  const max = opts.max != null ? ` max="${esc(opts.max)}"` : '';
  const extra = opts.extra || '';
  const hint = opts.hint ? `<span class="hint">${esc(opts.hint)}</span>` : '';
  return `<div class="form-field ${opts.full ? 'full' : ''}">
    <label>${esc(label)}</label>
    <input type="${type}" data-field="${esc(name)}" value="${esc(value ?? '')}"${step}${min}${max} ${extra}>
    ${hint}
  </div>`;
}

function selectHtml(name, label, value, options, opts = {}) {
  return `<div class="form-field ${opts.full ? 'full' : ''}">
    <label>${esc(label)}</label>
    <select data-field="${esc(name)}">
      ${options.map((opt) => {
        const val = typeof opt === 'string' ? opt : opt.value;
        const text = typeof opt === 'string' ? opt : opt.label;
        return `<option value="${esc(val)}" ${String(val) === String(value ?? '') ? 'selected' : ''}>${esc(text)}</option>`;
      }).join('')}
    </select>
    ${opts.hint ? `<span class="hint">${esc(opts.hint)}</span>` : ''}
  </div>`;
}

function textAreaHtml(name, label, value, opts = {}) {
  return `<div class="form-field full">
    <label>${esc(label)}</label>
    <textarea data-field="${esc(name)}" rows="${esc(opts.rows || 4)}" placeholder="${esc(opts.placeholder || '')}">${esc(value ?? '')}</textarea>
    ${opts.hint ? `<span class="hint">${esc(opts.hint)}</span>` : ''}
  </div>`;
}

function checkHtml(name, label, checked, opts = {}) {
  return `<label class="checkline ${opts.full ? 'full' : ''}" style="${opts.full ? 'grid-column:1 / -1;' : ''}">
    <input type="checkbox" data-field="${esc(name)}" ${checked ? 'checked' : ''}>
    <span>${esc(label)}${opts.hint ? `<span class="hint" style="display:block">${esc(opts.hint)}</span>` : ''}</span>
  </label>`;
}

function captureButton(target, label = 'Capturar') {
  return `<button type="button" class="btn small" data-capture="${esc(target)}">${iconMarkup('crosshair')}${esc(label)}</button>`;
}

function stepFormHtml(tipo, params) {
  const p = params || {};
  const clicar = tipo === 'clicar';
  const mover = tipo === 'mover';
  const imagem = tipo.startsWith('imagem_');
  const imagemClicar = tipo === 'imagem_clicar';
  const teclas = state.data?.teclas || [];

  if (clicar || mover) {
    return `<div class="form-grid">
      ${fieldHtml('x', 'Posição X', p.x ?? 0, { type: 'number', min: 0 })}
      ${fieldHtml('y', 'Posição Y', p.y ?? 0, { type: 'number', min: 0 })}
      <div class="form-field full">
        <label>Captura rápida</label>
        <div class="input-group">${captureButton('x,y', 'Capturar ponto na tela')}</div>
      </div>
      ${fieldHtml('duracao', 'Duração do movimento (s)', p.duracao ?? 1.2, { type: 'number', step: '0.1', min: 0 })}
      ${clicar ? selectHtml('botao', 'Botão', p.botao ?? 'left', [
        { value: 'left', label: 'Esquerdo' },
        { value: 'right', label: 'Direito' },
        { value: 'middle', label: 'Meio' },
      ]) : '<div></div>'}
      ${clicar ? fieldHtml('cliques', 'Quantidade de cliques', p.cliques ?? 1, { type: 'number', min: 1, max: 5 }) : ''}
    </div>`;
  }

  if (tipo === 'arrastar') {
    return `<div class="form-grid">
      ${fieldHtml('x1', 'Origem X', p.x1 ?? 0, { type: 'number', min: 0 })}
      ${fieldHtml('y1', 'Origem Y', p.y1 ?? 0, { type: 'number', min: 0 })}
      <div class="form-field full"><div class="input-group">${captureButton('x1,y1', 'Capturar origem')}</div></div>
      ${fieldHtml('x2', 'Destino X', p.x2 ?? 0, { type: 'number', min: 0 })}
      ${fieldHtml('y2', 'Destino Y', p.y2 ?? 0, { type: 'number', min: 0 })}
      <div class="form-field full"><div class="input-group">${captureButton('x2,y2', 'Capturar destino')}</div></div>
      ${fieldHtml('duracao', 'Duração do arrasto (s)', p.duracao ?? 1, { type: 'number', step: '0.1', min: 0 })}
      ${selectHtml('botao', 'Botão', p.botao ?? 'left', [
        { value: 'left', label: 'Esquerdo' },
        { value: 'right', label: 'Direito' },
        { value: 'middle', label: 'Meio' },
      ])}
    </div>`;
  }

  if (tipo === 'rolar') {
    const moverAntes = p.mover_antes != null
      ? Boolean(p.mover_antes)
      : (p.x != null && p.y != null);
    return `<div class="form-grid">
      ${fieldHtml('quantidade', 'Quantidade de rolagem', p.quantidade ?? -3, { type: 'number', hint: 'Negativo rola para baixo; positivo para cima.' })}
      ${checkHtml('mover_antes', 'Mover o mouse antes de rolar', moverAntes, { hint: 'Se desativado, usa a posição atual do cursor.' })}
      ${fieldHtml('x', 'Posição X (opcional)', p.x ?? '', { type: 'number', min: 0 })}
      ${fieldHtml('y', 'Posição Y (opcional)', p.y ?? '', { type: 'number', min: 0 })}
    </div>`;
  }

  if (tipo === 'digitar') {
    return `<div class="form-grid">
      ${textAreaHtml('texto', 'Texto', p.texto ?? '', { rows: 6, placeholder: 'Digite o texto que será escrito…', hint: 'Acentos e caracteres especiais são suportados.' })}
      ${fieldHtml('intervalo', 'Intervalo entre caracteres (s)', p.intervalo ?? '', { type: 'number', step: '0.01', min: 0, hint: 'Deixe vazio para usar o valor das configurações.' })}
    </div>`;
  }

  if (tipo === 'atalho') {
    return `<div class="form-grid">
      ${fieldHtml('teclas', 'Atalho', Array.isArray(p.teclas) ? p.teclas.join('+') : (p.teclas ?? 'ctrl+s'), { full: true, hint: 'Separe as teclas com +. Exemplo: ctrl+shift+s' })}
    </div>`;
  }

  if (tipo === 'tecla') {
    return `<div class="form-grid">
      ${selectHtml('nome', 'Tecla', p.nome ?? 'enter', teclas)}
      ${fieldHtml('repeticoes', 'Repetições', p.repeticoes ?? 1, { type: 'number', min: 1, max: 100 })}
    </div>`;
  }

  if (tipo === 'pausa') {
    return `<div class="form-grid">${fieldHtml('segundos', 'Duração da pausa (s)', p.segundos ?? 1, { type: 'number', step: '0.1', min: 0, full: true })}</div>`;
  }

  if (imagem) {
    const falhas = [
      { value: 'abortar', label: 'Abortar o fluxo' },
      { value: 'continuar', label: 'Continuar para o próximo passo' },
    ];
    return `<div class="form-grid">
      <div class="form-field full">
        <label>Template de imagem</label>
        <div class="input-group">
          <input data-field="arquivo" value="${esc(p.arquivo ?? '')}" placeholder="nome_do_template.png">
          <button type="button" class="btn small" data-template-pick>${iconMarkup('image')}Escolher</button>
          <button type="button" class="btn small" data-template-capture>${iconMarkup('camera')}Capturar</button>
        </div>
        <div class="template-current" data-template-preview>${iconMarkup('image')}<span>Nenhum template selecionado</span></div>
      </div>
      ${fieldHtml('timeout', 'Tempo limite (s)', p.timeout ?? 15, { type: 'number', step: '0.5', min: 0.5 })}
      ${fieldHtml('confianca', 'Confiança (0.5 a 1.0)', p.confianca ?? 0.9, { type: 'number', step: '0.01', min: 0.5, max: 1 })}
      ${fieldHtml('tentativas', 'Tentativas', p.tentativas ?? 2, { type: 'number', min: 1, max: 20 })}
      ${selectHtml('se_falhar', 'Se não encontrar', p.se_falhar ?? 'abortar', falhas)}
      <div class="form-field full"><div class="input-group">
        <button type="button" class="btn soft small" data-test-template>${iconMarkup('target')}Testar template agora</button>
        <span class="hint">A janela principal será escondida durante o teste.</span>
      </div></div>
      ${imagemClicar ? `
        ${fieldHtml('duracao', 'Duração do movimento (s)', p.duracao ?? 0.5, { type: 'number', step: '0.1', min: 0 })}
        ${fieldHtml('cliques', 'Cliques', p.cliques ?? 1, { type: 'number', min: 1, max: 5 })}
        ${selectHtml('botao', 'Botão', p.botao ?? 'left', [
          { value: 'left', label: 'Esquerdo' },
          { value: 'right', label: 'Direito' },
          { value: 'middle', label: 'Meio' },
        ])}
        ${fieldHtml('offset_x', 'Deslocamento X', Array.isArray(p.offset) ? (p.offset[0] ?? 0) : 0, { type: 'number' })}
        ${fieldHtml('offset_y', 'Deslocamento Y', Array.isArray(p.offset) ? (p.offset[1] ?? 0) : 0, { type: 'number' })}
        ${checkHtml('usar_fallback', 'Usar coordenada de reserva se a imagem não for encontrada', p.fallback != null, { full: true })}
        ${fieldHtml('fallback_x', 'Reserva X', Array.isArray(p.fallback) ? p.fallback[0] : 0, { type: 'number', min: 0 })}
        ${fieldHtml('fallback_y', 'Reserva Y', Array.isArray(p.fallback) ? p.fallback[1] : 0, { type: 'number', min: 0 })}
      ` : ''}
    </div>`;
  }

  if (tipo === 'bloco_inicio') {
    return `<div class="form-grid">
      ${fieldHtml('vezes', 'Repetir bloco', p.vezes ?? 1, { type: 'number', min: 1, max: 1000, hint: 'O bloco termina no próximo passo FIM de bloco.' })}
      ${fieldHtml('nota', 'Nome do bloco', p.nota ?? '', { placeholder: 'Opcional' })}
      <p class="form-note" style="grid-column:1 / -1">O passo FIM de bloco é criado automaticamente após este.</p>
    </div>`;
  }

  if (tipo === 'bloco_fim') {
    return `<div class="form-grid">
      ${fieldHtml('nota', 'Observação', p.nota ?? '', { full: true, placeholder: 'Opcional' })}
      <p class="form-note" style="grid-column:1 / -1">Este passo fecha o último INÍCIO de bloco. A repetição fica configurada no início.</p>
    </div>`;
  }

  if (tipo === 'comentario') {
    return `<div class="form-grid">
      ${textAreaHtml('texto', 'Comentário', p.texto ?? '', { rows: 6, placeholder: 'Uma anotação para lembrar o que este trecho faz…' })}
    </div>`;
  }

  return `<div class="form-grid">${textAreaHtml('json', 'Parâmetros', JSON.stringify(p, null, 2), { rows: 8, hint: 'Tipo sem formulário dedicado; edite o JSON com cuidado.' })}</div>`;
}

function getField(root, nome) {
  return $(`[data-field="${nome}"]`, root);
}

function fieldValue(root, nome) {
  const el = getField(root, nome);
  return el ? el.value : '';
}

function fieldNumber(root, nome, fallback = 0) {
  const el = getField(root, nome);
  return el ? numberValue(el.value, fallback) : fallback;
}

function fieldInt(root, nome, fallback = 0) {
  return Math.trunc(fieldNumber(root, nome, fallback));
}

function fieldChecked(root, nome) {
  return Boolean(getField(root, nome)?.checked);
}

function collectStepParams(tipo, root, base) {
  const p = JSON.parse(JSON.stringify(base || {}));
  const text = (nome) => String(fieldValue(root, nome) ?? '').trim();

  if (tipo === 'clicar' || tipo === 'mover') {
    p.x = fieldInt(root, 'x', 0);
    p.y = fieldInt(root, 'y', 0);
    p.duracao = Math.max(0, fieldNumber(root, 'duracao', 1.2));
    if (tipo === 'clicar') {
      p.botao = text('botao') || 'left';
      p.cliques = Math.max(1, fieldInt(root, 'cliques', 1));
    }
  } else if (tipo === 'arrastar') {
    p.x1 = fieldInt(root, 'x1', 0);
    p.y1 = fieldInt(root, 'y1', 0);
    p.x2 = fieldInt(root, 'x2', 0);
    p.y2 = fieldInt(root, 'y2', 0);
    p.duracao = Math.max(0, fieldNumber(root, 'duracao', 1));
    p.botao = text('botao') || 'left';
  } else if (tipo === 'rolar') {
    p.quantidade = fieldInt(root, 'quantidade', -3);
    p.mover_antes = fieldChecked(root, 'mover_antes');
    if (p.mover_antes) {
      p.x = fieldInt(root, 'x', 0);
      p.y = fieldInt(root, 'y', 0);
    } else {
      p.x = null;
      p.y = null;
    }
  } else if (tipo === 'digitar') {
    p.texto = String(getField(root, 'texto')?.value ?? '');
    const intervalo = text('intervalo');
    p.intervalo = intervalo === '' ? null : Math.max(0, numberValue(intervalo, 0));
  } else if (tipo === 'atalho') {
    const entrada = text('teclas');
    if (!entrada) throw new Error('Informe o atalho. Exemplo: ctrl+s');
    p.teclas = entrada.split(/[+,]/).map((t) => t.trim().toLowerCase()).filter(Boolean);
    if (!p.teclas.length) throw new Error('Informe pelo menos uma tecla.');
  } else if (tipo === 'tecla') {
    p.nome = text('nome') || 'enter';
    p.repeticoes = Math.max(1, fieldInt(root, 'repeticoes', 1));
  } else if (tipo === 'pausa') {
    p.segundos = Math.max(0, fieldNumber(root, 'segundos', 1));
  } else if (tipo.startsWith('imagem_')) {
    p.arquivo = text('arquivo');
    if (!p.arquivo) throw new Error('Escolha ou capture um template de imagem.');
    p.timeout = Math.max(0.5, fieldNumber(root, 'timeout', 15));
    p.confianca = Math.min(1, Math.max(0.5, fieldNumber(root, 'confianca', 0.9)));
    p.tentativas = Math.max(1, fieldInt(root, 'tentativas', 2));
    p.se_falhar = text('se_falhar') || 'abortar';
    if (tipo === 'imagem_clicar') {
      p.duracao = Math.max(0, fieldNumber(root, 'duracao', 0.5));
      p.cliques = Math.max(1, fieldInt(root, 'cliques', 1));
      p.botao = text('botao') || 'left';
      p.offset = [fieldInt(root, 'offset_x', 0), fieldInt(root, 'offset_y', 0)];
      p.fallback = fieldChecked(root, 'usar_fallback')
        ? [fieldInt(root, 'fallback_x', 0), fieldInt(root, 'fallback_y', 0)]
        : null;
    }
  } else if (tipo === 'bloco_inicio') {
    p.vezes = Math.max(1, fieldInt(root, 'vezes', 1));
    p.nota = text('nota');
  } else if (tipo === 'bloco_fim') {
    p.nota = text('nota');
  } else if (tipo === 'comentario') {
    p.texto = String(getField(root, 'texto')?.value ?? '');
  } else {
    const bruto = String(getField(root, 'json')?.value ?? '{}');
    return JSON.parse(bruto);
  }
  return p;
}

function updateTemplatePreview(container, nome) {
  if (!container) return;
  if (!nome) {
    container.innerHTML = `${iconMarkup('image')}<span>Nenhum template selecionado</span>`;
    return;
  }
  container.innerHTML = `${iconMarkup('image')}<span>${esc(nome)}</span>`;
  callBackend('template_data', { nome })
    .then((dados) => {
      if (dados?.data_url) {
        container.innerHTML = `<img src="${esc(dados.data_url)}" alt="${esc(nome)}"><span>${esc(nome)}</span>`;
      }
    })
    .catch(() => {});
}

async function capturePointTo(targets, root) {
  try {
    const resposta = await bridge()?.capture_point?.();
    if (!resposta || resposta.ok !== true) throw new Error(resposta?.erro || 'Captura cancelada.');
    const ponto = resposta.data?.ponto;
    if (!ponto) {
      toast('Captura cancelada', 'Nenhum ponto foi selecionado.', 'warn', 2600);
      return;
    }
    for (const target of targets) {
      const nome = target.trim();
      if (!nome) continue;
      if (nome === 'x,y') {
        const x = getField(root, 'x');
        const y = getField(root, 'y');
        if (x) x.value = String(ponto[0]);
        if (y) y.value = String(ponto[1]);
      } else {
        const campo = getField(root, nome);
        if (campo) {
          const index = /(?:^|_)y\d*$/.test(nome) ? 1 : 0;
          campo.value = String(ponto[index] ?? ponto[0]);
        }
      }
    }
    toast('Ponto capturado', `${ponto[0]}, ${ponto[1]}`, 'ok', 2200);
  } catch (error) {
    if (ehCancelamento(error?.message)) {
      toast('Captura cancelada', 'Nenhum ponto foi alterado.', 'warn', 2400);
    } else {
      toast('Captura indisponível', error.message, 'err');
    }
  }
}

async function captureTemplateTo(root) {
  try {
    const nome = await promptText({
      title: 'Capturar template',
      kicker: 'BUSCA POR IMAGEM',
      subtitle: 'A janela principal será escondida. Arraste para marcar a região.',
      label: 'Nome do template',
      value: 'regiao',
      confirmLabel: 'Capturar região',
    });
    if (nome == null) return;
    const resposta = await bridge()?.capture_region?.(String(nome).trim() || 'regiao');
    if (!resposta || resposta.ok !== true) throw new Error(resposta?.erro || 'Captura cancelada.');
    const arquivo = resposta.data?.nome;
    if (!arquivo) {
      toast('Captura cancelada', 'Nenhuma região foi salva.', 'warn', 2600);
      return;
    }
    const campo = getField(root, 'arquivo');
    if (campo) campo.value = arquivo;
    updateTemplatePreview($('[data-template-preview]', root), arquivo);
    toast('Template salvo', arquivo, 'ok');
  } catch (error) {
    if (ehCancelamento(error?.message)) {
      toast('Captura cancelada', 'Nenhuma região foi salva.', 'warn', 2400);
    } else {
      toast('Falha ao capturar template', error.message, 'err');
    }
  }
}

async function testTemplateFrom(root) {
  const nome = String(fieldValue(root, 'arquivo') || '').trim();
  const confianca = fieldNumber(root, 'confianca', 0.9);
  if (!nome) {
    toast('Escolha um template', 'Selecione uma imagem antes de testar.', 'warn');
    return;
  }
  try {
    const resposta = await bridge()?.test_template?.(nome, confianca);
    if (!resposta || resposta.ok !== true) throw new Error(resposta?.erro || 'Teste falhou.');
    const dados = resposta.data || {};
    openModal({
      title: dados.encontrada ? 'Template encontrado' : 'Template não encontrado',
      kicker: 'DIAGNÓSTICO',
      subtitle: nome,
      size: 'sm',
      body: `<p class="form-note" style="white-space:pre-wrap;font-size: var(--fs-sm);line-height:1.7">${esc(dados.texto || '')}</p>`,
      actions: [{ label: 'Fechar', kind: 'soft' }],
    });
  } catch (error) {
    toast('Teste indisponível', error.message, 'err');
  }
}

function openStepEditor(tipo, params, index) {
  const info = state.data?.tipos?.[tipo];
  const titulo = info?.titulo || tipo;
  const editando = index != null;
  let modal;
  modal = openModal({
    title: editando ? `Editar passo ${index + 1}` : `Novo passo — ${titulo}`,
    kicker: editando ? 'EDIÇÃO' : 'NOVO PASSO',
    subtitle: editando ? 'Ajuste os detalhes e salve no fluxo.' : 'Configure o bloco antes de adicioná-lo.',
    size: 'lg',
    body: stepFormHtml(tipo, params),
    actions: [
      { label: 'Cancelar', kind: 'soft' },
      {
        label: editando ? 'Salvar alterações' : 'Adicionar ao fluxo',
        kind: 'primary',
        onClick: async (ctx) => {
          let dados;
          try {
            dados = collectStepParams(tipo, ctx.body, params);
          } catch (error) {
            toast('Verifique os campos', error.message, 'warn');
            return false;
          }
          try {
            if (editando) {
              const resposta = await callBackend('update_step', { indice: index, tipo, params: dados });
              absorb(resposta);
              state.selected = index;
            } else {
              const posicao = state.selected == null ? undefined : state.selected + 1;
              const resposta = await callBackend('add_step', { tipo, params: dados, indice: posicao });
              absorb(resposta);
              state.selected = resposta.indice ?? (state.data.projeto.passos.length - 1);
            }
            updateSelection();
            toast(editando ? 'Passo atualizado' : 'Passo adicionado', titulo, 'ok', 2600);
            return true;
          } catch (error) {
            toast('Não foi possível salvar', error.message, 'err');
            return false;
          }
        },
      },
    ],
    onMount: (ctx) => {
      if (tipo.startsWith('imagem_')) {
        updateTemplatePreview($('[data-template-preview]', ctx.body), fieldValue(ctx.body, 'arquivo'));
      }
    },
  });

  modal.layer.addEventListener('click', async (event) => {
    const captura = event.target.closest('[data-capture]');
    if (captura) {
      event.preventDefault();
      await capturePointTo(captura.dataset.capture.split(','), modal.body);
      return;
    }
    if (event.target.closest('[data-template-pick]')) {
      event.preventDefault();
      openTemplateManager(fieldValue(modal.body, 'arquivo'), (nome) => {
        const campo = getField(modal.body, 'arquivo');
        if (campo) campo.value = nome;
        updateTemplatePreview($('[data-template-preview]', modal.body), nome);
      });
      return;
    }
    if (event.target.closest('[data-template-capture]')) {
      event.preventDefault();
      await captureTemplateTo(modal.body);
      return;
    }
    if (event.target.closest('[data-test-template]')) {
      event.preventDefault();
      await testTemplateFrom(modal.body);
    }
  });
}

/* ------------------------------------------------------------------ */
/* Gerenciador de templates                                            */
/* ------------------------------------------------------------------ */
async function openTemplateManager(inicial = '', onChoose = null) {
  let templates = [];
  try {
    const resposta = await callBackend('list_templates');
    templates = resposta.templates || [];
  } catch (error) {
    toast('Não foi possível listar templates', error.message, 'err');
  }
  let selecionado = inicial || templates[0]?.nome || null;
  let requisicao = 0;
  let recarregar = async () => {};

  const modal = openModal({
    title: 'Templates de imagem',
    kicker: 'BIBLIOTECA VISUAL',
    subtitle: 'Imagens usadas pelos passos de busca. Capture, importe ou remova templates.',
    size: 'xl',
    body: `<div class="template-manager">
      <div>
        <div class="search-field" style="width:100%;margin-bottom:7px">
          ${iconMarkup('search')}<input id="template-filter" placeholder="Filtrar templates…" autocomplete="off">
        </div>
        <div class="template-list" data-template-list></div>
      </div>
      <div class="template-preview" data-template-preview-large>
        <span>Selecione um template.</span>
      </div>
    </div>`,
    actions: [
      {
        label: 'Importar pasta',
        kind: 'soft',
        onClick: async () => {
          const pasta = await bridge()?.folder_dialog?.('Importar templates');
          if (!pasta?.caminho) return false;
          try {
            const info = await callBackend('import_templates', { pasta: pasta.caminho });
            toast('Templates importados', `${info.novos} novo(s), ${info.iguais} repetido(s).`, 'ok');
            await recarregar();
          } catch (error) {
            toast('Falha ao importar', error.message, 'err');
          }
          return false;
        },
      },
      {
        label: 'Remover',
        kind: 'danger-soft',
        onClick: async () => {
          if (!selecionado) {
            toast('Selecione um template', '', 'warn');
            return false;
          }
          const ok = await confirmDialog({
            title: 'Remover template',
            message: `Remover "${selecionado}" da biblioteca? Os passos que usam essa imagem deixarão de encontrá-la.`,
            confirmLabel: 'Remover',
            danger: true,
          });
          if (!ok) return false;
          try {
            await callBackend('remove_template', { nome: selecionado });
            toast('Template removido', selecionado, 'ok');
            selecionado = null;
            await recarregar();
          } catch (error) {
            toast('Falha ao remover', error.message, 'err');
          }
          return false;
        },
      },
      { label: 'Cancelar', kind: 'soft' },
      {
        label: onChoose ? 'Usar template' : 'Fechar',
        kind: 'primary',
        onClick: () => {
          if (onChoose && selecionado) onChoose(selecionado);
          return true;
        },
      },
    ],
    onMount: (ctx) => {
      const lista = $('[data-template-list]', ctx.body);
      const preview = $('[data-template-preview-large]', ctx.body);
      const filtro = $('#template-filter', ctx.body);

      const mostrarPreview = (nome) => {
        if (!nome) {
          preview.innerHTML = '<span>Selecione um template.</span>';
          return;
        }
        const token = ++requisicao;
        preview.innerHTML = '<span>Carregando…</span>';
        callBackend('template_data', { nome })
          .then((dados) => {
            if (token !== requisicao) return;
            preview.innerHTML = `<img src="${esc(dados.data_url)}" alt="${esc(nome)}">`;
          })
          .catch(() => {
            if (token === requisicao) preview.innerHTML = '<span>Prévia indisponível.</span>';
          });
      };

      const renderLista = () => {
        const termo = String(filtro?.value || '').trim().toLowerCase();
        const visiveis = templates.filter((item) => item.nome.toLowerCase().includes(termo));
        if (!visiveis.length) {
          lista.innerHTML = `<div class="form-note" style="padding:16px 6px">${templates.length ? 'Nenhum template corresponde ao filtro.' : 'Nenhum template salvo ainda. Capture uma região ou importe uma pasta.'}</div>`;
          return;
        }
        lista.innerHTML = visiveis.map((item) => `
          <button class="template-item ${item.nome === selecionado ? 'is-selected' : ''}" data-template-name="${esc(item.nome)}">
            <span class="icon">${iconMarkup('image', '')}</span>
            <span class="tpl-name">${esc(item.nome)}</span>
            <span class="tpl-size">${item.largura || 0}×${item.altura || 0}</span>
          </button>`).join('');
        applyIcons(lista);
      };

      const selecionar = (nome) => {
        selecionado = nome;
        $$('[data-template-name]', lista).forEach((el) => {
          el.classList.toggle('is-selected', el.dataset.templateName === nome);
        });
        mostrarPreview(nome);
      };

      recarregar = async () => {
        try {
          const resposta = await callBackend('list_templates');
          templates = resposta.templates || [];
        } catch (error) {
          templates = [];
        }
        if (selecionado && !templates.some((item) => item.nome === selecionado)) selecionado = null;
        if (!selecionado) selecionado = templates[0]?.nome || null;
        renderLista();
        mostrarPreview(selecionado);
      };

      modal.recarregarTemplates = recarregar;

      lista.addEventListener('click', (event) => {
        const item = event.target.closest('[data-template-name]');
        if (!item) return;
        selecionar(item.dataset.templateName);
      });
      lista.addEventListener('dblclick', (event) => {
        const item = event.target.closest('[data-template-name]');
        if (!item) return;
        selecionar(item.dataset.templateName);
        if (onChoose) {
          onChoose(item.dataset.templateName);
          modal.close();
        }
      });
      filtro?.addEventListener('input', renderLista);
      renderLista();
      mostrarPreview(selecionado);
    },
  });

  return modal;
}

/* ------------------------------------------------------------------ */
/* Configurações                                                       */
/* ------------------------------------------------------------------ */
function configCard(titulo, subtitulo, icone, conteudo) {
  return `<section class="config-card">
    <div class="config-card-head">
      <span class="config-card-icon">${iconMarkup(icone)}</span>
      <div><h3>${esc(titulo)}</h3><p>${esc(subtitulo)}</p></div>
    </div>
    <div class="config-card-body">${conteudo}</div>
  </section>`;
}

function cfgRow(label, controle, hint = '', classe = '') {
  return `<div class="config-row${classe ? ` ${classe}` : ''}">
    <div class="config-label">${esc(label)}${hint ? `<small>${esc(hint)}</small>` : ''}</div>
    <div class="config-control">${controle}</div>
  </div>`;
}

function rangeRow(label, key, min, max, step, hint = '') {
  return cfgRow(label, `<div class="range-wrap"><input type="range" data-cfg="${esc(key)}" min="${esc(min)}" max="${esc(max)}" step="${esc(step)}"><span class="range-value" data-val="${esc(key)}"></span></div>`, hint);
}

function numberRow(label, key, min, max, step = 1, hint = '') {
  return cfgRow(label, `<input class="field" type="number" data-cfg="${esc(key)}" min="${esc(min)}" max="${esc(max)}" step="${esc(step)}">`, hint);
}

function selectRow(label, key, options, hint = '') {
  return cfgRow(label, `<select class="field" data-cfg="${esc(key)}">${options.map((opt) => `<option value="${esc(opt.value ?? opt)}">${esc(opt.label ?? opt)}</option>`).join('')}</select>`, hint);
}

function switchRow(label, key, hint = '') {
  return cfgRow(label, `<label class="switch-label"><input type="checkbox" data-cfg="${esc(key)}"><span class="switch-track"><span class="switch-knob"></span></span><span data-switch-label="${esc(key)}"></span></label>`, hint);
}

function renderConfig() {
  const host = $('#config-scroll');
  if (!host || !state.data) return;
  const data = state.data;
  const fontes = data.fontes || ['Segoe UI'];

  const interfaceCfg = [
    selectRow('Fonte', 'fonte', fontes),
    numberRow('Escala da interface', 'escala_web', 15, 22, 1, 'Tamanho real de toda a interface, em pixels.'),
  ].join('');

  const execucao = [
    rangeRow('Movimento do mouse', 'duracao_movimento', 0, 3, 0.1, 'Duração padrão para mover e clicar.'),
    rangeRow('Pausa entre ações', 'pausa_entre_acoes', 0, 2, 0.05),
    rangeRow('Intervalo de digitação', 'intervalo_digitacao', 0, 0.5, 0.01),
    numberRow('Contagem antes de executar (s)', 'tempo_inicio', 0, 30, 1),
  ].join('');

  const imagensCfg = [
    rangeRow('Confiança mínima', 'confianca_imagem', 0.5, 1, 0.01),
    selectRow('Quando não encontrar', 'ao_falhar', [
      { value: 'abortar', label: 'Abortar o fluxo' },
      { value: 'continuar', label: 'Continuar para o próximo passo' },
    ]),
  ].join('');

  const gravacao = [
    switchRow('Registrar movimentos do mouse', 'registrar_movimento'),
    switchRow('Recortar imagens automaticamente', 'registrar_recorte', 'Cada clique vira um passo de imagem com coordenada de reserva.'),
    switchRow('Registrar pausas', 'registrar_pausas'),
  ].join('');

  host.innerHTML = [
    configCard('Interface', 'Fonte e escala', 'sliders', interfaceCfg),
    configCard('Execução', 'Ritmo do mouse, teclado e início', 'gauge', execucao),
    configCard('Imagem', 'Tolerância e falhas na busca', 'target', imagensCfg),
    configCard('Gravação', 'O que capturar enquanto grava', 'camera', gravacao),
  ].join('');

  state.configRendered = true;
  applyIcons(host);
  syncConfig();
}

function formatConfigValue(key, value) {
  const n = numberValue(value, 0);
  if (key === 'escala_web') return `${Math.round(n)} px`;
  if (['confianca_imagem'].includes(key)) return `${Math.round(n * 100)}%`;
  if (['duracao_movimento', 'pausa_entre_acoes', 'intervalo_digitacao'].includes(key)) {
    return `${n.toFixed(2).replace(/\.?0+$/, '')}s`;
  }
  return String(value ?? '');
}

function syncConfig() {
  if (!state.data?.config) return;
  const cfg = state.data.config;
  const host = $('#config-scroll');
  if (!host) return;
  $$('[data-cfg]', host).forEach((el) => {
    const key = el.dataset.cfg;
    const value = cfg[key];
    if (el.type === 'checkbox') {
      el.checked = Boolean(value);
    } else if (document.activeElement !== el) {
      el.value = value == null ? '' : value;
    }
  });
  $$('[data-val]', host).forEach((el) => {
    el.textContent = formatConfigValue(el.dataset.val, cfg[el.dataset.val]);
  });
  $$('[data-switch-label]', host).forEach((el) => {
    el.textContent = cfg[el.dataset.switchLabel] ? 'Ativado' : 'Desativado';
  });
}

function queueConfig(patch, delay = 160) {
  Object.assign(state.pendingConfig, patch);
  clearTimeout(state.configTimer);
  state.configTimer = setTimeout(applyPendingConfig, delay);
}

async function applyPendingConfig() {
  if (state.configSaving) return;
  const patch = state.pendingConfig;
  state.pendingConfig = {};
  if (!Object.keys(patch).length) return;
  state.configSaving = true;
  try {
    const resposta = await callBackend('set_config', { patch });
    if (resposta?.projeto) applyState(resposta);
    const saveState = $('#config-save-state');
    if (saveState) {
      saveState.textContent = 'Salvo agora';
      setTimeout(() => { if (saveState.textContent === 'Salvo agora') saveState.textContent = 'Salvo automaticamente'; }, 1800);
    }
  } catch (error) {
    toast('Falha ao salvar configuração', error.message, 'err');
    syncConfig();
  } finally {
    state.configSaving = false;
    if (Object.keys(state.pendingConfig).length) applyPendingConfig();
  }
}

function flushConfig() {
  if (!Object.keys(state.pendingConfig).length) return;
  clearTimeout(state.configTimer);
  applyPendingConfig();
}

function handleConfigInput(event) {
  const alvo = event.target;
  if (!alvo.matches('[data-cfg]')) return;
  const key = alvo.dataset.cfg;
  let value;
  if (alvo.type === 'checkbox') value = alvo.checked;
  else if (alvo.type === 'number' || alvo.type === 'range') value = numberValue(alvo.value, 0);
  else value = alvo.value;
  if (alvo.type === 'range' || alvo.type === 'number') {
    const label = $(`[data-val="${key}"]`);
    if (label) label.textContent = formatConfigValue(key, value);
  }
  queueConfig({ [key]: value }, alvo.type === 'checkbox' ? 0 : 180);
}

/* ------------------------------------------------------------------ */
/* Log                                                                 */
/* ------------------------------------------------------------------ */
function renderLogs(force = false) {
  const view = $('#log-view');
  if (!view || !state.data) return;
  const logs = (state.data.logs || []).slice(-800);
  const filtro = state.logFilter.trim().toLowerCase();
  const chave = `${filtro}|${logs.length}|${logs[logs.length - 1] || ''}|${logs[0] || ''}`;
  if (!force && chave === state.logKey) return;
  state.logKey = chave;

  let visiveis = 0;
  view.innerHTML = logs.map((linha) => {
    const combina = !filtro || String(linha).toLowerCase().includes(filtro);
    if (combina) visiveis += 1;
    const match = String(linha).match(/^(\d{2}:\d{2}:\d{2})\s+(.*)$/);
    const hora = match ? match[1] : '';
    const mensagem = match ? match[2] : String(linha);
    const baixa = mensagem.toLowerCase();
    let classe = '';
    if (baixa.includes('erro') || baixa.includes('falha') || baixa.includes('exception')) classe = 'is-err';
    else if (baixa.includes('aviso') || baixa.includes('warn')) classe = 'is-warn';
    else if (baixa.includes('[export]') || baixa.includes('[template]')) classe = 'is-export';
    else if (baixa.includes('conclu') || baixa.includes('[ok]') || baixa.includes('salvo')) classe = 'is-ok';
    return `<div class="log-line ${classe} ${combina ? '' : 'is-filtered'}">${hora ? `<span class="log-time">${esc(hora)}</span>` : ''}<span class="log-msg">${esc(mensagem)}</span></div>`;
  }).join('');

  const empty = $('#log-empty');
  if (empty) {
    empty.classList.toggle('is-on', logs.length === 0);
    empty.textContent = logs.length ? '' : 'Nenhuma atividade registrada ainda.';
  }
  const count = $('#log-count');
  if (count) count.textContent = `${visiveis} de ${logs.length} linha${logs.length === 1 ? '' : 's'}`;
  const auto = $('#log-autoscroll');
  if (auto?.checked && state.tab === 'log') view.scrollTop = view.scrollHeight;
}

/* ------------------------------------------------------------------ */
/* Projeto e arquivos                                                  */
/* ------------------------------------------------------------------ */
async function saveAsProject() {
  try {
    const nome = state.data?.projeto?.nome || 'projeto';
    const resposta = await bridge()?.save_project_dialog?.(nome);
    const caminho = resposta?.caminho;
    if (!caminho) return false;
    const salvo = await callBackend('save_as', { caminho });
    absorb(salvo);
    toast('Projeto salvo', salvo.caminho || caminho, 'ok');
    return true;
  } catch (error) {
    toast('Falha ao salvar', error.message, 'err');
    return false;
  }
}

async function saveProject() {
  const projeto = state.data?.projeto;
  if (!projeto) return false;
  if (!projeto.caminho) return saveAsProject();
  try {
    const salvo = await callBackend('save');
    absorb(salvo);
    toast('Projeto salvo', salvo.caminho || projeto.caminho, 'ok', 2600);
    return true;
  } catch (error) {
    toast('Falha ao salvar', error.message, 'err');
    return false;
  }
}

async function ensureSaved() {
  if (!state.data?.projeto?.alterado) return true;
  const escolha = await askSaveChanges();
  if (escolha === 'cancel') return false;
  if (escolha === 'save') return saveProject();
  return true;
}

async function quitApp() {
  const api = bridge();
  if (!api) return;
  flushConfig();
  try {
    if (state.data?.executando || state.data?.gravando) {
      const confirmar = await confirmDialog({
        title: 'Sair',
        message: 'Uma execução ou gravação está em andamento. Parar tudo e sair?',
        confirmLabel: 'Parar e sair',
        danger: true,
        kicker: 'El Gravador 18 Pro Max',
      });
      if (!confirmar) {
        await api.cancelar_fechamento?.();
        return;
      }
      try { await callBackend('stop_execution'); } catch (_) { /* já parou */ }
      try { await callBackend('stop_recording'); } catch (_) { /* já parou */ }
    }
    if (!(await ensureSaved())) {
      await api.cancelar_fechamento?.();
      return;
    }
    const resposta = await api.quit_app?.();
    if (!resposta || resposta.ok !== true) {
      throw new Error(resposta?.erro || 'O aplicativo não confirmou o fechamento.');
    }
  } catch (error) {
    toast('Não foi possível sair', error.message, 'err');
    await api.cancelar_fechamento?.();
  }
}

window.__elgravadorSolicitarFechamento = () => {
  quitApp();
};

async function newProject() {
  if (edicaoBloqueada()) return;
  if (!(await ensureSaved())) return;
  try {
    const resposta = await callBackend('new_project');
    applyState(resposta);
    state.selected = null;
    updateSelection();
    switchTab('fluxo');
    toast('Novo projeto', 'Um fluxo limpo para começar.', 'ok');
  } catch (error) {
    toast('Falha ao criar projeto', error.message, 'err');
  }
}

async function openProject() {
  if (edicaoBloqueada()) return;
  if (!(await ensureSaved())) return;
  try {
    const resposta = await bridge()?.open_project_dialog?.();
    const caminho = resposta?.caminho;
    if (!caminho) return;
    const aberto = await callBackend('open', { caminho });
    applyState(aberto);
    state.selected = null;
    updateSelection();
    switchTab('fluxo');
    toast('Projeto aberto', aberto.projeto?.nome || caminho, 'ok');
  } catch (error) {
    toast('Falha ao abrir', error.message, 'err');
  }
}

async function renameProject(nome) {
  const limpo = String(nome || '').trim();
  if (!limpo || limpo === state.data?.projeto?.nome) {
    $('#project-name').value = state.data?.projeto?.nome || 'novo_projeto';
    return;
  }
  try {
    const resposta = await callBackend('rename', { nome: limpo });
    applyState(resposta);
    toast('Projeto renomeado', limpo, 'ok', 2200);
  } catch (error) {
    toast('Não foi possível renomear', error.message, 'err');
    $('#project-name').value = state.data?.projeto?.nome || 'novo_projeto';
  }
}

async function setRepetitions(valor) {
  const numero = Math.max(0, Math.min(100000, Math.trunc(numberValue(valor, 1))));
  try {
    const resposta = await callBackend('set_repetitions', { valor: numero });
    applyState(resposta);
    $('#repeat-input').value = numero;
  } catch (error) {
    toast('Falha ao alterar repetições', error.message, 'err');
    $('#repeat-input').value = state.data?.projeto?.repeticoes ?? 1;
  }
}

async function setSimulate(valor) {
  try {
    const resposta = await callBackend('set_simulate', { valor: Boolean(valor) });
    applyState(resposta);
    toast(Boolean(valor) ? 'Modo simulação ativado' : 'Modo real ativado', Boolean(valor) ? 'Nada será controlado de verdade.' : 'O robô controlará mouse e teclado.', 'info', 3000);
  } catch (error) {
    toast('Falha ao alternar modo', error.message, 'err');
    $('#simulate-switch').checked = !valor;
  }
}

async function undo() {
  if (edicaoBloqueada()) return;
  try {
    const resposta = await callBackend('undo');
    applyState(resposta);
    toast('Alteração desfeita', '', 'ok', 2000);
  } catch (error) {
    toast('Nada para desfazer', error.message, 'warn', 2600);
  }
}

async function generateScript() {
  if (!state.data?.projeto?.passos?.length) {
    toast('Fluxo vazio', 'Adicione pelo menos um passo antes de gerar o script.', 'warn');
    return;
  }
  let validacao;
  try {
    validacao = await callBackend('validate');
  } catch (error) {
    toast('Falha ao validar', error.message, 'err');
    return;
  }
  const problemas = validacao.problemas || [];
  const ausentes = validacao.templates_ausentes || [];
  if (problemas.length || ausentes.length) {
    const partes = [];
    if (problemas.length) partes.push(`Problemas no fluxo:\n${problemas.map((p) => `• ${p}`).join('\n')}`);
    if (ausentes.length) partes.push(`Templates ausentes:\n${ausentes.map((p) => `• ${p}`).join('\n')}`);
    const continuar = await confirmDialog({
      title: 'O script pode falhar',
      message: partes.join('\n\n') + '\n\nDeseja gerar mesmo assim?',
      confirmLabel: 'Gerar mesmo assim',
      danger: true,
    });
    if (!continuar) return;
  }

  const repeticoes = await promptText({
    title: 'Gerar script',
    kicker: 'EXPORTAÇÃO',
    subtitle: 'O script .py será criado junto com um sidecar do projeto e os templates usados.',
    label: 'Repetições',
    value: String(state.data.projeto.repeticoes ?? 1),
    confirmLabel: 'Escolher destino',
  });
  if (repeticoes == null) return;
  let destino;
  try {
    const escolha = await bridge()?.save_script_dialog?.(state.data.projeto.nome || 'automacao');
    destino = escolha?.caminho;
  } catch (error) {
    toast('Falha ao escolher destino', error.message, 'err');
    return;
  }
  if (!destino) return;
  try {
    const info = await callBackend('generate', {
      caminho: destino,
      repeticoes: Math.max(0, Math.trunc(numberValue(repeticoes, 1))),
    });
    const ausentesTexto = info.templates_ausentes?.length
      ? `<p class="form-note" style="color:var(--orange)">Atenção: ${esc(info.templates_ausentes.join(', '))}</p>`
      : '';
    openModal({
      title: 'Script gerado',
      kicker: 'EXPORTAÇÃO CONCLUÍDA',
      subtitle: 'O arquivo está pronto para ser executado com Python.',
      size: 'sm',
      body: `<div class="form-note" style="font-family:var(--mono);font-size: var(--fs-caption);line-height:1.7;word-break:break-all">${esc(info.script || destino)}</div>
        <p class="form-note">${info.templates?.length || 0} template(s) copiado(s).</p>${ausentesTexto}`,
      actions: [
        {
          label: 'Abrir pasta',
          kind: 'soft',
          onClick: () => { openFolderPath(destino); return true; },
        },
        { label: 'Fechar', kind: 'primary' },
      ],
    });
    switchTab('log');
  } catch (error) {
    toast('Falha ao gerar script', error.message, 'err');
  }
}

async function openFolder(key) {
  try {
    await callBackend('open_folder', { chave: key || 'base' });
  } catch (error) {
    toast('Não foi possível abrir a pasta', error.message, 'err');
  }
}

function openFolderPath(caminho) {
  if (!caminho) return;
  const pai = String(caminho).replace(/[\\/][^\\/]*$/, '');
  openFolder(pai);
}

async function clearLog() {
  try {
    await callBackend('clear_log');
    state.logKey = '';
    if (state.data) state.data.logs = [];
    renderLogs(true);
    toast('Log limpo', '', 'ok', 2000);
  } catch (error) {
    toast('Falha ao limpar log', error.message, 'err');
  }
}

async function showProblems() {
  try {
    const dados = await callBackend('validate');
    const problemas = dados.problemas || [];
    const ausentes = dados.templates_ausentes || [];
    if (!problemas.length && !ausentes.length) {
      toast('Fluxo válido', 'Nenhum problema encontrado.', 'ok');
      return;
    }
    const blocos = [];
    if (problemas.length) blocos.push(`<strong>Fluxo</strong><ul style="margin:4px 0 10px 16px;padding:0">${problemas.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>`);
    if (ausentes.length) blocos.push(`<strong>Templates ausentes</strong><ul style="margin:4px 0 0 16px;padding:0">${ausentes.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>`);
    openModal({
      title: 'Validação do fluxo',
      kicker: 'DIAGNÓSTICO',
      size: 'sm',
      body: `<div class="form-note" style="font-size: var(--fs-caption)">${blocos.join('')}</div>`,
      actions: [{ label: 'Fechar', kind: 'primary' }],
    });
  } catch (error) {
    toast('Falha ao validar', error.message, 'err');
  }
}

/* ------------------------------------------------------------------ */
/* Execução e gravação                                                 */
/* ------------------------------------------------------------------ */
async function toggleRecord() {
  if (!state.data) return;
  if (state.data.gravando) {
    try {
      const resposta = await callBackend('stop_recording');
      applyState(resposta);
      toast('Gravação encerrada', 'Os passos foram adicionados ao fluxo.', 'ok');
    } catch (error) {
      toast('Falha ao parar gravação', error.message, 'err');
    }
    return;
  }
  try {
    const resposta = await bridge()?.start_recording?.();
    if (!resposta || resposta.ok !== true) throw new Error(resposta?.erro || 'Não foi possível gravar.');
    toast('Gravação iniciada', 'Use F9 para parar, F10 para pausar e ESC para descartar.', 'warn', 6000);
  } catch (error) {
    toast('Gravação indisponível', error.message, 'err');
  }
}

async function execute(mode = 'tudo') {
  const projeto = state.data?.projeto;
  if (!projeto?.passos?.length) {
    toast('Fluxo vazio', 'Adicione passos antes de executar.', 'warn');
    return;
  }
  if (['daqui', 'ate', 'teste'].includes(mode) && state.selected == null) {
    toast('Selecione um passo', 'Escolha um passo no fluxo para esta ação.', 'warn');
    return;
  }
  try {
    const resposta = await bridge()?.start_execution?.(mode, state.selected);
    if (!resposta || resposta.ok !== true) throw new Error(resposta?.erro || 'Não foi possível executar.');
    if (resposta.data?.simular) toast('Simulação iniciada', 'Acompanhe o status no rodapé e no log.', 'info');
    else toast('Execução iniciada', 'A janela será escondida durante a automação.', 'ok', 4200);
  } catch (error) {
    toast('Execução não iniciada', error.message, 'err', 7000);
  }
}

async function pauseExecution() {
  try {
    const resposta = await callBackend('pause_execution');
    applyState(resposta);
    toast(resposta.pausado ? 'Execução pausada' : 'Execução retomada', '', 'info', 2200);
  } catch (error) {
    toast('Falha ao pausar', error.message, 'err');
  }
}

async function stopExecution() {
  try {
    const resposta = await callBackend('stop_execution');
    applyState(resposta);
    toast('Execução interrompida', '', 'warn', 2600);
  } catch (error) {
    toast('Falha ao parar', error.message, 'err');
  }
}

/* ------------------------------------------------------------------ */
/* Ajuda                                                               */
/* ------------------------------------------------------------------ */
function showHelp() {
  openModal({
    title: 'Atalhos e dicas',
    kicker: 'El Gravador 18 Pro Max',
    subtitle: 'Os atalhos funcionam mesmo com a janela principal escondida.',
    size: 'lg',
    body: `<div class="form-grid">
      <div class="form-note"><strong>Durante a gravação</strong><br>F9 encerra e adiciona os passos.<br>F10 pausa/retoma.<br>ESC descarta.</div>
      <div class="form-note"><strong>Durante a execução</strong><br>F8 pausa/retoma.<br>ESC interrompe.<br>O HUD mostra o passo atual.</div>
      <div class="form-note"><strong>Na interface</strong><br>Ctrl+N novo · Ctrl+O abrir<br>Ctrl+S salvar · Ctrl+Shift+S salvar como<br>Ctrl+R executar · Ctrl+Z desfazer</div>
      <div class="form-note"><strong>Passos</strong><br>Duplo clique edita.<br>Arraste para reordenar.<br>Delete exclui · Espaço ativa/desativa.</div>
      <div class="form-note" style="grid-column:1/-1"><strong>Dica de imagem</strong><br>Prefira templates pequenos e únicos. Use o botão <em>Testar template agora</em> no editor para conferir a confiança antes de executar.</div>
    </div>`,
    actions: [{ label: 'Fechar', kind: 'primary' }],
  });
}

/* ------------------------------------------------------------------ */
/* Menu, ações e atalhos                                               */
/* ------------------------------------------------------------------ */
function menuItem(action, icone, label, atalho = '') {
  return `<button data-menu-action="${esc(action)}">${iconMarkup(icone)}<span>${esc(label)}</span>${atalho ? `<span class="menu-shortcut">${esc(atalho)}</span>` : ''}</button>`;
}

function toggleMoreMenu(force) {
  const menu = $('#more-menu');
  if (!menu) return;
  const abrir = force == null ? menu.hidden : Boolean(force);
  if (!abrir) {
    menu.hidden = true;
    return;
  }
  menu.innerHTML = [
    menuItem('execute-all', 'play', 'Executar tudo', 'Ctrl R'),
    menuItem('execute-here', 'target', 'Executar daqui em diante'),
    menuItem('test-step', 'crosshair', 'Testar este passo'),
    '<div class="menu-sep"></div>',
    menuItem('save-as', 'save', 'Salvar como…', 'Ctrl Shift S'),
    menuItem('generate-script', 'code', 'Gerar script .py', 'Ctrl G'),
    '<div class="menu-sep"></div>',
    menuItem('open-templates', 'image', 'Gerenciar templates'),
    menuItem('help', 'help', 'Atalhos e dicas'),
    '<div class="menu-sep"></div>',
    menuItem('quit', 'x', 'Sair'),
  ].join('');
  applyIcons(menu);
  menu.hidden = false;
}

function handleMenuAction(action) {
  toggleMoreMenu(false);
  switch (action) {
    case 'execute-all': execute('tudo'); break;
    case 'execute-here': execute('daqui'); break;
    case 'test-step': execute('teste'); break;
    case 'save-as': saveAsProject(); break;
    case 'generate-script': generateScript(); break;
    case 'open-templates': openTemplateManager(); break;
    case 'help': showHelp(); break;
    case 'quit': quitApp(); break;
    default: break;
  }
}

function handleAction(action, alvo) {
  switch (action) {
    case 'toggle-menu': toggleMoreMenu(); break;
    case 'new-project': newProject(); break;
    case 'open-project': openProject(); break;
    case 'save-project': saveProject(); break;
    case 'generate-script': generateScript(); break;
    case 'add-step': openAddStepModal(); break;
    case 'record': toggleRecord(); break;
    case 'execute': execute('tudo'); break;
    case 'undo': undo(); break;
    case 'show-problems': showProblems(); break;
    case 'help': showHelp(); break;
    case 'open-templates': openTemplateManager(); break;
    case 'clear-log': clearLog(); break;
    case 'open-logs-folder': openFolder('logs'); break;
    case 'open-folder': openFolder(alvo?.dataset?.key || 'base'); break;
    case 'repeat-up': setRepetitions((state.data?.projeto?.repeticoes ?? 1) + 1); break;
    case 'repeat-down': setRepetitions((state.data?.projeto?.repeticoes ?? 1) - 1); break;
    case 'pause-execution': pauseExecution(); break;
    case 'stop-execution': stopExecution(); break;
    default: break;
  }
}

/* ------------------------------------------------------------------ */
/* Navegação                                                           */
/* ------------------------------------------------------------------ */
function switchTab(tab) {
  flushConfig();
  state.tab = tab;
  $$('.nav-item').forEach((item) => item.classList.toggle('is-active', item.dataset.tab === tab));
  $$('.tab').forEach((section) => section.classList.toggle('is-active', section.id === `tab-${tab}`));
  if (tab === 'config') {
    if (!state.configRendered) renderConfig();
    else syncConfig();
  } else if (tab === 'log') {
    renderLogs(true);
  } else if (tab === 'fluxo' && state.data) {
    renderPalette(state.data);
    updateSelection();
    updateCurrentStep(state.data);
  }
}

/* ------------------------------------------------------------------ */
/* Eventos                                                             */
/* ------------------------------------------------------------------ */
function bindStatic() {
  applyIcons();

  document.addEventListener('click', (event) => {
    const alvo = event.target;

    const tab = alvo.closest('[data-tab]');
    if (tab) {
      switchTab(tab.dataset.tab);
      return;
    }

    const menuAction = alvo.closest('[data-menu-action]');
    if (menuAction) {
      event.preventDefault();
      handleMenuAction(menuAction.dataset.menuAction);
      return;
    }

    const action = alvo.closest('[data-action]');
    if (action) {
      event.preventDefault();
      handleAction(action.dataset.action, action);
      return;
    }

    if (!alvo.closest('#more-menu') && !alvo.closest('#more-btn')) toggleMoreMenu(false);
  });

  const steps = $('#steps-list');
  steps?.addEventListener('click', (event) => {
    const row = event.target.closest('.step-row');
    if (!row) return;
    const index = Number(row.dataset.index);
    const botao = event.target.closest('[data-step-action]');
    if (botao) {
      event.stopPropagation();
      selectStep(index);
      if (botao.dataset.stepAction === 'edit') editStep(index);
      else if (botao.dataset.stepAction === 'duplicate') duplicateStep(index);
      else if (botao.dataset.stepAction === 'delete') deleteStep(index);
      else if (botao.dataset.stepAction === 'toggle') toggleStep(index);
      return;
    }
    selectStep(index);
  });
  steps?.addEventListener('dblclick', (event) => {
    const row = event.target.closest('.step-row');
    if (!row || event.target.closest('[data-step-action]')) return;
    editStep(Number(row.dataset.index));
  });

  steps?.addEventListener('dragstart', (event) => {
    const row = event.target.closest('.step-row');
    if (!row) return;
    state.dragging = Number(row.dataset.index);
    row.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(state.dragging));
  });
  steps?.addEventListener('dragover', (event) => {
    const row = event.target.closest('.step-row');
    if (!row || state.dragging == null) return;
    event.preventDefault();
    $$('.step-row.is-drop-target', steps).forEach((el) => el.classList.remove('is-drop-target'));
    row.classList.add('is-drop-target');
  });
  steps?.addEventListener('dragleave', (event) => {
    const row = event.target.closest('.step-row');
    if (row) row.classList.remove('is-drop-target');
  });
  steps?.addEventListener('drop', (event) => {
    const row = event.target.closest('.step-row');
    if (!row || state.dragging == null) return;
    event.preventDefault();
    const destino = Number(row.dataset.index);
    const origem = state.dragging;
    state.dragging = null;
    $$('.step-row', steps).forEach((el) => el.classList.remove('is-drop-target', 'is-dragging'));
    moveStep(origem, destino);
  });
  steps?.addEventListener('dragend', () => {
    state.dragging = null;
    $$('.step-row', steps).forEach((el) => el.classList.remove('is-drop-target', 'is-dragging'));
  });

  $('#palette-list')?.addEventListener('click', (event) => {
    const botao = event.target.closest('[data-add-type]');
    if (botao) addStep(botao.dataset.addType);
  });

  const nome = $('#project-name');
  nome?.addEventListener('change', () => renameProject(nome.value));
  nome?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      nome.blur();
    }
  });

  const repetir = $('#repeat-input');
  repetir?.addEventListener('change', () => setRepetitions(repetir.value));
  repetir?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      repetir.blur();
    }
  });

  $('#simulate-switch')?.addEventListener('change', (event) => setSimulate(event.target.checked));

  $('#log-filter')?.addEventListener('input', (event) => {
    state.logFilter = event.target.value || '';
    renderLogs(true);
  });

  $('#config-scroll')?.addEventListener('input', handleConfigInput);
  $('#config-scroll')?.addEventListener('change', (event) => {
    if (event.target.matches('select[data-cfg]')) handleConfigInput(event);
  });
  $('#config-scroll')?.addEventListener('focusout', (event) => {
    if (event.target.matches('[data-cfg]')) flushConfig();
  });

  document.addEventListener('keydown', handleKeydown);
}

function isTypingTarget(target) {
  return target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable);
}

function trapFocus(event) {
  const top = state.modalStack[state.modalStack.length - 1];
  if (!top) return;
  const focaveis = [...top.modal.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((el) => el.getClientRects().length > 0);
  if (!focaveis.length) return;
  const primeiro = focaveis[0];
  const ultimo = focaveis[focaveis.length - 1];
  const ativo = document.activeElement;
  const fora = !top.modal.contains(ativo);
  if (event.shiftKey && (ativo === primeiro || fora)) {
    event.preventDefault();
    ultimo.focus();
  } else if (!event.shiftKey && (ativo === ultimo || fora)) {
    event.preventDefault();
    primeiro.focus();
  }
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    if (state.modalStack.length) {
      event.preventDefault();
      closeTopModal();
      return;
    }
    if (!$('#more-menu')?.hidden) {
      event.preventDefault();
      toggleMoreMenu(false);
      return;
    }
    // F8/ESC durante execução são tratados pelo listener global do processo
    // Tk. Não os repetimos aqui para evitar alternar a pausa duas vezes.
  }

  if (state.modalStack.length) {
    if (event.key === 'Tab') trapFocus(event);
    return;
  }
  if (isTypingTarget(event.target)) return;

  const ctrl = event.ctrlKey || event.metaKey;
  if (event.key === 'F9') {
    event.preventDefault();
    toggleRecord();
  } else if (event.key === 'F10') {
    if (state.data?.gravando) {
      event.preventDefault();
      callBackend('pause_recording').then((resposta) => toast(resposta.pausado ? 'Gravação pausada' : 'Gravação retomada', '', 'info', 2200));
    }
  } else if (event.key === 'Delete') {
    if (state.selected != null) {
      event.preventDefault();
      deleteStep(state.selected);
    }
  } else if (event.key === ' ') {
    if (state.selected != null) {
      event.preventDefault();
      toggleStep(state.selected);
    }
  } else if (event.key === 'Enter') {
    if (state.selected != null) {
      event.preventDefault();
      editStep(state.selected);
    }
  } else if (ctrl && !event.shiftKey && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveProject();
  } else if (ctrl && event.shiftKey && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveAsProject();
  } else if (ctrl && !event.shiftKey && event.key.toLowerCase() === 'n') {
    event.preventDefault();
    newProject();
  } else if (ctrl && !event.shiftKey && event.key.toLowerCase() === 'o') {
    event.preventDefault();
    openProject();
  } else if (ctrl && !event.shiftKey && event.key.toLowerCase() === 'r') {
    event.preventDefault();
    execute('tudo');
  } else if (ctrl && !event.shiftKey && event.key.toLowerCase() === 'g') {
    event.preventDefault();
    generateScript();
  } else if (ctrl && !event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    undo();
  } else if (ctrl && (event.key === '=' || event.key === '+')) {
    event.preventDefault();
    queueConfig({ escala_web: Math.min(22, Math.round(numberValue(state.data?.config?.escala_web, 15)) + 1) }, 0);
  } else if (ctrl && event.key === '-') {
    event.preventDefault();
    queueConfig({ escala_web: Math.max(15, Math.round(numberValue(state.data?.config?.escala_web, 15)) - 1) }, 0);
  }
}

/* ------------------------------------------------------------------ */
/* Inicialização                                                       */
/* ------------------------------------------------------------------ */
function showFatal(message) {
  if (state.fatalShown) return;
  state.fatalShown = true;
  hideBoot();
  state.fatalModal = openModal({
    title: 'Não foi possível conectar',
    kicker: 'El Gravador 18 Pro Max',
    subtitle: 'O núcleo de automação não respondeu.',
    size: 'sm',
    body: `<p class="form-note" style="font-family:var(--mono);white-space:pre-wrap;font-size: var(--fs-caption);line-height:1.6">${esc(message || 'Erro desconhecido.')}</p><p class="form-note">Feche e abra o aplicativo. Se o problema continuar, execute com <code>python main.py</code> em um terminal para ver os detalhes.</p>`,
    actions: [{ label: 'Fechar', kind: 'primary' }],
    onClose: () => {
      state.fatalShown = false;
      state.fatalModal = null;
    },
  });
}

function limparFatal() {
  if (state.fatalModal) {
    const modal = state.fatalModal;
    state.fatalModal = null;
    state.fatalShown = false;
    modal.close();
  }
}

async function refreshState(initial = false) {
  try {
    const dados = await getState();
    applyState(dados, initial);
    if (initial && document.body.dataset.ready !== '1') {
      throw new Error('O aplicativo respondeu, mas não enviou os dados do projeto.');
    }
    if (initial) limparFatal();
  } catch (error) {
    if (initial) showFatal(error.message);
    console.error(error);
  }
}

async function poll() {
  if (state.pollBusy || !bridge() || state.modalStack.length && state.modalStack.some((m) => m.modal?.querySelector('[data-block-poll]'))) return;
  state.pollBusy = true;
  try {
    const dados = await getState();
    applyState(dados);
    limparFatal();
  } catch (error) {
    console.error(error);
  } finally {
    state.pollBusy = false;
  }
}

async function boot() {
  if (state.booted) return;
  state.booted = true;
  try {
    await refreshState(true);
    state.pollTimer = setInterval(poll, 700);
  } catch (error) {
    showFatal(error.message);
  }
}

bindStatic();
if (bridge()) boot();
window.addEventListener('pywebviewready', () => boot());
setTimeout(() => {
  if (!state.booted && !bridge()) {
    hideBoot();
    showFatal('A interface foi carregada, mas a ponte com o Python não apareceu. Verifique se o PyWebView está instalado e se o aplicativo foi iniciado por main.py.');
  }
}, 10000);
