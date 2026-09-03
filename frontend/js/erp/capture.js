import { get, post, put } from '../api.js';
import { options } from '../data.js';
import { esc, money, number } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260826-3';
import { emit } from '../events.js?v=20260826-3';

export async function render(container) {
  return renderCapture(container);
}

export async function renderCapture(container) {
  const [status, suppliers, materials] = await Promise.all([
    get(`/erp/${state.companyId}/capture/status`),
    options('suppliers', 'name'),
    options('materials', (row) => `${row.code} · ${row.name}`),
  ]);
  let preview = null;
  const paint = () => {
    container.innerHTML = pageHeader('Ler fatura', 'Fotografe ou carregue o PDF. O Gemini lê; vocês ligam os artigos uma vez e o programa aprende.', '<a class="btn" href="#/erp-docs">Ver documentos</a>') + `
      <div class="integration-grid">
        <section class="card">
          <div class="card-header"><h2>Gemini</h2><span>${status.gemini_configured ? 'Chave gravada' : 'Sem chave'}</span></div>
          ${status.gemini_configured ? '<p class="muted">Tire foto à fatura do fornecedor ou escolha um PDF. A leitura corre no servidor; a chave não sai para o ecrã.</p>' : `
            <form id="gemini-key-form" class="form-grid">
              <div class="field full"><label>Chave API Gemini<input name="api_key" type="password" autocomplete="off" placeholder="AIza…"></label><small class="muted">Obtém-se em Google AI Studio. Fica cifrada no servidor desta empresa.</small></div>
              <div class="form-footer"><button class="btn primary" type="submit">Guardar chave</button></div>
            </form>`}
          <div class="capture-drop">
            <input id="erp-file" type="file" accept="image/*,application/pdf" capture="environment">
            <label class="btn primary" for="erp-file">Fotografar ou escolher ficheiro</label>
            <p class="muted">JPEG, PNG ou PDF. A foto é reduzida antes de enviar.</p>
          </div>
        </section>
        <section class="card" data-preview>
          ${previewMarkup(preview, suppliers, materials)}
        </section>
      </div>`;
    container.querySelector('#gemini-key-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await put(`/erp/${state.companyId}/capture/key`, { api_key: event.currentTarget.api_key.value });
        toast('Chave Gemini guardada.');
        await renderCapture(container);
      } catch (error) { toast(error.message, 'error'); }
    });
    container.querySelector('#erp-file')?.addEventListener('change', async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        toast('A ler o documento…');
        const packed = await packFile(file);
        preview = await post(`/erp/${state.companyId}/capture/read`, packed);
        paint();
      } catch (error) { toast(error.message, 'error'); }
    });
    container.querySelector('[data-confirm-capture]')?.addEventListener('click', async () => {
      try {
        const payload = readPreview(container, preview);
        const saved = await post(`/erp/${state.companyId}/capture/confirm`, payload);
        const extra = (saved.follow_on || []).map((item) => item.doc_no).filter(Boolean);
        emit('ops-changed', { source: 'stock-receipt', docNo: saved.doc_no });
        toast(`${saved.doc_no} criado${extra.length ? ` e ${extra.join(', ')}` : ''} preparado para o Primavera. Os artigos ligados ficam na memória.`);
        location.hash = '#/erp-docs';
      } catch (error) { toast(error.message, 'error'); }
    });
  };
  paint();
}

function previewMarkup(preview, suppliers, materials) {
  if (!preview) return `<div class="empty"><strong>À espera do documento</strong>A primeira vez tem de ligar cada linha ao artigo TextileFlow. Nas seguintes o programa reconhece sozinho.</div>`;
  const supplierOptions = [`<option value="">Fornecedor…</option>`, ...suppliers.map((item) => `<option value="${item.value}" ${String(item.value) === String(preview.supplier_id || '') ? 'selected' : ''}>${esc(item.label)}</option>`)].join('');
  const materialOptions = (selected) => [`<option value="">Artigo TextileFlow…</option>`, ...materials.map((item) => `<option value="${item.value}" ${String(item.value) === String(selected || '') ? 'selected' : ''}>${esc(item.label)}</option>`)].join('');
  return `<div class="card-header"><h2>${esc(preview.number || 'Documento lido')}</h2><span>${preview.unmatched ? preview.unmatched + ' linhas por ligar' : preview.learned + ' linhas reconhecidas'}</span></div>
    <div class="form-grid">
      <div class="field"><label>Fornecedor<select data-cap-supplier>${supplierOptions}</select></label></div>
      <div class="field"><label>Data<input data-cap-date type="date" value="${esc(String(preview.date || '').slice(0, 10))}"></label></div>
      <div class="field"><label>Total<input value="${esc(preview.total)}" readonly></label></div>
    </div>
    <p class="muted">${esc(preview.supplier_name || '')} ${esc(preview.supplier_tax_id || '')}</p>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>No documento</th><th>Qtd</th><th>Preço</th><th>Artigo TextileFlow</th></tr></thead><tbody>
      ${(preview.lines || []).map((line, index) => `<tr>
        <td><b>${esc(line.source_code || '—')}</b><div class="muted">${esc(line.source_name || '')}</div>${line.learned ? '<span class="badge green">Aprendido</span>' : ''}</td>
        <td>${number(line.quantity)}</td>
        <td>${money(line.unit_cost)}</td>
        <td><select data-cap-material="${index}">${materialOptions(line.material_id)}</select></td>
      </tr>`).join('')}
    </tbody></table></div>
    <div class="form-footer"><button class="btn primary" data-confirm-capture>Guardar e preparar Primavera</button></div>`;
}

function readPreview(container, preview) {
  const lines = (preview.lines || []).map((line, index) => ({
    ...line,
    material_id: Number(container.querySelector(`[data-cap-material="${index}"]`)?.value || '') || null,
  }));
  return {
    ...preview,
    supplier_id: Number(container.querySelector('[data-cap-supplier]')?.value || '') || null,
    date: container.querySelector('[data-cap-date]')?.value || preview.date,
    lines,
    prepare: true,
  };
}

function packFile(file) {
  return new Promise((resolve, reject) => {
    if (file.type.startsWith('image/')) {
      const image = new Image();
      const url = URL.createObjectURL(file);
      image.onload = () => {
        const canvas = document.createElement('canvas');
        const scale = Math.min(1, 1600 / Math.max(image.width, image.height));
        canvas.width = Math.max(1, image.width * scale);
        canvas.height = Math.max(1, image.height * scale);
        canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
        const data = canvas.toDataURL('image/jpeg', 0.72).split(',')[1];
        URL.revokeObjectURL(url);
        resolve({ mime: 'image/jpeg', data });
      };
      image.onerror = () => reject(new Error('Não foi possível ler a fotografia.'));
      image.src = url;
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve({ mime: file.type || 'application/pdf', data: String(reader.result).split(',')[1] });
    reader.onerror = () => reject(new Error('Não foi possível ler o ficheiro.'));
    reader.readAsDataURL(file);
  });
}

export async function renderAliases(container) {
  const rows = await get(`/erp/${state.companyId}/aliases`);
  container.innerHTML = pageHeader('Artigos aprendidos', 'Cada ligação que confirmam numa fatura fica aqui. Na próxima leitura o ERP reconhece sozinho.', '<a class="btn primary" href="#/erp-capture">Ler nova fatura</a>') + `
    <div class="table-wrap"><table class="data-table"><thead><tr><th>No documento do fornecedor</th><th>Fornecedor</th><th>Artigo TextileFlow</th><th>Vezes</th></tr></thead>
    <tbody>${rows.map((row) => `<tr><td><b>${esc(row.source_code || '—')}</b><div class="muted">${esc(row.source_name || '')}</div></td><td>${esc(row.supplier)}</td><td>${esc(row.material)}</td><td>${row.hits}</td></tr>`).join('') || '<tr><td colspan="4"><div class="empty"><strong>Ainda não aprendeu artigos</strong>Leia uma fatura e ligue as linhas. Essa memória fica para as seguintes.</div></td></tr>'}</tbody></table></div>`;
}
