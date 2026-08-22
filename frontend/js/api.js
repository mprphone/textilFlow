const sameHost = `${location.protocol}//${location.host}`;
export const API_URL = location.port === '8000' ? sameHost : `${sameHost}/api`;

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

function errorMessage(data) {
  const detail = data?.detail ?? data;
  if (Array.isArray(detail)) {
    return detail.map(item => {
      const labels = {description:'Descrição',quantity:'Quantidade',unit:'Unidade',unit_cost:'Preço',selling_price:'Preço de venda',article_type_id:'Tipo de peça',customer_id:'Cliente',services:'Subcontratos',overheads:'Custos gerais'};
      const parts = (item.loc || []).filter(part => !['body', 'query', 'path'].includes(part));
      const field = parts.at(-1);
      const line = parts.find(part => typeof part === 'number');
      const path = `${labels[field] || labels[parts[0]] || field || 'Campo'}${line !== undefined ? ` (linha ${line + 1})` : ''}`;
      const messages = {string_too_short:'é obrigatório',greater_than:'tem de ser superior a zero',greater_than_equal:'não pode ser negativo',less_than_equal:'está acima do máximo permitido',missing:'é obrigatório'};
      return `${path}: ${messages[item.type] || item.msg || 'valor inválido'}`;
    }).join('\n');
  }
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.message || 'Os dados enviados não são válidos.';
  return 'Erro de comunicação';
}

export async function api(path, options = {}) {
  const { skipAuth = false, timeoutMs = 45000, ...rest } = options;
  const token = skipAuth ? null : localStorage.getItem('tf_token');
  const headers = { ...(rest.body ? { 'Content-Type': 'application/json' } : {}), ...(rest.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...rest, headers, signal: controller.signal });
  } catch (error) {
    if (error.name === 'AbortError') throw new ApiError('A API não respondeu a tempo. Confirme se o serviço na porta 8000 está a correr.', 0);
    throw new ApiError('Não foi possível contactar a API.', 0);
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 204) return null;
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) throw new ApiError(errorMessage(data), response.status, data);
  return data;
}

export const get = (path, options) => api(path, options);
export const post = (path, data, options) => api(path, { method: 'POST', body: JSON.stringify(data), ...options });
export const put = (path, data) => api(path, { method: 'PUT', body: JSON.stringify(data) });
export const patch = (path, data) => api(path, { method: 'PATCH', body: JSON.stringify(data) });
export const remove = path => api(path, { method: 'DELETE' });

export function crudList(resource, companyId, query = '') { return get(`/crud/${resource}?company_id=${companyId}${query ? `&${query}` : ''}`); }
export function crudCreate(resource, data) { return post(`/crud/${resource}`, data); }
export function crudUpdate(resource, id, data) { return put(`/crud/${resource}/${id}`, data); }
export function crudDelete(resource, id, companyId) { return remove(`/crud/${resource}/${id}?company_id=${companyId}`); }
