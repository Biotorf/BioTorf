// Экспорт таблиц поставок/выгрузок «как в Excel» и печать актов.
// Без внешних npm-зависимостей: используем форматы, которые Excel и LibreOffice
// открывают нативно — CSV (UTF-8 с BOM) и XML Spreadsheet 2003 (.xls).

export function downloadBlob(content, filename, mime) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mime });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

/**
 * rows: массив массивов ячеек (string|number|null).
 */
export function toCsv(rows, sep = ';') {
  return '\uFEFF' + rows.map((r) =>
    r.map((c) => {
      const v = c == null ? '' : String(v_safe(c));
      return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    }).join(sep)
  ).join('\r\n');
}

function v_safe(c) {
  if (c == null) return '';
  if (typeof c === 'number') return c;
  return String(c);
}

export function toXmlSpreadsheet(rows, sheetName = 'Лист1') {
  const cell = (v) => {
    if (typeof v === 'number' && isFinite(v)) {
      return `<Cell><Data ss:Type="Number">${v}</Data></Cell>`;
    }
    return `<Cell><Data ss:Type="String">${esc(v == null ? '' : String(v))}</Data></Cell>`;
  };
  const table = rows.map((r) => `<Row>${r.map(cell).join('')}</Row>`).join('');
  return `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="${esc(sheetName)}"><Table>${table}</Table></Worksheet>
</Workbook>`;
}

// ── Печать документа/акта в отдельном окне (→ Ctrl+P или «Сохранить как PDF») ──
export function printHtml(title, bodyHtml) {
  const win = window.open('', '_blank', 'width=900,height=700');
  if (!win) { alert('Браузер заблокировал окно печати — разрешите всплывающие окна'); return false; }
  win.document.write(`<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>
  @page { size: A4; margin: 16mm; }
  body { font: 13px/1.45 Arial, sans-serif; color:#1c2b26; }
  h1 { font-size: 17px; margin: 0 0 2px; }
  h2 { font-size: 14px; margin: 18px 0 6px; }
  .org { color:#5c7368; font-size:12px; margin-bottom:14px; }
  .grid { display:flex; gap:28px; font-size:12px; margin:8px 0 14px; flex-wrap:wrap; }
  .grid div b { display:block; font-size:11px; color:#6c8178; text-transform:uppercase; }
  table { width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }
  th, td { border:1px solid #9bb3a8; padding:6px 8px; text-align:left; }
  th { background:#e4f0e9; }
  td.num, th.num { text-align:right; }
  tfoot td { font-weight:bold; }
  .sign { display:flex; gap:60px; margin-top:44px; font-size:12px; }
  .sign > div { flex:1; }
  .line { border-bottom:1px solid #333; height:26px; margin-bottom:3px; }
  .small { color:#6c8178; font-size:11px; }
</style></head><body>${bodyHtml}
<script>window.onload = () => { window.print(); };</script></body></html>`);
  win.document.close();
  return true;
}
