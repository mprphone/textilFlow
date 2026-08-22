import { crudList } from './api.js';
import { state } from './state.js';

export async function options(resource, label, value = 'id', query = '') {
  const rows = await crudList(resource, state.companyId, query);
  return rows.map(row => ({ value: row[value], label: typeof label === 'function' ? label(row) : row[label] }));
}

export async function references(resources) {
  const entries = await Promise.all(resources.map(async resource => [resource, await crudList(resource, state.companyId)]));
  return Object.fromEntries(entries);
}
