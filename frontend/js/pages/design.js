import { renderBoard } from '../design/board.js?v=20260826-3';
import { renderToday } from '../design/control.js?v=20260826-3';
import { renderOrganization } from '../design/organization.js?v=20260826-3';
import { renderReport } from '../design/report.js?v=20260826-3';

export async function render(container, view = 'today') {
  if (view === 'requests') return renderBoard(container, 'portfolio');
  if (view === 'samples') return renderBoard(container, 'samples');
  if (view === 'organization') return renderOrganization(container);
  if (view === 'report') return renderReport(container);
  return renderToday(container);
}
