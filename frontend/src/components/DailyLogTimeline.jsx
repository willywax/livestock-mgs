import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getAnimalDailyLogTimeline } from '../lib/api';
import { EVENT_TYPES } from '../lib/utils';
import { Button } from './ui/button';

const colors = {
  birth: 'bg-pink-500', pd_test: 'bg-pink-500', service: 'bg-pink-500', abortion: 'bg-pink-500',
  transfer: 'bg-orange-500', category_change: 'bg-orange-500', weaning: 'bg-orange-500',
  death: 'bg-black', sold: 'bg-gray-500', gift_out: 'bg-gray-500', bought: 'bg-green-500', gift_in: 'bg-green-500',
};

export default function DailyLogTimeline({ animalId }) {
  const [filters, setFilters] = useState({ from_date: '', to_date: '', event_type: '' });
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    if (page === 1) { setItems([]); setTotal(0); }
    const params = { page, page_size: 20, ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)) };
    getAnimalDailyLogTimeline(animalId, params).then(({ data }) => {
      if (!active) return;
      setTotal(data.total);
      setItems((previous) => page === 1 ? data.items : [...new Map([...previous, ...data.items].map((item) => [item.event_id, item])).values()]);
    }).catch(() => {
      if (active) setError('Unable to load daily-log events. Check the date range and try again.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [animalId, filters, page, retry]);
  const changeFilter = (key, value) => { setPage(1); setFilters((previous) => ({ ...previous, [key]: value })); };
  return <div className="space-y-4" data-testid="daily-log-timeline">
    <div className="flex flex-wrap gap-3">
      <label className="text-sm">From<input className="ml-2 rounded border bg-background p-2" aria-label="Timeline from date" type="date" value={filters.from_date} onChange={(e) => changeFilter('from_date', e.target.value)} /></label>
      <label className="text-sm">To<input className="ml-2 rounded border bg-background p-2" aria-label="Timeline to date" type="date" value={filters.to_date} onChange={(e) => changeFilter('to_date', e.target.value)} /></label>
      <label className="text-sm">Event<select className="ml-2 rounded border bg-background p-2" aria-label="Timeline event type" value={filters.event_type} onChange={(e) => changeFilter('event_type', e.target.value)}><option value="">All events</option>{Object.entries(EVENT_TYPES).map(([key, config]) => <option key={key} value={key}>{config.label}</option>)}</select></label>
    </div>
    {!loading && !error && items.length === 0 && <p className="text-sm text-muted-foreground">No events recorded for this animal yet.</p>}
    <ol className="space-y-3">{items.map((item) => <li key={item.event_id} className="flex flex-wrap items-start gap-3 rounded-lg border p-4">
      <span aria-hidden="true" className={`mt-1.5 h-3 w-3 shrink-0 rounded-full ${colors[item.event_type] || 'bg-blue-500'}`} />
      <div className="min-w-0 flex-1"><Link className="font-medium text-primary hover:underline" to={`/daily-logs/${item.daily_log_id}`}>{item.event_type_label}</Link>
        <p className="text-sm text-muted-foreground">{item.farm_name} · {item.event_date}</p>
        <p className="text-xs text-muted-foreground">Quantity: {item.quantity}{item.result ? ` · Result: ${item.result}` : ''}{item.recorded_by_name ? ` · ${item.recorded_by_name}` : ''}</p>
      </div>
      {item.notes && <p title={item.notes} className="max-w-sm break-words text-sm text-muted-foreground">{item.notes.length > 60 ? item.notes.slice(0, 60) + '…' : item.notes}</p>}
    </li>)}</ol>
    {loading && <p role="status" className="text-sm text-muted-foreground">Loading events…</p>}
    {error && <div role="alert" className="space-y-2 text-sm text-red-700"><p>{error}</p><Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Retry</Button></div>}
    {!error && items.length < total && <Button variant="outline" disabled={loading} onClick={() => setPage((value) => value + 1)}>Load more</Button>}
  </div>;
}
