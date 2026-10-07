const PDFDocument = require('pdfkit');

const money = value => `CHF ${Number(value || 0).toLocaleString('de-CH', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
function streamPdf(res, filename, build) {
  res.type('application/pdf'); res.attachment(filename);
  const doc = new PDFDocument({size: 'A4', margin: 54, info: {Creator: 'AST Manager'}});
  doc.pipe(res); build(doc); doc.end();
}
function heading(doc, title, subtitle='') {
  doc.font('Helvetica-Bold').fontSize(20).fillColor('#0d3440').text(title);
  if (subtitle) doc.moveDown(.3).font('Helvetica').fontSize(10).fillColor('#526a76').text(subtitle);
  doc.moveDown(1.2).fillColor('#111111');
}
function table(doc, headers, rows) {
  const width=(doc.page.width-doc.page.margins.left-doc.page.margins.right)/headers.length;
  const row=(values,bold=false,shade=false)=>{ const y=doc.y; if(shade) doc.rect(doc.page.margins.left,y-3,width*headers.length,19).fill('#edf3f5').fillColor('#111'); values.forEach((v,i)=>doc.font(bold?'Helvetica-Bold':'Helvetica').fontSize(8).text(String(v??''),doc.page.margins.left+i*width,y,{width:width-4,height:16})); doc.y=y+19; };
  row(headers,true,true); rows.forEach((values,i)=>row(values,false,i%2===1));
}
function debtorsPdf(res, rows) {
  streamPdf(res,'Debitoren.pdf',doc=>{ heading(doc,'Debitoren','Rechnungen und Zahlungseingänge'); table(doc,['Rechnung','Kunde','Fällig','Betrag','Bezahlt','Offen','Status'],rows.map(r=>[r.invoice_number,r.customer,r.due_date,money(r.amount),money(r.paid_amount),money(r.amount-r.paid_amount),(r.amount-r.paid_amount)<=0?'Bezahlt':'Offen'])); });
}
function timesheetPdf(res, employee, year, rows) {
  streamPdf(res,`Stundennachweis_${year}_${employee.last_name}_${employee.first_name}.pdf`,doc=>{ heading(doc,`Stundennachweis · ${employee.first_name} ${employee.last_name}`,`Kalenderjahr ${year} · Personal-Nr. ${employee.personnel_number}`); table(doc,['Datum','Arbeitszeit','Grund','Bemerkung'],rows.map(r=>[r.work_date,`${Number(r.hours).toFixed(2)} h`,r.reason,r.notes])); });
}
function reminderPdf(res, row, settings) {
  const levels={1:'Zahlungserinnerung',2:'Mahnung 1',3:'Mahnung 2',4:'Betreibung'};
  streamPdf(res,`${levels[row.level]}-${row.invoice_number||'manuell'}.pdf`,doc=>{ doc.font('Helvetica-Bold').fontSize(18).text(settings.company||'AST Elektro Tüscher AG'); doc.moveDown(3); doc.font('Helvetica').fontSize(11).text(row.customer); doc.moveDown(3); heading(doc,`${levels[row.level]} · Rechnung ${row.invoice_number||''}`,row.reminder_date); doc.font('Helvetica').fontSize(11).text(row.reminder_text||'Bitte begleichen Sie den offenen Betrag.'); doc.moveDown(1.5).font('Helvetica-Bold').text(`Offener Betrag: ${money(row.amount)}`); });
}
function certificatePdf(res, row, employee, settings) {
  streamPdf(res,`${row.certificate_type}_${employee.last_name}_${employee.first_name}.pdf`,doc=>{ doc.font('Helvetica-Bold').fontSize(18).text(settings.company||'AST Elektro Tüscher AG'); doc.moveDown(3); doc.font('Helvetica').fontSize(11).text(`${employee.first_name} ${employee.last_name}\n${employee.address||''}\n${employee.postcode||''} ${employee.city||''}`); doc.moveDown(2); heading(doc,`${row.certificate_type} ${employee.first_name} ${employee.last_name} per ${row.reference_date}`); doc.font('Helvetica').fontSize(11).text(row.generated_text||row.notes||'',{align:'justify',lineGap:4}); });
}
module.exports={debtorsPdf,timesheetPdf,reminderPdf,certificatePdf};
