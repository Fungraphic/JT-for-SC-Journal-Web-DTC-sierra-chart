const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const m = html.match(/<script[^>]*>([\s\S]*?)<\/script>/g);
if (!m) { console.log('No script tags found'); process.exit(0); }
let errors = 0;
m.forEach((block, i) => {
  const code = block.replace(/<\/?script[^>]*>/g, '');
  try { new Function(code); } catch(e) { errors++; console.log('Script block ' + i + ': ' + e.message); }
});
if (errors === 0) console.log('All script blocks OK');
else console.log(errors + ' error(s)');