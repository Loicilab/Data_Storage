import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {Workbook} from '@oai/artifact-tool';

const root = 'C:/Users/loici/Desktop/Data_Store/Data_Storage';
const csvPath = `${root}/accounts/email-pairs.csv`;
const original = await fs.readFile(csvPath, 'utf8');
const workbook = await Workbook.fromCSV(original.replace(/^\uFEFF/, ''), {sheetName:'Pairs'});
const sheet = workbook.worksheets.getItem('Pairs');
const prior = sheet.getRange('A1:L11').values;
sheet.getRange('A1:F11').format.autofitColumns();
const before = await workbook.render({sheetName:'Pairs',range:'A1:F4',scale:1,format:'png'});
await fs.writeFile(`${root}/research/signup-evidence/email-pairs-before-provider-change.png`, new Uint8Array(await before.arrayBuffer()));

const py = "import json; from replace_outlook_pairs import update_pairs; print(json.dumps(update_pairs()))";
const records = JSON.parse(execFileSync('C:/Users/loici/miniforge3/python.exe',['-c',py],{cwd:`${root}/research`,encoding:'utf8'}));
const headers = Object.keys(records[0]);
const matrix = [headers,...records.map(r=>headers.map(h=>r[h]))];
if (records.length!==10 || headers.length!==12) throw new Error('Unexpected pair table dimensions');
const passwords = records.flatMap(r=>[r.password_a,r.password_b]);
if (new Set(passwords).size!==20 || passwords.some(p=>typeof p!=='string'||p.length<32)) throw new Error('Password coverage or uniqueness check failed');
for (let i=0;i<records.length;i++) {
  for (const field of ['pair_id','generated_name','email_b','password_a','password_b','provider_b','status_b','mutual_recovery','mega_status']) {
    if (records[i][field]!==prior[i+1][prior[0].indexOf(field)]) throw new Error(`Unrequested change in ${field}`);
  }
  if(records[i].provider_a!=='Mailfence'||records[i].status_a!=='planned'||records[i].email_a.split('@')[0]===records[i].email_b.split('@')[0]) throw new Error('Replacement provider or distinct username check failed');
}

sheet.getRange('A1:L11').values = matrix;
sheet.getRange('A1:L11').format.autofitColumns();
workbook.recalculate();
const actual = sheet.getRange('A1:L11').values;
if (JSON.stringify(actual)!==JSON.stringify(matrix)) throw new Error('CSV cell values did not match the prepared pairs');
const after = await workbook.render({sheetName:'Pairs',range:'B1:E4',scale:1,format:'png'});
await fs.writeFile(`${root}/research/signup-evidence/email-pairs-after-provider-change.png`, new Uint8Array(await after.arrayBuffer()));
const quote = v => {const s=String(v??''); return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;};
await fs.writeFile(csvPath,'\uFEFF'+actual.map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n','utf8');
console.log(JSON.stringify({pairs:records.length,replacement_provider:'Mailfence',all_usernames_different_within_pairs:true,proton_and_passwords_preserved:true,output:'accounts/email-pairs.csv'}));
