// Exercise the bank workflow's Normalize code against GoCardless-shaped
// fixtures, with the n8n helpers stubbed. Checks the money path above all.
const fs = require('fs');
const wf = JSON.parse(fs.readFileSync('C:/projects/jytte/deploy/n8n/workflows/bank.json', 'utf8'));
const code = wf.nodes.find((n) => n.name === 'Normalize accounts').parameters.jsCode;

const wrap = (arr) => arr.map((json) => ({ json }));

const nodes = {
  Config: wrap([{ requisition_id: 'req-1', lookback_days: 30 }]),
  'Split accounts': wrap([
    { account_id: 'acc-a', consent_status: 'LN' },
    { account_id: 'acc-b', consent_status: 'LN' },
  ]),
  'Fetch details': wrap([
    { account: { iban: 'DK5000400440116243', name: 'Lønkonto', currency: 'DKK', ownerName: 'Danske Bank' } },
    { account: { iban: 'DK9520000123456789', product: 'Opsparing', currency: 'DKK' } },
  ]),
  'Fetch balances': wrap([
    {
      balances: [
        { balanceAmount: { amount: '-120.55', currency: 'DKK' }, balanceType: 'closingBooked', referenceDate: '2026-10-13' },
        { balanceAmount: { amount: '12345.67', currency: 'DKK' }, balanceType: 'interimAvailable', referenceDate: '2026-10-14' },
      ],
    },
    { balances: [{ balanceAmount: { amount: '80000.10', currency: 'DKK' }, balanceType: 'closingBooked', referenceDate: '2026-10-11' }] },
  ]),
  'Fetch transactions': wrap([
    {
      transactions: {
        booked: [
          { transactionId: 't1', bookingDate: '2026-10-12', transactionAmount: { amount: '-249.50', currency: 'DKK' }, creditorName: 'NETTO', remittanceInformationUnstructured: 'Dankort' },
          { transactionId: 't2', bookingDate: '2026-10-01', transactionAmount: { amount: '35116.93', currency: 'DKK' }, debtorName: 'TRUSTWORKS APS' },
          { transactionId: 'old', bookingDate: '2025-01-01', transactionAmount: { amount: '-1.00', currency: 'DKK' } },
        ],
        pending: [{ transactionId: 't3', valueDate: '2026-10-14', transactionAmount: { amount: '-99.00', currency: 'DKK' }, creditorName: 'SPOTIFY' }],
      },
    },
    { transactions: { booked: [], pending: [] } },
  ]),
};

const $ = (name) => ({
  all: () => nodes[name],
  first: () => nodes[name][0],
});

const run = new Function('$', '$input', code);
const out = run($, { all: () => [], first: () => ({ json: {} }) });
const p = out[0].json;

let fails = 0;
const check = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fails++;
  console.log((ok ? 'PASS ' : 'FAIL ') + label + '  got=' + JSON.stringify(got) + (ok ? '' : ' want=' + JSON.stringify(want)));
};

check('ready', p.ready, true);
check('accounts', p.accounts.length, 2);
// interimAvailable must win over closingBooked, else the page disagrees with the bank app
check('acc-a balance_oere (interimAvailable)', p.accounts[0].balance_oere, 1234567);
check('acc-a balance_type', p.accounts[0].balance_type, 'interimAvailable');
check('acc-a formatted', p.accounts[0].balance_kr, '12.345,67');
check('acc-a iban tail only', p.accounts[0].iban_tail, '6243');
check('no full iban leaked', JSON.stringify(p).includes('DK5000400440116243'), false);
check('acc-b falls back to product name', p.accounts[1].name, 'Opsparing');
check('total balance', p.totals.balance_oere, 1234567 + 8000010);
check('total formatted', p.totals.balance_kr, '92.345,77');
// 249.50 * 100 in float is 24949.999999999996 - the round is the test
check('negative amount to oere', p.transactions.find((t) => t.id === 't1').amount_oere, -24950);
check('salary amount to oere', p.transactions.find((t) => t.id === 't2').amount_oere, 3511693);
check('lookback drops 2025 row', p.transactions.some((t) => t.id === 'old'), false);
check('pending flagged', p.transactions.find((t) => t.id === 't3').pending, true);
check('newest first', p.transactions[0].date, '2026-10-14');
check('out 30d', p.totals.out_30d_oere, -24950 - 9900);
check('in 30d', p.totals.in_30d_oere, 3511693);
check('kind out', p.transactions.find((t) => t.id === 't1').kind, 'out');

// Expired consent: zero accounts, honest reason, ready false
nodes['Split accounts'] = wrap([{ account_id: null, consent_status: 'EX' }]);
nodes['Fetch details'] = [];
nodes['Fetch balances'] = [];
nodes['Fetch transactions'] = [];
const p2 = new Function('$', '$input', code)($, { all: () => [] })[0].json;
check('expired consent not ready', p2.ready, false);
check('expired consent explains itself', /EX/.test(p2.reason), true);

console.log(fails === 0 ? '\nALL PASS' : '\n' + fails + ' FAILED');
process.exit(fails === 0 ? 0 : 1);
