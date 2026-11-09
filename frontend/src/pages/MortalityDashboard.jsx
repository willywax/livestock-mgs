import React, { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, LabelList } from 'recharts';
import DateRangePicker from '../components/DateRangePicker';
import { getLocations, getMortalityReport } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';

const speciesNames = { cattle: 'Cattle', sheep: 'Sheep', goat: 'Goats' };
const colors = { cattle: '#2D5A27', sheep: '#0284C7', goat: '#D97706' };
const percent = (value) => value == null ? '—' : `${Number(value).toFixed(2)}%`;
function status(row) {
  if (row.is_alert) return { label: '🔴 Alert', color: 'border-red-500', chip: 'bg-red-100 text-red-800' };
  if (row.mortality_rate_pct == null) return { label: 'No rate', color: 'border-slate-300', chip: 'bg-slate-100 text-slate-700' };
  if (row.mortality_rate_pct > 0 && row.threshold_pct == null) return { label: '🟡 Watch', color: 'border-amber-500', chip: 'bg-amber-100 text-amber-800' };
  return { label: '🟢 OK', color: 'border-green-500', chip: 'bg-green-100 text-green-800' };
}
function initialRange() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return { from: new Date(Number(values.year), 0, 1), to: new Date(Number(values.year), Number(values.month) - 1, Number(values.day)) };
}

export default function MortalityDashboard() {
  const [range, setRange] = useState(initialRange);
  const [location, setLocation] = useState('');
  const [species, setSpecies] = useState('');
  const [locations, setLocations] = useState([]);
  const [locationError, setLocationError] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const dateFrom = format(range.from, 'yyyy-MM-dd');
  const dateTo = format(range.to, 'yyyy-MM-dd');

  useEffect(() => {
    let active = true;
    setLocationError('');
    getLocations().then(({ data }) => { if (active) setLocations(data); })
      .catch(() => { if (active) setLocationError('Could not load farms. Use Refresh to retry.'); });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setReport(null);
    getMortalityReport({ date_from: dateFrom, date_to: dateTo, location_id: location || undefined, species: species || undefined })
      .then(({ data }) => { if (active) setReport(data); })
      .catch(() => { if (active) setError('Could not load mortality data. Please retry.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [dateFrom, dateTo, location, species, refresh]);

  const farms = [...(report?.by_farm || [])].sort((a, b) => Number(b.is_alert) - Number(a.is_alert)
    || (b.mortality_rate_pct ?? -Infinity) - (a.mortality_rate_pct ?? -Infinity) || a.farm.localeCompare(b.farm));
  const causes = [...(report?.by_cause || [])].filter((row) => row.cause_name != null)
    .sort((a, b) => Number(a.cause_name.toLowerCase() === 'unknown') - Number(b.cause_name.toLowerCase() === 'unknown') || b.count - a.count);
  const monthly = (report?.by_month || []).map((row) => ({ month: row.month, ...row.by_species }));
  const flaggedSpecies = [...new Set((report?.flagged || []).map((row) => speciesNames[row.species] || row.species))];
  const selectedSpecies = species ? [species] : Object.keys(speciesNames);

  return <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h1 className="font-heading text-3xl font-bold">Mortality Dashboard</h1><p className="mt-1 text-sm text-muted-foreground">Deaths, causes, and farm-level mortality alerts.</p></div>
      <DateRangePicker value={range} onChange={setRange} />
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Farm<select value={location} onChange={(event) => setLocation(event.target.value)} className="mt-1 block w-48 rounded-md border bg-background p-2">
        <option value="">All farms</option>{locations.map((loc) => <option key={loc.id} value={loc.id}>{loc.name}</option>)}
      </select></label>
      <label className="text-sm">Species<select value={species} onChange={(event) => setSpecies(event.target.value)} className="mt-1 block w-40 rounded-md border bg-background p-2">
        <option value="">All species</option>{Object.entries(speciesNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <Button variant="outline" onClick={() => setRefresh((value) => value + 1)}>Refresh</Button>
    </div>
    {locationError && <p role="alert" className="text-sm text-red-700">{locationError}</p>}
    {loading ? <p role="status" className="rounded-lg border p-8">Loading mortality report…</p> : error ?
      <div role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">{error} <Button variant="outline" onClick={() => setRefresh((value) => value + 1)}>Retry</Button></div> : report && <>
      {report.flagged.length > 0 && <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 font-medium text-red-800">
        ⚠ {report.flagged.length} alerts — mortality above threshold in {flaggedSpecies.join(', ')}
      </div>}
      <p className="text-sm text-muted-foreground">{report.summary.total_deaths} deaths in the selected period. Rates use average opening and closing stock. A dash indicates no positive average stock or no threshold.</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {report.by_species.filter((row) => row.avg_stock > 0 || row.deaths > 0).map((row) => <Card key={row.species} className={`border-2 ${status(row).color}`}>
          <CardHeader className="pb-2"><CardTitle>{speciesNames[row.species]}</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-semibold">Deaths: {row.deaths}</p>
            <div className="mt-3 flex flex-wrap justify-between gap-2 text-sm"><span>Rate: {percent(row.mortality_rate_pct)}</span><span>Threshold: {percent(row.threshold_pct)}</span></div>
            <span className={`mt-3 inline-block rounded-full px-2 py-1 text-xs ${status(row).chip}`}>{status(row).label}</span>
          </CardContent></Card>)}
      </div>
      {!report.by_species.length && <p className="rounded-lg border p-6 text-muted-foreground">No stock or deaths found for these filters.</p>}
      <Card><CardHeader><CardTitle>Monthly deaths</CardTitle><p className="text-sm text-muted-foreground">Latest 12 months ending in the selected period, limited to its dates.</p></CardHeader>
        <CardContent><div className="h-80 w-full min-w-0" role="img" aria-label="Monthly death counts by species">
          <ResponsiveContainer width="100%" height="100%"><LineChart data={monthly} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} />
            <Tooltip /><Legend />{selectedSpecies.map((key) => <Line key={key} type="monotone" dataKey={key} name={speciesNames[key]} stroke={colors[key]} strokeWidth={2} dot={{ r: 3 }} />)}
          </LineChart></ResponsiveContainer>
        </div><details className="mt-3 text-sm"><summary className="cursor-pointer text-muted-foreground">View monthly values</summary>
          <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th className="p-2">Month</th>{selectedSpecies.map((key) => <th className="p-2" key={key}>{speciesNames[key]}</th>)}</tr></thead>
            <tbody>{monthly.map((row) => <tr key={row.month}><td className="p-2">{row.month}</td>{selectedSpecies.map((key) => <td className="p-2" key={key}>{row[key] || 0}</td>)}</tr>)}</tbody></table></div>
        </details></CardContent></Card>
      {causes.length > 0 && <Card><CardHeader><CardTitle>Cause of death</CardTitle></CardHeader><CardContent>
        <div className="w-full min-w-0" style={{ height: Math.max(220, causes.length * 44) }} role="img" aria-label="Death counts by structured cause, with percentage of all deaths">
          <ResponsiveContainer width="100%" height="100%"><BarChart data={causes} layout="vertical" margin={{ right: 65, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="cause_name" width={130} tick={{ fontSize: 12 }} />
            <Tooltip /><Bar dataKey="count" name="Deaths" fill="#b45309" radius={[0, 4, 4, 0]}><LabelList dataKey="pct_of_total" position="right" formatter={(value) => `${value}%`} /></Bar>
          </BarChart></ResponsiveContainer>
        </div><p className="mt-3 text-sm text-muted-foreground">Cause breakdown only includes deaths recorded with a cause selected</p>
      </CardContent></Card>}
      <Card><CardHeader><CardTitle>Farm comparison</CardTitle></CardHeader><CardContent>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Farm', 'Species', 'Deaths', 'Rate %', 'Threshold %', 'Status'].map((heading) => <th key={heading} className="border-b p-3 font-medium">{heading}</th>)}</tr></thead>
          <tbody>{farms.map((row) => <tr key={`${row.location_id}-${row.species}`} className="border-b last:border-0">
            <td className="p-3 font-medium">{row.farm}</td><td className="p-3">{speciesNames[row.species]}</td><td className="p-3">{row.deaths}</td><td className="p-3">{percent(row.mortality_rate_pct)}</td><td className="p-3">{percent(row.threshold_pct)}</td>
            <td className="p-3"><span className={`whitespace-nowrap rounded-full px-2 py-1 text-xs ${status(row).chip}`}>{status(row).label}</span></td>
          </tr>)}{!farms.length && <tr><td colSpan={6} className="p-6 text-center text-muted-foreground">No farms to compare.</td></tr>}</tbody>
        </table></div>
      </CardContent></Card>
    </>}
  </div>;
}
