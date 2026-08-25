import { get, post } from './api.js?v=20260822-16';
import { setSession } from './state.js';

const form = document.getElementById('login-form');
const message = document.getElementById('login-message');
const loginScreen = document.getElementById('login-screen');
const shell = document.getElementById('app-shell');

function say(text) {
  if (message) message.textContent = text || '';
}

async function launchApp() {
  say('A abrir o sistema…');
  try {
    const app = await import('./app.js?v=20260825-52');
    await app.bootApp();
    say('');
  } catch (error) {
    loginScreen?.classList.remove('hidden');
    shell?.classList.add('hidden');
    say(`Não foi possível iniciar a área de trabalho: ${error.message}`);
  }
}

form?.addEventListener('submit', async event => {
  event.preventDefault();
  say('A validar…');
  try {
    const data = await post('/auth/login', {
      username: document.getElementById('login-username').value.trim(),
      password: document.getElementById('login-password').value,
    }, { skipAuth: true, timeoutMs: 45000 });
    localStorage.setItem('tf_token', data.token);
    setSession(data);
    await launchApp();
  } catch (error) {
    say(error.message);
  }
});

(async function bootstrapLogin() {
  try {
    await get('/health', { skipAuth: true, timeoutMs: 8000 });
    document.getElementById('api-status')?.classList.remove('offline');
  } catch {
    const status = document.getElementById('api-status');
    if (status) status.innerHTML = '<i></i> API indisponível';
  }
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
