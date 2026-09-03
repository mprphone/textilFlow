import { get, post } from './api.js?v=20260826-3';
import { setSession } from './state.js';

const form = document.getElementById('login-form');
const message = document.getElementById('login-message');
const loginScreen = document.getElementById('login-screen');
const shell = document.getElementById('app-shell');
const submit = form?.querySelector('button[type="submit"]');
const APP_MODULE = './app.js?v=20260903-3';
let signingIn = false;

function resetLoginLayers() {
  const modal = document.getElementById('modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  modal.setAttribute('inert', '');
  modal.hidden = true;
  modal.style.setProperty('display', 'none');
  document.body.classList.remove('modal-open');
}

function setBusy(busy) {
  signingIn = busy;
  form?.setAttribute('aria-busy', String(busy));
  if (!submit) return;
  submit.disabled = busy;
  submit.textContent = busy ? 'A entrar…' : 'Entrar';
}

function say(text) {
  if (message) message.textContent = text || '';
}

async function launchApp() {
  say('A abrir o sistema…');
  try {
    const app = await import(APP_MODULE);
    await app.bootApp();
    say('');
  } catch (error) {
    localStorage.removeItem('tf_token');
    loginScreen?.classList.remove('hidden');
    shell?.classList.add('hidden');
    resetLoginLayers();
    say(`Não foi possível iniciar a área de trabalho: ${error.message}`);
    throw error;
  }
}

form?.addEventListener('submit', async event => {
  event.preventDefault();
  if (signingIn) return;
  setBusy(true);
  say('A validar…');
  const slowMessage = setTimeout(() => say('O servidor está a preparar a sessão…'), 4000);
  try {
    const data = await post('/auth/login', {
      username: document.getElementById('login-username').value.trim(),
      password: document.getElementById('login-password').value,
    }, { skipAuth: true, timeoutMs: 20000 });
    localStorage.setItem('tf_token', data.token);
    setSession(data);
    await launchApp();
  } catch (error) {
    say(error.message);
  } finally {
    clearTimeout(slowMessage);
    setBusy(false);
  }
});

(async function bootstrapLogin() {
  get('/health', { skipAuth: true, timeoutMs: 5000 }).then(() => {
    document.getElementById('api-status')?.classList.remove('offline');
  }).catch(() => {
    const status = document.getElementById('api-status');
    if (status) status.innerHTML = '<i></i> API indisponível';
  });
  const token = localStorage.getItem('tf_token');
  if (!token) return;
  try {
    const me = await get('/auth/me');
    setSession(me);
    await launchApp();
  } catch {
    localStorage.removeItem('tf_token');
  }
})().catch(error => say(`Não foi possível iniciar: ${error.message}`));

// O ecrã de login nunca pode ficar bloqueado por uma modal restaurada pelo browser.
resetLoginLayers();
const loginLayerGuard = new MutationObserver(() => {
  if (!loginScreen?.classList.contains('hidden')) resetLoginLayers();
});
loginLayerGuard.observe(loginScreen, { attributes: true, attributeFilter: ['class'] });
