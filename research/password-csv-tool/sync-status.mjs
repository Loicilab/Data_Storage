import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {Workbook} from '@oai/artifact-tool';

const root = 'C:/Users/loici/Desktop/Data_Store/Data_Storage';
const csvPath = `${root}/accounts/email-pairs.csv`;
const workbook = await Workbook.fromCSV((await fs.readFile(csvPath,'utf8')).replace(/^\uFEFF/,''),{sheetName:'Pairs'});
const sheet = workbook.worksheets.getItem('Pairs');
const prior = sheet.getRange('A1:L11').values;
const py = "import json; from record_lena_mailbox_blocker import record; print(json.dumps(record()))";
const rows = JSON.parse(execFileSync('C:/Users/loici/miniforge3/python.exe',['-c',py],{cwd:`${root}/research`,encoding:'utf8'}));
const headers = Object.keys(rows[0]);
if(rows.length!==10 || headers.length!==12) throw new Error('Unexpected pair table dimensions');
for(let i=0;i<rows.length;i++) {
  for(const field of headers.filter(h=>!['status_b','mega_status'].includes(h))) {
    if(rows[i][field]!==prior[i+1][prior[0].indexOf(field)]) throw new Error(`Unexpected change in ${field}`);
  }
}
const matrix = [headers,...rows.map(r=>headers.map(h=>r[h]))];
sheet.getRange('A1:L11').values = matrix;
workbook.recalculate();
if(JSON.stringify(sheet.getRange('A1:L11').values)!==JSON.stringify(matrix)) throw new Error('Cell verification failed');
sheet.getRange('J1:L11').format.autofitColumns();
const render = await workbook.render({sheetName:'Pairs',range:'J1:L4',scale:1,format:'png'});
await fs.writeFile(`${root}/research/signup-evidence/email-pairs-lena-status.png`,new Uint8Array(await render.arrayBuffer()));
const quote = v => {const s=String(v??'');return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};
await fs.writeFile(csvPath,'\uFEFF'+matrix.map(r=>r.map(quote).join(',')).join('\r\n')+'\r\n','utf8');
console.log(JSON.stringify({pairs:rows.length,addresses_and_passwords_preserved:true,lena_proton:'suspended_observed',lena_mega:'not_created_mailbox_suspended',other_proton:'created_user_reported'}));
