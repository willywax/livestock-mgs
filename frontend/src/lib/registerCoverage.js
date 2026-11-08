// Shared helpers for the animal-register reconciliation UI (Animals page panel, Dashboard card).
// Input rows are ReconciliationRow objects from GET /api/animals/register-reconciliation:
// { location_id, location_name, species, stock_count, registered_active, registered_pct, unregistered }

export const ATTENTION_THRESHOLD = 50; // % below which a farm "needs attention"

// green >= 80, amber 50-79, red < 50; grey when there is no stock to compare against.
export function coverageTone(pct) {
  if (pct === null || pct === undefined) return 'grey';
  if (pct >= 80) return 'green';
  if (pct >= 50) return 'amber';
  return 'red';
}

export const TONE_TEXT = {
  green: 'text-green-700',
  amber: 'text-amber-600',
  red: 'text-red-600',
  grey: 'text-muted-foreground',
};
export const TONE_BG = {
  green: 'bg-green-100 text-green-700',
  amber: 'bg-amber-100 text-amber-700',
  red: 'bg-red-100 text-red-700',
  grey: 'bg-gray-100 text-gray-600',
};
export const TONE_BAR = {
  green: 'bg-green-500',
  amber: 'bg-amber-400',
  red: 'bg-red-500',
  grey: 'bg-gray-300',
};

const TONE_RANK = { red: 0, amber: 1, green: 2, grey: 3 };

// Red rows first, then amber, then green (grey last); farm name, then species, within each group.
export function sortReconciliationRows(rows) {
  return [...rows].sort(function (a, b) {
    const ra = TONE_RANK[coverageTone(a.registered_pct)];
    const rb = TONE_RANK[coverageTone(b.registered_pct)];
    if (ra !== rb) return ra - rb;
    const byName = (a.location_name || '').localeCompare(b.location_name || '');
    return byName !== 0 ? byName : (a.species || '').localeCompare(b.species || '');
  });
}

// Overall figures:
//  - pct         = total registered / total stock, over rows that have stock (extras in
//                  zero-stock rows cannot push it past 100%); null when there is no stock
//  - unregistered = sum of the positive gaps only
//  - attentionFarms = farms (all species combined, stock > 0) whose coverage is < 50%
export function summariseReconciliation(rows) {
  const withStock = rows.filter(function (r) { return r.stock_count > 0; });
  const totalStock = withStock.reduce(function (n, r) { return n + r.stock_count; }, 0);
  const registered = withStock.reduce(function (n, r) { return n + r.registered_active; }, 0);
  const unregistered = rows.reduce(function (n, r) { return n + Math.max(0, r.unregistered); }, 0);

  const farms = {};
  withStock.forEach(function (r) {
    const f = farms[r.location_id] || (farms[r.location_id] = { stock: 0, registered: 0 });
    f.stock += r.stock_count;
    f.registered += r.registered_active;
  });
  const attentionFarms = Object.values(farms).filter(function (f) {
    return (f.registered / f.stock) * 100 < ATTENTION_THRESHOLD;
  }).length;

  return {
    pct: totalStock > 0 ? Math.round((registered / totalStock) * 100) : null,
    registered,
    unregistered,
    totalStock,
    attentionFarms,
  };
}
