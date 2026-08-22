export const state = {
  user: null,
  companies: [],
  companyId: Number(localStorage.getItem('tf_company') || 0),
  cache: new Map(),
};

export function setSession(data) {
  state.user = data.user || data;
  if (data.must_change_password != null && state.user) state.user.must_change_password = data.must_change_password;
  state.companies = data.companies || [];
  if (!state.companyId || !state.companies.some(company => company.id === state.companyId)) state.companyId = state.companies[0]?.id || 0;
  localStorage.setItem('tf_company', state.companyId);
}

export function setCompany(id) {
  state.companyId = Number(id);
  state.cache.clear();
  localStorage.setItem('tf_company', state.companyId);
}

export function clearSession() {
  localStorage.removeItem('tf_token');
  localStorage.removeItem('tf_company');
  state.user = null; state.companies = []; state.companyId = 0; state.cache.clear();
}
