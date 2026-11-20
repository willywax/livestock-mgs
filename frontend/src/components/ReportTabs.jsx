import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import DateRangePicker, { yearToDateRange } from './DateRangePicker';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import {
  getSalesReport, getMortalityReport, getCalvingReport, getReproductiveStatusReport, getAbortionsReport,
} from '../lib/api';

// Report tabs for Reports.jsx. Sales and Mortality call the pre-existing /reports/sales and
// /reports/mortality endpoints with their current params; Calving, Reproductive Status and
// Abortions call the /reports/{calving,reproductive-status,abortions} endpoints.

const SPECIES = { cattle: 'Cattle', sheep: 'Sheep', goat: 'Goats' };
const CYCLE_STATUSES = ['OPEN', 'SERVED', 'PREGNANT', 'CALVED', 'ABORTED'];
const pretty = (value) => (value ? value.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : '—');
const dash = (value) => (value === null || value === undefined || value === '' ? '—' : value);
const money = (value) => (value === null || value === undefined ? '—' : `TZS ${Number(value).toLocaleString()}`);
const percent = (value) => (value === null || value === undefined ? '—' : `${Number(value).toFixed(2)}%`);
const day = (value) => (value ? String(value).slice(0, 10) : '—');
const dateParam = (date) => format(date, 'yyyy-MM-dd');

function errorText(error) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : 'Could not load this report. Please retry.';
}

// Loads on mount and whenever the (JSON-serialisable) params change. Tab content unmounts when the
// tab is not selected, so a report is only requested once its tab is opened.
function useReport(fetcher, params) {
  const [state, setState] = useState({ data: null, loading: true, error: '' });
  const [refresh, setRefresh] = useState(0);
  const key = JSON.stringify(params);
  useEffect(() => {
    let active = true;
    setState({ data: null, loading: true, error: '' });
    fetcher(JSON.parse(key))
      .then(({ data }) => { if (active) setState({ data, loading: false, error: '' }); })
      .catch((error) => { if (active) setState({ data: null, loading: false, error: errorText(error) }); });
    return () => { active = false; };
  }, [fetcher, key, refresh]);
  return { ...state, reload: () => setRefresh((n) => n + 1) };
}

function Filters({ locations, filters, onChange, dates = 'required', showStatuses = false }) {
  const set = (patch) => onChange({ ...filters, ...patch });
  const toggleStatus = (status) => set({
    statuses: filters.statuses.includes(status) ? filters.statuses.filter((s) => s !== status) : [...filters.statuses, status],
  });
  return (
    <Card className="border-border/60"><CardContent className="p-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="space-y-1 text-xs text-muted-foreground">Location
          <select value={filters.location} onChange={(e) => set({ location: e.target.value })}
            className="mt-1 block w-48 rounded-md border bg-background p-2 text-sm text-foreground">
            <option value="">All locations</option>
            {locations.map((loc) => <option key={loc.id} value={loc.id}>{loc.name}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-xs text-muted-foreground">Species
          <select value={filters.species} onChange={(e) => set({ species: e.target.value })}
            className="mt-1 block w-40 rounded-md border bg-background p-2 text-sm text-foreground">
            <option value="">All species</option>
            {Object.entries(SPECIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        {dates !== 'none' && (
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Date range</span>
            <div className="flex items-center gap-3">
              <DateRangePicker value={filters.range} onChange={(range) => { if (range?.from && range?.to) set({ range }); }} />
              {dates === 'optional' && (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={filters.allDates} onChange={(e) => set({ allDates: e.target.checked })} />
                  All dates
                </label>
              )}
            </div>
          </div>
        )}
        {showStatuses && (
          <fieldset className="space-y-1">
            <legend className="text-xs text-muted-foreground">Latest cycle status</legend>
            <div className="flex flex-wrap gap-3">
              {CYCLE_STATUSES.map((status) => (
                <label key={status} className="flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={filters.statuses.includes(status)} onChange={() => toggleStatus(status)} />
                  {pretty(status)}
                </label>
              ))}
            </div>
          </fieldset>
        )}
      </div>
    </CardContent></Card>
  );
}

function useFilters() {
  return useState(() => ({ location: '', species: '', range: yearToDateRange(), allDates: false, statuses: [] }));
}

const baseParams = (f) => ({ location_id: f.location || undefined, species: f.species || undefined });
const rangeParams = (f) => ({ date_from: dateParam(f.range.from), date_to: dateParam(f.range.to) });

function ReportState({ report, label, children }) {
  if (report.loading) return <p role="status" className="rounded-lg border p-8">Loading {label}…</p>;
  if (report.error) {
    return (
      <div role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">
        {report.error} <Button variant="outline" size="sm" onClick={report.reload}>Retry</Button>
      </div>
    );
  }
  return report.data ? children : null;
}

function Stat({ label, value }) {
  return (
    <Card className="border-border/60"><CardContent className="p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </CardContent></Card>
  );
}

function Tags({ tags }) {
  if (!tags || !tags.length) return <span className="text-muted-foreground">—</span>;
  return <span className="text-xs text-muted-foreground">{tags.map((t) => `${pretty(t.id_type)}: ${t.id_value}`).join(' · ')}</span>;
}

function Animal({ tag, tags }) {
  return <div><div className="font-medium">{dash(tag)}</div><Tags tags={tags} /></div>;
}

function DataTable({ columns, rows, empty, rowKey }) {
  return (
    <Card className="border-border/60"><CardContent className="overflow-x-auto p-0">
      <Table>
        <TableHeader><TableRow>{columns.map((c) => <TableHead key={c.label} className={c.right ? 'text-right' : ''}>{c.label}</TableHead>)}</TableRow></TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={rowKey ? rowKey(row, i) : i}>
              {columns.map((c) => <TableCell key={c.label} className={c.right ? 'text-right' : ''}>{c.render(row)}</TableCell>)}
            </TableRow>
          ))}
          {!rows.length && <TableRow><TableCell colSpan={columns.length} className="p-6 text-center text-muted-foreground">{empty}</TableCell></TableRow>}
        </TableBody>
      </Table>
    </CardContent></Card>
  );
}

// ---------------- Sales: GET /api/reports/sales (date_from, date_to required) ----------------
export function SalesReportTab({ locations }) {
  const [filters, setFilters] = useFilters();
  const report = useReport(getSalesReport, { ...baseParams(filters), ...rangeParams(filters) });
  return (
    <div className="space-y-4" data-testid="sales-report-tab">
      <Filters locations={locations} filters={filters} onChange={setFilters} />
      <ReportState report={report} label="sales report">
        {report.data && <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Total revenue" value={money(report.data.summary.total_revenue)} />
            <Stat label="Head sold" value={report.data.summary.total_head} />
            <Stat label="Avg price / head" value={money(report.data.summary.avg_price_per_head)} />
          </div>
          <Card className="border-border/60"><CardHeader><CardTitle className="text-lg">By month</CardTitle></CardHeader><CardContent className="p-0">
            <DataTable rowKey={(r) => r.month} empty="No sales in this period."
              columns={[
                { label: 'Month', render: (r) => r.month },
                { label: 'Head', right: true, render: (r) => r.head_count },
                { label: 'Revenue', right: true, render: (r) => money(r.revenue) },
              ]}
              rows={report.data.by_period} />
          </CardContent></Card>
          <DataTable rowKey={(r, i) => `${r.event_id}-${i}`} empty="No sales in this period."
            columns={[
              { label: 'Date', render: (r) => day(r.date) },
              { label: 'Farm', render: (r) => r.farm },
              { label: 'Species', render: (r) => SPECIES[r.species] || r.species },
              { label: 'Category', render: (r) => dash(r.category) },
              { label: 'Qty', right: true, render: (r) => r.qty },
              { label: 'Price / head', right: true, render: (r) => money(r.price_per_head) },
              { label: 'Total', right: true, render: (r) => money(r.total_price) },
              { label: 'Customer', render: (r) => dash(r.customer_name) },
            ]}
            rows={report.data.line_items} />
        </>}
      </ReportState>
    </div>
  );
}

// ---------------- Mortality: GET /api/reports/mortality (date_from, date_to required) ----------------
export function MortalityReportTab({ locations }) {
  const [filters, setFilters] = useFilters();
  const report = useReport(getMortalityReport, { ...baseParams(filters), ...rangeParams(filters) });
  return (
    <div className="space-y-4" data-testid="mortality-report-tab">
      <Filters locations={locations} filters={filters} onChange={setFilters} />
      <ReportState report={report} label="mortality report">
        {report.data && <>
          {report.data.flagged.length > 0 && (
            <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 font-medium text-red-800">
              ⚠ {report.data.flagged.length} farm/species combinations above their mortality threshold.
            </div>
          )}
          <p className="text-sm text-muted-foreground">
            {report.data.summary.total_deaths} deaths in the selected period.{' '}
            <Link to="/reports/mortality" className="underline">Open the full Mortality Dashboard</Link>
          </p>
          <DataTable rowKey={(r) => r.species} empty="No stock or deaths for these filters."
            columns={[
              { label: 'Species', render: (r) => SPECIES[r.species] || r.species },
              { label: 'Deaths', right: true, render: (r) => r.deaths },
              { label: 'Rate', right: true, render: (r) => percent(r.mortality_rate_pct) },
              { label: 'Threshold', right: true, render: (r) => percent(r.threshold_pct) },
              { label: 'Status', render: (r) => (r.is_alert ? 'Alert' : 'OK') },
            ]}
            rows={report.data.by_species.filter((r) => r.avg_stock > 0 || r.deaths > 0)} />
          <DataTable rowKey={(r) => `${r.location_id}-${r.species}`} empty="No farms to compare."
            columns={[
              { label: 'Farm', render: (r) => r.farm },
              { label: 'Species', render: (r) => SPECIES[r.species] || r.species },
              { label: 'Deaths', right: true, render: (r) => r.deaths },
              { label: 'Rate', right: true, render: (r) => percent(r.mortality_rate_pct) },
              { label: 'Threshold', right: true, render: (r) => percent(r.threshold_pct) },
              { label: 'Status', render: (r) => (r.is_alert ? 'Alert' : 'OK') },
            ]}
            rows={report.data.by_farm} />
          <DataTable rowKey={(r) => r.cause_name} empty="No deaths with a recorded cause."
            columns={[
              { label: 'Cause of death', render: (r) => r.cause_name },
              { label: 'Deaths', right: true, render: (r) => r.count },
              { label: '% of deaths', right: true, render: (r) => `${r.pct_of_total}%` },
            ]}
            rows={report.data.by_cause.filter((r) => r.cause_name != null)} />
        </>}
      </ReportState>
    </div>
  );
}

// ---------------- Calving: GET /api/reports/calving ----------------
export function CalvingReportTab({ locations }) {
  const [filters, setFilters] = useFilters();
  const params = { ...baseParams(filters), ...(filters.allDates ? {} : rangeParams(filters)) };
  const report = useReport(getCalvingReport, params);
  return (
    <div className="space-y-4" data-testid="calving-report-tab">
      <Filters locations={locations} filters={filters} onChange={setFilters} dates="optional" />
      <ReportState report={report} label="calving report">
        {report.data && <>
          <div className="grid gap-4 sm:grid-cols-4">
            <Stat label="Calvings" value={report.data.summary.total} />
            <Stat label="Live" value={report.data.summary.live} />
            <Stat label="Stillbirths" value={report.data.summary.stillbirths} />
            <Stat label="Assisted" value={report.data.summary.assisted} />
          </div>
          <DataTable empty="No calvings found for these filters."
            columns={[
              { label: 'Date', render: (r) => day(r.calved_date) },
              { label: 'Dam', render: (r) => <Animal tag={r.dam_tag} tags={r.dam_tags} /> },
              { label: 'Location', render: (r) => dash(r.location_name) },
              { label: 'Species', render: (r) => SPECIES[r.species] || r.species },
              { label: 'Outcome', render: (r) => pretty(r.calving_outcome) },
              { label: 'Interval (days)', right: true, render: (r) => dash(r.calving_interval_days) },
              { label: 'Calf', render: (r) => (r.calf_tag ? <Animal tag={r.calf_tag} tags={r.calf_tags} /> : '—') },
              { label: 'Calf sex', render: (r) => pretty(r.calf_sex) },
              { label: 'Calf status', render: (r) => pretty(r.calf_status) },
            ]}
            rows={report.data.rows} />
        </>}
      </ReportState>
    </div>
  );
}

// ---------------- Reproductive status: GET /api/reports/reproductive-status ----------------
export function ReproductiveStatusReportTab({ locations }) {
  const [filters, setFilters] = useFilters();
  const params = { ...baseParams(filters), status: filters.statuses.length ? filters.statuses.join(',') : undefined };
  const report = useReport(getReproductiveStatusReport, params);
  return (
    <div className="space-y-4" data-testid="repro-status-report-tab">
      <Filters locations={locations} filters={filters} onChange={setFilters} dates="none" showStatuses />
      <ReportState report={report} label="reproductive status report">
        {report.data && <>
          <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-7">
            <Stat label="Females" value={report.data.summary.total} />
            {[...CYCLE_STATUSES, 'unknown'].map((status) => (
              <Stat key={status} label={pretty(status)} value={report.data.summary.by_status[status] ?? 0} />
            ))}
          </div>
          <DataTable empty="No females found for these filters."
            columns={[
              { label: 'Animal', render: (r) => <Animal tag={r.tag_number} tags={r.tags} /> },
              { label: 'Location', render: (r) => dash(r.location_name) },
              { label: 'Species', render: (r) => SPECIES[r.species] || r.species },
              { label: 'Cycle status', render: (r) => pretty(r.cycle_status) },
              { label: 'Last calving', render: (r) => day(r.last_calving_date) },
              { label: 'Interval (days)', right: true, render: (r) => dash(r.calving_interval_days) },
              { label: 'Calvings', right: true, render: (r) => dash(r.lifetime_calvings) },
              { label: 'Months pregnant', right: true, render: (r) => dash(r.months_pregnant) },
              { label: 'Last PD', render: (r) => day(r.last_pd_date) },
              { label: 'Expected calving', render: (r) => day(r.expected_calving_date) },
            ]}
            rows={report.data.rows} />
        </>}
      </ReportState>
    </div>
  );
}

// ---------------- Abortions: GET /api/reports/abortions ----------------
export function AbortionsReportTab({ locations }) {
  const [filters, setFilters] = useFilters();
  const params = { ...baseParams(filters), ...(filters.allDates ? {} : rangeParams(filters)) };
  const report = useReport(getAbortionsReport, params);
  return (
    <div className="space-y-4" data-testid="abortions-report-tab">
      <Filters locations={locations} filters={filters} onChange={setFilters} dates="optional" />
      <ReportState report={report} label="abortions report">
        {report.data && <>
          <div className="grid gap-4 sm:grid-cols-4">
            <Stat label="Abortions" value={report.data.summary.total} />
            {Object.entries(report.data.summary.by_stage).map(([stage, count]) => <Stat key={stage} label={`${pretty(stage)} stage`} value={count} />)}
          </div>
          <p className="text-xs text-muted-foreground">Dates are when the cycle was recorded, not necessarily when the abortion happened.</p>
          <DataTable empty="No abortions found for these filters."
            columns={[
              { label: 'Recorded', render: (r) => day(r.abortion_date) },
              { label: 'Animal', render: (r) => <Animal tag={r.tag_number} tags={r.tags} /> },
              { label: 'Location', render: (r) => dash(r.location_name) },
              { label: 'Species', render: (r) => SPECIES[r.species] || r.species },
              { label: 'Stage', render: (r) => pretty(r.abortion_stage) },
              { label: 'Cycle #', right: true, render: (r) => r.cycle_number },
              { label: 'Notes', render: (r) => dash(r.notes) },
            ]}
            rows={report.data.rows} />
        </>}
      </ReportState>
    </div>
  );
}
