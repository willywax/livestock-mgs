import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowClockwise, Bell, Warning, Heart, Baby, Question, ArrowsClockwise } from '@phosphor-icons/react';
import { getLocations, getReproductiveStatusBoard } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import ReproductiveEventDialog from '../components/ReproductiveEventDialog';
import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';

export const BUCKETS = [
  { key: 'open', title: 'Open', icon: Heart, color: 'border-green-200 bg-green-50 text-green-900', description: 'Not currently pregnant.', empty: 'No females are currently recorded as open.' },
  { key: 'pregnant', title: 'Pregnant', icon: Heart, color: 'border-blue-200 bg-blue-50 text-blue-900', description: 'Females with a confirmed pregnant status.', empty: 'No females are currently recorded as pregnant.' },
  { key: 'close_to_calving', title: 'Close to calving', icon: Baby, color: 'border-amber-400 bg-blue-50 text-blue-950', description: 'Estimated to give birth within the next 30 days.', empty: 'No animals close to calving in the next 30 days.' },
  { key: 'due_this_month', title: 'Due this month', icon: Bell, color: 'border-amber-200 bg-amber-50 text-amber-900', description: 'Due today through the next 30 days.', empty: 'No animals due in the next 30 days.' },
  { key: 'recently_calved', title: 'Recently calved', icon: Baby, color: 'border-teal-200 bg-teal-50 text-teal-900', description: 'Gave birth within the last 30 days.', empty: 'No calvings recorded in the last 30 days.' },
  { key: 'recently_aborted', title: 'Recently aborted', icon: Warning, color: 'border-red-200 bg-red-50 text-red-900', description: 'An abortion was recorded in the last 30 days.', empty: 'No abortions recorded in the last 30 days.' },
  { key: 'repeat_breeders', title: 'Repeat breeders', icon: ArrowsClockwise, color: 'border-orange-200 bg-orange-50 text-orange-900', description: 'Three or more services without conception.', empty: 'No repeat breeders recorded.' },
  { key: 'unknown_status', title: 'Unknown status', icon: Question, color: 'border-gray-200 bg-gray-50 text-gray-800', description: 'Below breeding age, or birth date is not recorded.', empty: 'No young or age-unknown females without a status.' },
  { key: 'needs_attention', title: 'Needs attention', icon: Warning, color: 'border-red-500 bg-red-50 text-red-900', description: 'Breeding-age status unknown, pregnancy PD over 180 days old, or repeated services.', empty: 'No females currently meet the attention criteria.' },
];

export function quickAction(key, animal) {
  if (key === 'needs_attention') return null;
  if (animal.reproductive_status === 'pregnant') return { type: 'calving', label: 'Record calving' };
  if (animal.reproductive_status === 'open') return { type: 'service', label: 'Record service' };
  return null;
}

const detailTitle = (key) => ({ pregnant: 'Months pregnant', close_to_calving: 'Est. calving', due_this_month: 'Est. calving', recently_calved: 'Calved', repeat_breeders: 'Failed services', recently_aborted: 'Last event', unknown_status: 'Age (months)', needs_attention: 'Reason' }[key] || 'Last event');
export function animalDetail(key, animal) {
  if (key === 'pregnant') return animal.months_pregnant ?? 'Not recorded';
  if (key === 'close_to_calving' || key === 'due_this_month') return animal.expected_calving_date || 'Not recorded';
  if (key === 'recently_calved') return animal.last_calving_date || 'Not recorded';
  if (key === 'repeat_breeders') return animal.services_without_conception;
  if (key === 'unknown_status') return animal.age_months ?? 'Birth date unknown';
  if (key === 'needs_attention') {
    const reasons = [];
    if (animal.reproductive_status === 'unknown') reasons.push('Status unknown');
    if (animal.reproductive_status === 'pregnant' && animal.last_pd_date) reasons.push(`Last PD: ${animal.last_pd_date}`);
    if (animal.services_without_conception >= 3) reasons.push(`${animal.services_without_conception} failed services`);
    return reasons.join(' · ');
  }
  return animal.last_event_date ? `${animal.last_event_date} · ${(animal.last_event_type || '').replaceAll('_', ' ')}` : 'No event recorded';
}

export function BucketCard({ config, bucket, canWrite, onAction }) {
  const [expanded, setExpanded] = useState(bucket.count > 0);
  const [sort, setSort] = useState('tag');
  useEffect(() => { setExpanded(bucket.count > 0); }, [bucket.count]);
  const Icon = config.icon;
  const animals = [...bucket.animals].sort((a, b) => sort === 'date'
    ? (b.last_event_date || '').localeCompare(a.last_event_date || '') || a.tag_number.localeCompare(b.tag_number, undefined, { numeric: true })
    : a.tag_number.localeCompare(b.tag_number, undefined, { numeric: true }));
  return <section className="min-w-0 self-start overflow-hidden rounded-xl border bg-card shadow-sm" aria-label={config.title}>
    <div className={cn('border-b p-4', config.color)}>
      <div className="flex items-center gap-2"><Icon className="h-5 w-5" /><h2 className="flex-1 font-semibold">{config.title}</h2><span className="rounded-full bg-white/70 px-3 py-1 text-lg font-bold">{bucket.count}</span></div>
      <p className="mt-2 text-sm">{config.description}</p>
      <button type="button" className="mt-3 text-sm font-semibold underline underline-offset-4" aria-expanded={expanded} aria-controls={`bucket-${config.key}`} onClick={() => setExpanded((value) => !value)}>{expanded ? 'Hide animals' : 'Show animals'}</button>
    </div>
    <div id={`bucket-${config.key}`} hidden={!expanded}>
      {!bucket.count ? <p className="p-4 text-sm text-muted-foreground">{config.empty}</p> : <>
        <div className="flex justify-end p-3"><label className="text-sm">Sort by <select aria-label={`Sort ${config.title}`} className="ml-2 rounded border bg-background p-1" value={sort} onChange={(event) => setSort(event.target.value)}><option value="tag">Tag</option><option value="date">Last event (newest)</option></select></label></div>
        <div className="max-h-96 overflow-auto"><table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-muted"><tr>{['Tag', 'Category', 'Farm', detailTitle(config.key), 'Action'].map((name) => <th key={name} className="whitespace-nowrap px-3 py-2 font-medium">{name}</th>)}</tr></thead>
          <tbody>{animals.map((animal) => {
            const action = quickAction(config.key, animal);
            return <tr key={animal.id} className={cn('border-t', config.key === 'repeat_breeders' && (animal.services_without_conception >= 5 ? 'bg-red-50' : 'bg-amber-50'))}>
              <td className="px-3 py-2"><Link className="font-medium text-primary underline" to={`/animals/${animal.id}`}>{animal.tag_number}</Link></td>
              <td className="px-3 py-2">{animal.category}</td><td className="px-3 py-2">{animal.farm}</td>
              <td className="px-3 py-2">{animalDetail(config.key, animal)}</td>
              <td className="whitespace-nowrap px-3 py-2">{canWrite && action ? <Button size="sm" variant="outline" onClick={() => onAction({ animal, type: action.type })}>{action.label}</Button> : <Link className="text-primary underline" to={`/animals/${animal.id}`}>View animal</Link>}</td>
            </tr>;
          })}</tbody>
        </table></div>
      </>}
    </div>
  </section>;
}

export default function ReproductiveStatusBoard() {
  const { isDataEntry } = useAuth();
  const [farms, setFarms] = useState([]);
  const [farmError, setFarmError] = useState(false);
  const [farm, setFarm] = useState('');
  const [species, setSpecies] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState(null);
  const [dialog, setDialog] = useState(null);
  useEffect(() => {
    let active = true;
    getLocations().then(({ data: locations }) => { if (active) { setFarms(locations); setFarmError(false); } })
      .catch(() => { if (active) setFarmError(true); });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setData(null);
    getReproductiveStatusBoard({ ...(farm ? { farm_id: Number(farm) } : {}), ...(species ? { species } : {}) })
      .then(({ data: result }) => { if (active) { setData(result); setUpdated(new Date()); } })
      .catch(() => { if (active) setError('Unable to load the reproductive status board. Please refresh to try again.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [farm, species, refresh]);
  return <div className="space-y-6" data-testid="reproductive-status-board">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="font-heading text-3xl font-bold">Reproductive Status Board</h1><p className="mt-1 text-sm text-muted-foreground">The active female herd, from breeding to calving.</p></div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium">Farm <select className="ml-2 rounded-md border bg-background p-2" aria-label="Farm" value={farm} onChange={(event) => setFarm(event.target.value)}><option value="">All farms</option>{farms.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
        <Button variant="outline" disabled={loading} onClick={() => setRefresh((value) => value + 1)}><ArrowClockwise className="mr-2 h-4 w-4" />Refresh</Button>
      </div>
    </header>
    {farmError && <p role="alert" className="text-sm text-red-700">Farm choices could not be loaded. Refresh to retry; the all-farms board is still available.</p>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div role="group" aria-label="Species" className="flex flex-wrap gap-2">{[['', 'All'], ['cattle', 'Cattle'], ['sheep', 'Sheep'], ['goat', 'Goats']].map(([value, label]) => <Button key={value} size="sm" variant={species === value ? 'default' : 'outline'} aria-pressed={species === value} onClick={() => setSpecies(value)}>{label}</Button>)}</div>
      {updated && !loading && !error && <span className="text-xs text-muted-foreground">Last updated {updated.toLocaleString()}</span>}
    </div>
    {loading && <p role="status" className="py-12 text-center text-muted-foreground">Loading herd status…</p>}
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
    {data && <>
      <p className="text-sm text-muted-foreground">{data.summary.total_breeding_females} breeding females · Status known for {data.summary.status_known_pct}% · {data.needs_attention.count} need attention</p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{BUCKETS.slice(0, 5).map((config) => <div key={config.key} className={cn('rounded-lg border p-4', config.color)}><p className="text-sm font-medium">{config.title}</p><p className="mt-1 text-3xl font-bold">{data[config.key].count}</p></div>)}</div>
      <p className="text-xs text-muted-foreground">Animals can appear in more than one category. Close to calving and Due this month both cover the next 30 days. Dates are estimates based on the last PD test.</p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{BUCKETS.map((config) => <BucketCard key={`${farm}:${species}:${config.key}`} config={config} bucket={data[config.key]} canWrite={isDataEntry} onAction={setDialog} />)}</div>
    </>}
    {dialog && <ReproductiveEventDialog animal={dialog.animal} initialType={dialog.type} onClose={() => setDialog(null)} onSaved={() => setRefresh((value) => value + 1)} />}
  </div>;
}
