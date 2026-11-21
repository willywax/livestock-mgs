import React, { useState, useEffect, useRef } from 'react';
import { format, subDays } from 'date-fns';
import { toast } from 'sonner';
import {
  ChartBar, CalendarBlank, Baby, Skull, CurrencyCircleDollar, Warning, FirstAid, Clock,
  ListBullets, CalendarCheck, Heartbeat, ClipboardText, TrendUp, Download, MagnifyingGlass, Syringe,
} from '@phosphor-icons/react';
import {
  getLocations, getDailyReport, getRangeReport, getAnalyticsReport, getDetailedReport,
  getCalvingReport, getReproductiveStatusReport, getAbortionsReport, getSalesReport, getMortalityReport,
  getUpcomingHealthEvents, getFarmHealthEvents,
} from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Skeleton } from '../components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import DateRangePicker from '../components/DateRangePicker';
import { EVENT_TYPES, SPECIES_CONFIG } from '../lib/utils';

// ---------------------------------------------------------------- helpers
const SPECIES = { cattle: 'Cattle', sheep: 'Sheep', goat: 'Goats' };
const CYCLE_STATUSES = ['OPEN', 'SERVED', 'PREGNANT', 'CALVED', 'ABORTED'];
const pretty = (v) => (v ? String(v).replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : '—');
const dash = (v) => (v === null || v === undefined || v === '' ? '—' : v);
const money = (v) => (v === null || v === undefined ? '—' : `TZS ${Number(v).toLocaleString()}`);
const pct = (v) => (v === null || v === undefined ? '—' : `${Number(v).toFixed(2)}%`);
const day = (v) => (v ? String(v).slice(0, 10) : '—');
const ymd = (d) => format(d, 'yyyy-MM-dd');
const speciesName = (s) => SPECIES[s] || s || '—';
const tagText = (tags) => (tags && tags.length ? tags.map((t) => `${pretty(t.id_type)}: ${t.id_value}`).join(' · ') : '');
const animalText = (tag, tags) => [dash(tag), tagText(tags)].filter((x) => x && x !== '').join(' ');

function errorText(error) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : 'Could not load this report. Please retry.';
}

function csvCell(v) {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(name, result) {
  const lines = [];
  (result.stats || []).forEach((s) => lines.push([s.label, s.value].map(csvCell).join(',')));
  (result.tables || []).forEach((t) => {
    if (lines.length) lines.push('');
    if (t.title) lines.push(csvCell(t.title));
    lines.push(t.columns.map((c) => csvCell(c.label)).join(','));
    t.rows.forEach((r) => lines.push(t.columns.map((c) => csvCell(c.value(r))).join(',')));
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${name}-${ymd(new Date())}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const locParam = (f) => (f.location ? { location_id: f.location } : {});
const speciesParam = (f) => (f.species ? { species: f.species } : {});
const rangeStartEnd = (f) => ({ start_date: ymd(f.range.from), end_date: ymd(f.range.to) });
const rangeFromTo = (f) => ({ date_from: ymd(f.range.from), date_to: ymd(f.range.to) });
const optionalRange = (f) => (f.allDates ? {} : rangeFromTo(f));

// ---------------------------------------------------------------- report definitions
// Each run(filters, ctx) resolves to { stats: [{label, value}], tables: [{title, columns, rows, empty}] }.
// columns: { label, value(row) -> string|number, right? } (the same accessor feeds the table and the CSV).
const REPORTS = [
  {
    id: 'daily', group: 'Herd Reports', name: 'Daily Summary', icon: CalendarBlank,
    description: 'Stock held at each location on a single day.',
    filters: ['date', 'location'],
    async run(f, ctx) {
      const { data } = await getDailyReport(ymd(f.date));
      const locName = ctx.locations.find((l) => String(l.id) === String(f.location))?.name;
      const entries = Object.entries(data.stock_by_location || {}).filter(([name]) => !locName || name === locName);
      const rows = entries.map(([name, s]) => ({
        name, cattle: s.cattle || 0, sheep: s.sheep || 0, goat: s.goat || 0,
        total: (s.cattle || 0) + (s.sheep || 0) + (s.goat || 0),
      }));
      const sum = (k) => rows.reduce((a, r) => a + r[k], 0);
      return {
        stats: [
          { label: 'Total stock', value: sum('total') }, { label: 'Cattle', value: sum('cattle') },
          { label: 'Sheep', value: sum('sheep') }, { label: 'Goats', value: sum('goat') },
        ],
        tables: [{
          title: `Stock by location - ${ymd(f.date)}`, empty: 'No stock data for this date.', rows,
          columns: [
            { label: 'Location', value: (r) => r.name }, { label: 'Cattle', right: true, value: (r) => r.cattle },
            { label: 'Sheep', right: true, value: (r) => r.sheep }, { label: 'Goats', right: true, value: (r) => r.goat },
            { label: 'Total', right: true, value: (r) => r.total },
          ],
        }],
      };
    },
  },
  {
    id: 'analytics', group: 'Herd Reports', name: 'Herd Analytics', icon: TrendUp,
    description: 'Calving, weaning and mortality rates plus net change by species.',
    filters: ['location', 'range'],
    async run(f) {
      const { data } = await getAnalyticsReport({ ...rangeStartEnd(f), ...locParam(f) });
      const rates = data.species_rates || [];
      const total = (k) => rates.reduce((a, r) => a + (r[k] || 0), 0);
      return {
        stats: [
          { label: 'Total stock', value: total('total_stock') }, { label: 'Births', value: total('births') },
          { label: 'Sold', value: total('sold') }, { label: 'Bought', value: total('bought') },
          { label: 'Deaths', value: data.death_analysis?.total_deaths ?? 0 },
        ],
        tables: [
          {
            title: 'Rates by species', empty: 'No analytics for this period.', rows: rates,
            columns: [
              { label: 'Species', value: (r) => speciesName(r.species) },
              { label: 'Stock', right: true, value: (r) => r.total_stock },
              { label: 'Breeding females', right: true, value: (r) => r.breeding_females },
              { label: 'Births', right: true, value: (r) => r.births },
              { label: 'Calving %', right: true, value: (r) => r.calving_rate },
              { label: 'Weaning %', right: true, value: (r) => r.weaning_rate },
              { label: 'Mortality %', right: true, value: (r) => r.mortality_rate },
              { label: 'Sold', right: true, value: (r) => r.sold },
              { label: 'Bought', right: true, value: (r) => r.bought },
            ],
          },
          {
            title: 'Net change', empty: 'No movements in this period.', rows: data.net_changes || [],
            columns: [
              { label: 'Species', value: (r) => speciesName(r.species) },
              { label: 'Births', right: true, value: (r) => r.births }, { label: 'Bought', right: true, value: (r) => r.bought },
              { label: 'Deaths', right: true, value: (r) => r.deaths }, { label: 'Sold', right: true, value: (r) => r.sold },
              { label: 'Net change', right: true, value: (r) => r.net_change },
            ],
          },
        ],
      };
    },
  },
  {
    id: 'detailed', group: 'Herd Reports', name: 'Detailed Event Log', icon: ListBullets,
    description: 'Opening and closing balances with every event in the range.',
    filters: ['location', 'range'],
    async run(f) {
      const { data } = await getDetailedReport({ ...rangeStartEnd(f), ...locParam(f) });
      const events = data.events || [];
      const balanceCols = [
        { label: 'Location', value: (r) => r.location_name }, { label: 'Cattle', right: true, value: (r) => r.cattle },
        { label: 'Sheep', right: true, value: (r) => r.sheep }, { label: 'Goats', right: true, value: (r) => r.goat },
        { label: 'Total', right: true, value: (r) => r.total },
      ];
      return {
        stats: [
          { label: 'Events', value: events.length },
          { label: 'Animals affected', value: events.reduce((a, e) => a + (e.count || 0), 0) },
        ],
        tables: [
          { title: 'Opening balances', empty: 'No opening balances.', rows: data.opening_totals || [], columns: balanceCols },
          { title: 'Closing balances', empty: 'No closing balances.', rows: data.closing_totals || [], columns: balanceCols },
          {
            title: 'Events', empty: 'No events recorded in this period.', rows: events,
            columns: [
              { label: 'Date', value: (r) => day(r.log_date) },
              { label: 'Type', value: (r) => EVENT_TYPES[r.event_type]?.label || pretty(r.event_type) },
              { label: 'Location', value: (r) => dash(r.location_name) },
              { label: 'Species', value: (r) => speciesName(r.species) },
              { label: 'Category', value: (r) => dash(r.category_name_sw) },
              { label: 'Count', right: true, value: (r) => r.count },
              { label: 'Movement', value: (r) => (r.from_location_name || r.to_location_name
                ? `${r.from_location_name || '?'} → ${r.to_location_name || '?'}`
                : (r.from_category_name_sw || r.to_category_name_sw ? `${r.from_category_name_sw || '?'} → ${r.to_category_name_sw || '?'}` : '')) },
              { label: 'Notes', value: (r) => dash(r.notes) },
            ],
          },
        ],
      };
    },
  },
  {
    id: 'range', group: 'Herd Reports', name: 'Date Range Report', icon: ClipboardText,
    description: 'Event counts by type across a date range.',
    filters: ['location', 'range'],
    async run(f) {
      const { data } = await getRangeReport({ ...rangeStartEnd(f), ...locParam(f) });
      const rows = Object.entries(data.events_by_type || {}).map(([type, v]) => ({ type, count: v.count, animals: v.total_animals }));
      return {
        stats: [
          { label: 'Events', value: rows.reduce((a, r) => a + (r.count || 0), 0) },
          { label: 'Animals affected', value: rows.reduce((a, r) => a + (r.animals || 0), 0) },
        ],
        tables: [{
          title: 'Events by type', empty: 'No events in this period.', rows,
          columns: [
            { label: 'Event type', value: (r) => EVENT_TYPES[r.type]?.label || pretty(r.type) },
            { label: 'Events', right: true, value: (r) => r.count }, { label: 'Animals', right: true, value: (r) => r.animals },
          ],
        }],
      };
    },
  },
  {
    id: 'calving', group: 'Breeding Reports', name: 'Calving Report', icon: Baby,
    description: 'Calvings with outcome, interval and calf details.',
    filters: ['location', 'species', 'range', 'allDates'],
    async run(f) {
      const { data } = await getCalvingReport({ ...locParam(f), ...speciesParam(f), ...optionalRange(f) });
      const s = data.summary;
      return {
        stats: [
          { label: 'Calvings', value: s.total }, { label: 'Live', value: s.live },
          { label: 'Stillbirths', value: s.stillbirths }, { label: 'Assisted', value: s.assisted },
        ],
        tables: [{
          title: 'Calvings', empty: 'No calvings found for these filters.', rows: data.rows,
          columns: [
            { label: 'Date', value: (r) => day(r.calved_date) },
            { label: 'Dam', value: (r) => animalText(r.dam_tag, r.dam_tags) },
            { label: 'Location', value: (r) => dash(r.location_name) },
            { label: 'Species', value: (r) => speciesName(r.species) },
            { label: 'Outcome', value: (r) => pretty(r.calving_outcome) },
            { label: 'Interval (days)', right: true, value: (r) => dash(r.calving_interval_days) },
            { label: 'Calf', value: (r) => (r.calf_tag ? animalText(r.calf_tag, r.calf_tags) : '—') },
            { label: 'Calf sex', value: (r) => pretty(r.calf_sex) },
            { label: 'Calf status', value: (r) => pretty(r.calf_status) },
          ],
        }],
      };
    },
  },
  {
    id: 'repro', group: 'Breeding Reports', name: 'Reproductive Status', icon: Heartbeat,
    description: 'Current cycle status of every breeding female.',
    filters: ['location', 'species', 'statuses'],
    async run(f) {
      const { data } = await getReproductiveStatusReport({
        ...locParam(f), ...speciesParam(f), ...(f.statuses.length ? { status: f.statuses.join(',') } : {}),
      });
      return {
        stats: [
          { label: 'Females', value: data.summary.total },
          ...[...CYCLE_STATUSES, 'unknown'].map((k) => ({ label: pretty(k), value: data.summary.by_status[k] ?? 0 })),
        ],
        tables: [{
          title: 'Breeding females', empty: 'No females found for these filters.', rows: data.rows,
          columns: [
            { label: 'Animal', value: (r) => animalText(r.tag_number, r.tags) },
            { label: 'Location', value: (r) => dash(r.location_name) },
            { label: 'Species', value: (r) => speciesName(r.species) },
            { label: 'Cycle status', value: (r) => pretty(r.cycle_status) },
            { label: 'Last calving', value: (r) => day(r.last_calving_date) },
            { label: 'Interval (days)', right: true, value: (r) => dash(r.calving_interval_days) },
            { label: 'Calvings', right: true, value: (r) => dash(r.lifetime_calvings) },
            { label: 'Months pregnant', right: true, value: (r) => dash(r.months_pregnant) },
            { label: 'Last PD', value: (r) => day(r.last_pd_date) },
            { label: 'Expected calving', value: (r) => day(r.expected_calving_date) },
          ],
        }],
      };
    },
  },
  {
    id: 'abortions', group: 'Breeding Reports', name: 'Abortion Log', icon: Warning,
    description: 'Recorded abortions by stage and animal.',
    filters: ['location', 'species', 'range', 'allDates'],
    async run(f) {
      const { data } = await getAbortionsReport({ ...locParam(f), ...speciesParam(f), ...optionalRange(f) });
      return {
        stats: [
          { label: 'Abortions', value: data.summary.total },
          ...Object.entries(data.summary.by_stage).map(([k, v]) => ({ label: `${pretty(k)} stage`, value: v })),
        ],
        tables: [{
          title: 'Abortions (dates are when the cycle was recorded)', empty: 'No abortions found for these filters.', rows: data.rows,
          columns: [
            { label: 'Recorded', value: (r) => day(r.abortion_date) },
            { label: 'Animal', value: (r) => animalText(r.tag_number, r.tags) },
            { label: 'Location', value: (r) => dash(r.location_name) },
            { label: 'Species', value: (r) => speciesName(r.species) },
            { label: 'Stage', value: (r) => pretty(r.abortion_stage) },
            { label: 'Cycle #', right: true, value: (r) => r.cycle_number },
            { label: 'Notes', value: (r) => dash(r.notes) },
          ],
        }],
      };
    },
  },
  {
    id: 'upcoming', group: 'Health Reports', name: 'Upcoming Treatments', icon: CalendarCheck,
    description: 'Vaccinations and treatments falling due soon.',
    filters: ['location', 'species', 'horizon'],
    async run(f) {
      const { data } = await getUpcomingHealthEvents({ days: f.horizon, ...locParam(f) });
      const rows = f.species ? data.filter((e) => e.species === f.species) : data;
      return { ...healthResult(rows, 'Due', 'No treatments due in this window.', (r) => day(r.next_due_date)) };
    },
  },
  {
    id: 'history', group: 'Health Reports', name: 'Treatment History', icon: Syringe,
    description: 'Past vaccinations, dosing and treatments in a date range.',
    filters: ['location', 'species', 'range'],
    async run(f) {
      const { data } = await getFarmHealthEvents({ ...rangeFromTo(f), ...locParam(f), ...speciesParam(f), limit: 500 });
      return { ...healthResult(data, 'Next due', 'No treatments recorded in this period.', (r) => day(r.next_due_date)) };
    },
  },
  {
    id: 'sales', group: 'Sales & Financial', name: 'Sales Report', icon: CurrencyCircleDollar,
    description: 'Revenue, head sold and every sale line item.',
    filters: ['location', 'species', 'range'],
    async run(f) {
      const { data } = await getSalesReport({ ...locParam(f), ...speciesParam(f), ...rangeFromTo(f) });
      return {
        stats: [
          { label: 'Total revenue', value: money(data.summary.total_revenue) },
          { label: 'Head sold', value: data.summary.total_head },
          { label: 'Avg price / head', value: money(data.summary.avg_price_per_head) },
        ],
        tables: [
          {
            title: 'By month', empty: 'No sales in this period.', rows: data.by_period,
            columns: [
              { label: 'Month', value: (r) => r.month }, { label: 'Head', right: true, value: (r) => r.head_count },
              { label: 'Revenue', right: true, value: (r) => money(r.revenue) },
            ],
          },
          {
            title: 'Line items', empty: 'No sales in this period.', rows: data.line_items,
            columns: [
              { label: 'Date', value: (r) => day(r.date) }, { label: 'Farm', value: (r) => r.farm },
              { label: 'Species', value: (r) => speciesName(r.species) }, { label: 'Category', value: (r) => dash(r.category) },
              { label: 'Qty', right: true, value: (r) => r.qty }, { label: 'Price / head', right: true, value: (r) => money(r.price_per_head) },
              { label: 'Total', right: true, value: (r) => money(r.total_price) }, { label: 'Customer', value: (r) => dash(r.customer_name) },
            ],
          },
        ],
      };
    },
  },
  {
    id: 'mortality', group: 'Mortality', name: 'Mortality Report', icon: Skull,
    description: 'Deaths, mortality rates against thresholds, and causes.',
    filters: ['location', 'species', 'range'],
    async run(f) {
      const { data } = await getMortalityReport({ ...locParam(f), ...speciesParam(f), ...rangeFromTo(f) });
      const status = (r) => (r.is_alert ? 'Alert' : 'OK');
      const rateCols = (first) => [
        first,
        { label: 'Deaths', right: true, value: (r) => r.deaths },
        { label: 'Rate', right: true, value: (r) => pct(r.mortality_rate_pct) },
        { label: 'Threshold', right: true, value: (r) => pct(r.threshold_pct) },
        { label: 'Status', value: status },
      ];
      return {
        stats: [
          { label: 'Total deaths', value: data.summary.total_deaths },
          { label: 'Above threshold', value: data.flagged.length },
        ],
        tables: [
          {
            title: 'By species', empty: 'No stock or deaths for these filters.',
            rows: data.by_species.filter((r) => r.avg_stock > 0 || r.deaths > 0),
            columns: rateCols({ label: 'Species', value: (r) => speciesName(r.species) }),
          },
          {
            title: 'By farm', empty: 'No farms to compare.', rows: data.by_farm,
            columns: [
              ...rateCols({ label: 'Farm', value: (r) => r.farm }).slice(0, 1),
              { label: 'Species', value: (r) => speciesName(r.species) },
              ...rateCols({}).slice(1),
            ],
          },
          {
            title: 'By cause', empty: 'No deaths with a recorded cause.', rows: data.by_cause.filter((r) => r.cause_name != null),
            columns: [
              { label: 'Cause of death', value: (r) => r.cause_name }, { label: 'Deaths', right: true, value: (r) => r.count },
              { label: '% of deaths', right: true, value: (r) => `${r.pct_of_total}%` },
            ],
          },
        ],
      };
    },
  },
];

function healthResult(rows, dueLabel, empty, dueValue) {
  const today = ymd(new Date());
  return {
    stats: [
      { label: 'Events', value: rows.length },
      { label: 'Overdue', value: rows.filter((r) => r.next_due_date && day(r.next_due_date) < today).length },
      { label: 'Total cost', value: money(rows.reduce((a, r) => a + (Number(r.total_cost) || 0), 0)) },
    ],
    tables: [{
      title: 'Health events', empty, rows,
      columns: [
        { label: 'Date', value: (r) => day(r.event_date) },
        { label: 'Location', value: (r) => dash(r.location_name) },
        { label: 'Type', value: (r) => pretty(r.event_type) },
        { label: 'Species', value: (r) => (r.species ? speciesName(r.species) : 'All') },
        { label: 'Product', value: (r) => dash(r.vaccine_type_name || r.product_name) },
        { label: 'Head', right: true, value: (r) => dash(r.head_count) },
        { label: 'Cost', right: true, value: (r) => money(r.total_cost) },
        { label: dueLabel, value: dueValue },
        { label: 'Notes', value: (r) => dash(r.notes) },
      ],
    }],
  };
}

const GROUPS = ['Herd Reports', 'Breeding Reports', 'Health Reports', 'Sales & Financial', 'Mortality'];

// ---------------------------------------------------------------- UI pieces
const selectCls = 'mt-1 block w-44 rounded-md border bg-background p-2 text-sm text-foreground';

function ReportCard({ report, active, onSelect }) {
  const Icon = report.icon;
  return (
    <button
      type="button" onClick={() => onSelect(report.id)} aria-pressed={active}
      data-testid={`report-card-${report.id}`}
      className={`flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:border-[#2D5A27]/60 hover:bg-[#2D5A27]/5 ${
        active ? 'border-[#2D5A27] bg-[#2D5A27]/10 ring-1 ring-[#2D5A27]' : 'border-border/60 bg-card'}`}
    >
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[#2D5A27]/10 text-[#2D5A27]">
        <Icon className="h-5 w-5" weight="duotone" />
      </span>
      <span className="min-w-0">
        <span className="block font-heading text-sm font-semibold">{report.name}</span>
        <span className="block text-xs text-muted-foreground">{report.description}</span>
      </span>
    </button>
  );
}

function FilterBar({ report, filters, setFilters, locations }) {
  const set = (patch) => setFilters({ ...filters, ...patch });
  const has = (k) => report.filters.includes(k);
  return (
    <div className="flex flex-wrap items-end gap-4">
      {has('location') && (
        <label className="text-xs text-muted-foreground">Location
          <select value={filters.location} onChange={(e) => set({ location: e.target.value })} className={selectCls}>
            <option value="">All locations</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
      )}
      {has('species') && (
        <label className="text-xs text-muted-foreground">Species
          <select value={filters.species} onChange={(e) => set({ species: e.target.value })} className={selectCls}>
            <option value="">All species</option>
            {Object.entries(SPECIES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
      )}
      {has('horizon') && (
        <label className="text-xs text-muted-foreground">Due within
          <select value={filters.horizon} onChange={(e) => set({ horizon: Number(e.target.value) })} className={selectCls}>
            {[14, 30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
      )}
      {has('date') && (
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground">Date</span>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="flex gap-2" data-testid="report-date-picker">
                <CalendarBlank className="h-4 w-4" />{format(filters.date, 'PPP')}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar mode="single" selected={filters.date} onSelect={(d) => { if (d) set({ date: d }); }} />
            </PopoverContent>
          </Popover>
        </div>
      )}
      {has('range') && (
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground">Date range</span>
          <div className="flex items-center gap-3">
            <DateRangePicker
              value={filters.range}
              onChange={(range) => { if (range?.from && range?.to) set({ range }); }}
            />
            {has('allDates') && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={filters.allDates} onChange={(e) => set({ allDates: e.target.checked })} />
                All dates
              </label>
            )}
          </div>
        </div>
      )}
      {has('statuses') && (
        <fieldset className="space-y-1">
          <legend className="text-xs text-muted-foreground">Latest cycle status</legend>
          <div className="flex flex-wrap gap-3">
            {CYCLE_STATUSES.map((s) => (
              <label key={s} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox" checked={filters.statuses.includes(s)}
                  onChange={() => set({ statuses: filters.statuses.includes(s) ? filters.statuses.filter((x) => x !== s) : [...filters.statuses, s] })}
                />
                {pretty(s)}
              </label>
            ))}
          </div>
        </fieldset>
      )}
    </div>
  );
}

function ResultTable({ table }) {
  return (
    <div>
      {table.title && <h4 className="mb-2 font-heading text-sm font-semibold">{table.title}</h4>}
      <div className="overflow-x-auto rounded-lg border border-border/60">
        <Table>
          <TableHeader>
            <TableRow>
              {table.columns.map((c) => <TableHead key={c.label} className={c.right ? 'text-right' : ''}>{c.label}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {table.rows.map((row, i) => (
              <TableRow key={i}>
                {table.columns.map((c) => <TableCell key={c.label} className={c.right ? 'text-right' : ''}>{c.value(row)}</TableCell>)}
              </TableRow>
            ))}
            {!table.rows.length && (
              <TableRow><TableCell colSpan={table.columns.length} className="p-6 text-center text-muted-foreground">{table.empty}</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function hasData(result) {
  return result.tables.some((t) => t.rows.length > 0);
}

function DetailPanel({ report, locations }) {
  const [filters, setFilters] = useState(() => ({
    location: '', species: '', date: new Date(), horizon: 30, allDates: false, statuses: [],
    range: { from: subDays(new Date(), 30), to: new Date() },
  }));
  const [state, setState] = useState({ status: 'idle', result: null, error: '' });
  const runId = useRef(0);

  // A different report starts from a clean results area (filters are kept so they carry across reports).
  useEffect(() => { runId.current += 1; setState({ status: 'idle', result: null, error: '' }); }, [report.id]);

  async function run() {
    const id = ++runId.current;
    setState({ status: 'loading', result: null, error: '' });
    try {
      const result = await report.run(filters, { locations });
      if (id === runId.current) setState({ status: 'done', result, error: '' });
    } catch (error) {
      if (id !== runId.current) return;
      const message = errorText(error);
      setState({ status: 'error', result: null, error: message });
      toast.error(`Failed to load ${report.name.toLowerCase()}`);
    }
  }

  const Icon = report.icon;
  const { status, result } = state;
  return (
    <Card className="border-border/60" data-testid="report-detail-panel">
      <CardContent className="space-y-5 p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[#2D5A27] text-white">
            <Icon className="h-5 w-5" weight="fill" />
          </span>
          <div>
            <h2 className="font-heading text-xl font-bold">{report.name}</h2>
            <p className="text-sm text-muted-foreground">{report.description}</p>
          </div>
        </div>

        <FilterBar report={report} filters={filters} setFilters={setFilters} locations={locations} />

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={run} disabled={status === 'loading'} className="gap-2 bg-[#2D5A27] hover:bg-[#244a1f]" data-testid="run-report-btn">
            <MagnifyingGlass className="h-4 w-4" />Run Report
          </Button>
          <Button
            variant="outline" className="gap-2" data-testid="export-csv-btn"
            disabled={status !== 'done' || !hasData(result)}
            onClick={() => downloadCsv(report.id, result)}
          >
            <Download className="h-4 w-4" />Export CSV
          </Button>
        </div>

        <div className="border-t pt-5" aria-live="polite">
          {status === 'idle' && (
            <div className="py-10 text-center text-muted-foreground">
              <ChartBar className="mx-auto mb-3 h-10 w-10 opacity-50" />
              <p>Set your filters and choose Run Report.</p>
            </div>
          )}
          {status === 'loading' && (
            <div className="space-y-3" role="status" aria-label="Loading report">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>
              <Skeleton className="h-48" />
            </div>
          )}
          {status === 'error' && (
            <div role="alert" className="rounded-lg bg-red-50 p-4 text-red-800">
              {state.error} <Button variant="outline" size="sm" onClick={run}>Retry</Button>
            </div>
          )}
          {status === 'done' && (
            <div className="space-y-5">
              {result.stats.length > 0 && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
                  {result.stats.map((s) => (
                    <div key={s.label} className="rounded-lg border border-border/60 bg-muted/30 p-3">
                      <p className="text-xs text-muted-foreground">{s.label}</p>
                      <p className="mt-1 font-heading text-xl font-bold text-[#2D5A27]">{s.value}</p>
                    </div>
                  ))}
                </div>
              )}
              {!hasData(result) && (
                <div className="py-6 text-center text-muted-foreground" data-testid="report-empty">
                  <FirstAid className="mx-auto mb-2 h-8 w-8 opacity-50" />
                  <p>No results for these filters.</p>
                </div>
              )}
              {result.tables.map((t) => <ResultTable key={t.title} table={t} />)}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- page
function Reports() {
  const [locations, setLocations] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const panelRef = useRef(null);

  useEffect(() => {
    getLocations()
      .then((response) => setLocations(response.data))
      .catch(() => toast.error('Failed to load locations'));
  }, []);

  function select(id) {
    setSelectedId(id);
    // On single-column (mobile) layouts the panel sits below the catalog: bring it into view.
    if (window.matchMedia && !window.matchMedia('(min-width: 1024px)').matches) {
      setTimeout(() => panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    }
  }

  const selected = REPORTS.find((r) => r.id === selectedId);

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div>
        <h1 className="font-heading text-3xl font-bold">Reports & Analytics</h1>
        <p className="mt-1 text-muted-foreground">Pick a report, set its filters and run it.</p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="space-y-6" data-testid="report-catalog">
          {GROUPS.map((group) => (
            <section key={group} aria-label={group}>
              <h3 className="mb-2 font-heading text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group}</h3>
              <div className="grid gap-2">
                {REPORTS.filter((r) => r.group === group).map((r) => (
                  <ReportCard key={r.id} report={r} active={r.id === selectedId} onSelect={select} />
                ))}
              </div>
            </section>
          ))}
        </div>

        <div ref={panelRef} className="scroll-mt-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto">
          {selected ? (
            <DetailPanel report={selected} locations={locations} />
          ) : (
            <Card className="border-dashed border-border/80" data-testid="report-empty-prompt">
              <CardContent className="py-16 text-center text-muted-foreground">
                <Clock className="mx-auto mb-3 h-10 w-10 opacity-50" />
                <p className="font-heading font-semibold text-foreground">No report selected</p>
                <p className="text-sm">Choose a report card to set filters and run it.</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default Reports;
