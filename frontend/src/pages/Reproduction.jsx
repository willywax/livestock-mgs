import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { addDays, differenceInCalendarDays, format, startOfDay } from 'date-fns';
import DateRangePicker, { yearToDateRange } from '../components/DateRangePicker';
import { toast } from 'sonner';
import { CaretDown, CaretRight, Pencil, Plus } from '@phosphor-icons/react';
import { useAuth } from '../context/AuthContext';
import {
  getLocations, getAnimals, getOpeningBalances, getStockLevels, getReproductionAnalytics,
  getReproductiveCycles, getBullAssignments, createBullAssignment, updateBullAssignment,
} from '../lib/api';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Skeleton } from '../components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../components/ui/collapsible';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import {
  AnimalSelect, DateField, INTERVAL_THRESHOLDS, RecordBCSDialog, RecordCalvingDialog, RecordPDDialog,
  RecordServiceDialog, SPECIES_TERMS, SpeciesPills, getTerms, intervalTone, parseDate, toISODate,
} from '../components/ReproductionDialogs';
import { cn } from '../lib/utils';

const MAX_ATTENTION_ROWS = 20;
const SPECIES_ORDER = ['cattle', 'sheep', 'goat'];
const SPECIES_LABEL = { cattle: 'Cattle', sheep: 'Sheep', goat: 'Goats' };
// Offspring tags typed in the calving dialog but not matching an animal are stored in notes.
const OFFSPRING_TAG_RE = new RegExp(
  `(?:${Object.values(SPECIES_TERMS).map((t) => t.offspring).join('|')}) tag: (\\S+)`
);

const TONE_TEXT = {
  green: 'text-green-700', amber: 'text-amber-600', red: 'text-red-600', grey: 'text-muted-foreground',
};
const TONE_PILL = {
  green: 'bg-green-100 text-green-700',
  amber: 'bg-amber-100 text-amber-700',
  red: 'bg-red-100 text-red-700',
  orange: 'bg-orange-100 text-orange-700',
  grey: 'bg-gray-100 text-gray-600',
};

const fmt = (s) => (s ? format(parseDate(s), 'dd MMM yyyy') : '—');

function Pill({ tone, title, children }) {
  return (
    <span title={title} className={cn('px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap', TONE_PILL[tone])}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// KPI maths. For "All species" the numbers come from /analytics/reproduction.
// For a single species the same definitions are computed here (the endpoint has
// no species filter), see docs/decisions/0008 and ROADMAP.
// ---------------------------------------------------------------------------
function kooCountFrom(kooData, start) {
  if (!kooData) return 0;
  const latest = new Map();
  kooData.balances
    .filter((b) => b.category_name_sw === 'Koo' && parseDate(b.period_start) <= start)
    .forEach((b) => {
      const key = `${b.location_id}|${b.species}|${b.category_id}`;
      const prev = latest.get(key);
      if (!prev || b.period_start > prev.period_start) latest.set(key, b);
    });
  if (latest.size) return [...latest.values()].reduce((sum, b) => sum + b.count, 0);
  return kooData.stock
    .filter((s) => s.category_name_sw === 'Koo')
    .reduce((sum, s) => sum + s.current_count, 0);
}

function computeMetrics({ cycles, animals, start, end, kooCount }) {
  const inYear = (s) => {
    if (!s) return false;
    const d = parseDate(s);
    return d >= start && d <= end;
  };
  const calved = cycles.filter((c) => inYear(c.actual_calving_date));
  const live = calved.filter((c) => ['live_calf', 'assisted_live'].includes(c.calving_outcome)).length;
  const pdDone = cycles.filter((c) => c.pd_result && inYear(c.pd_check_date));
  const pdPregnant = pdDone.filter((c) => c.pd_result === 'pregnant').length;
  const confirmed = cycles.filter(
    (c) => c.pd_result === 'pregnant' && inYear(c.actual_calving_date || c.pd_check_date || c.service_date)
  );
  const aborted = confirmed.filter((c) => c.status === 'aborted' || c.calving_outcome === 'abortion').length;
  const females = animals.filter((a) => a.status === 'active' && a.sex === 'female');
  const activeIds = new Set(females.map((a) => a.id));
  const pregnantIds = new Set(
    cycles
      .filter((c) => c.pd_result === 'pregnant' && !c.actual_calving_date && c.status !== 'aborted'
        && c.calving_outcome !== 'abortion' && activeIds.has(c.animal_id))
      .map((c) => c.animal_id)
  );
  return {
    koo_count: kooCount,
    live_calvings: live,
    calving_rate: kooCount ? live / kooCount : null,
    conception_rate: pdDone.length ? pdPregnant / pdDone.length : null,
    abortion_rate: confirmed.length ? aborted / confirmed.length : null,
    open_cows: females.filter((a) => a.category_name_sw === 'Koo' && !pregnantIds.has(a.id)).length,
    pregnant_cows: pregnantIds.size,
  };
}

const toneByThreshold = (pct, redBelow, amberBelow) => {
  if (pct === null || pct === undefined) return 'grey';
  if (pct < redBelow) return 'red';
  if (pct < amberBelow) return 'amber';
  return 'green';
};

function KpiCard({ title, value, subtitle, tone = 'grey', testId, children }) {
  return (
    <Card data-testid={testId}>
      <CardContent className="p-4">
        <p className="text-sm text-muted-foreground">{title}</p>
        {children || (
          <>
            <p className={cn('text-3xl font-heading font-bold mt-1', TONE_TEXT[tone])}>{value}</p>
            <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Bull assignment dialog (admin)
// ---------------------------------------------------------------------------
function BullDialog({ state, onClose, onSaved, males, locations, defaultLocationId, terms }) {
  const editing = state?.mode === 'edit';
  const assignment = state?.assignment;
  const [bull, setBull] = useState(null);
  const [locationId, setLocationId] = useState('');
  const [assignedDate, setAssignedDate] = useState(new Date());
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!state) return;
    if (state.mode === 'edit') {
      setBull(null);
      setLocationId(String(state.assignment.location_id));
      setAssignedDate(parseDate(state.assignment.assigned_date));
      setNotes(state.assignment.notes || '');
    } else {
      setBull(null);
      setLocationId(defaultLocationId ? String(defaultLocationId) : '');
      setAssignedDate(new Date());
      setNotes('');
    }
  }, [state, defaultLocationId]);

  const save = async (extra = {}) => {
    setSaving(true);
    try {
      if (editing) {
        await updateBullAssignment(assignment.id, {
          location_id: Number(locationId),
          assigned_date: toISODate(assignedDate),
          notes: notes.trim() || null,
          ...extra,
        });
        toast.success(extra.removed_date ? `${terms.male} removed` : 'Assignment updated');
      } else {
        await createBullAssignment({
          bull_animal_id: bull.id,
          location_id: Number(locationId),
          assigned_date: toISODate(assignedDate),
          notes: notes.trim() || null,
        });
        toast.success(`${terms.male} assigned`);
      }
      onSaved();
      onClose();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to save assignment');
    } finally {
      setSaving(false);
    }
  };

  const canSave = !!locationId && !!assignedDate && (editing || !!bull);
  return (
    <Dialog open={!!state} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="bull-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">
            {editing ? `Edit ${terms.male.toLowerCase()} assignment` : `Assign ${terms.male.toLowerCase()}`}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {editing ? (
            <div className="space-y-1">
              <Label>{terms.male}</Label>
              <p className="text-sm font-medium">
                {assignment.bull_tag_number}{assignment.bull_name ? ` · ${assignment.bull_name}` : ''}
              </p>
            </div>
          ) : (
            <AnimalSelect animals={males} value={bull?.id} onChange={setBull} label={terms.male} testId="bull-animal" />
          )}
          <div className="space-y-2">
            <Label>Farm</Label>
            <Select value={locationId || undefined} onValueChange={setLocationId}>
              <SelectTrigger data-testid="bull-location"><SelectValue placeholder="Select farm" /></SelectTrigger>
              <SelectContent>
                {locations.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Assigned date</Label>
            <DateField value={assignedDate} onChange={setAssignedDate} testId="bull-date" />
          </div>
          <div className="space-y-2">
            <Label>Notes (optional)</Label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </div>
        </div>
        <DialogFooter className="gap-2">
          {editing && (
            <Button
              type="button" variant="outline" disabled={saving}
              onClick={() => save({ removed_date: toISODate(new Date()) })}
              data-testid="bull-remove"
            >
              Remove today
            </Button>
          )}
          <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="button" onClick={() => save()} disabled={saving || !canSave} data-testid="bull-save">
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
function Reproduction() {
  const { isAdmin, isDataEntry } = useAuth();
  const [locations, setLocations] = useState([]);
  const [animals, setAnimals] = useState([]);
  const [cycles, setCycles] = useState([]);
  const [bulls, setBulls] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [kooData, setKooData] = useState(null);
  const [loading, setLoading] = useState(true);

  const [locationId, setLocationId] = useState('all');
  const [range, setRange] = useState(yearToDateRange);
  const start = startOfDay(range.from);
  const end = startOfDay(range.to);
  const dateFrom = format(range.from, 'yyyy-MM-dd');
  const dateTo = format(range.to, 'yyyy-MM-dd');
  const [species, setSpecies] = useState('all');
  const [showAll, setShowAll] = useState(false);
  const [bullsOpen, setBullsOpen] = useState(false);
  const [dialog, setDialog] = useState({ type: null });
  const [bullState, setBullState] = useState(null);

  const locationParam = locationId === 'all' ? undefined : Number(locationId);
  const terms = getTerms(species === 'all' ? null : species);
  const today = startOfDay(new Date());

  useEffect(() => {
    getLocations()
      .then((res) => setLocations(res.data.filter((l) => l.is_active)))
      .catch(() => toast.error('Failed to load farms'));
    getAnimals()
      .then((res) => setAnimals(res.data))
      .catch(() => toast.error('Failed to load animals'));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cycleRes, bullRes, analyticsRes] = await Promise.all([
        getReproductiveCycles({ location_id: locationParam }),
        getBullAssignments({ active_only: true, location_id: locationParam }),
        getReproductionAnalytics(locationParam, { date_from: dateFrom, date_to: dateTo }),
      ]);
      setCycles(cycleRes.data);
      setBulls(bullRes.data);
      setAnalytics(analyticsRes.data);
    } catch (err) {
      toast.error('Failed to load reproduction data');
    } finally {
      setLoading(false);
    }
  }, [locationParam, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (species === 'all') { setKooData(null); return undefined; }
    let live = true;
    const params = { species, location_id: locationParam };
    Promise.all([getOpeningBalances(params), getStockLevels(params)])
      .then(([ob, sl]) => { if (live) setKooData({ balances: ob.data, stock: sl.data }); })
      .catch(() => toast.error('Failed to load Koo counts'));
    return () => { live = false; };
  }, [species, locationParam]);

  const animalById = useMemo(() => new Map(animals.map((a) => [a.id, a])), [animals]);
  const speciesOf = useCallback((c) => animalById.get(c.animal_id)?.species, [animalById]);
  const scoped = useMemo(
    () => cycles.filter((c) => species === 'all' || speciesOf(c) === species),
    [cycles, species, speciesOf]
  );

  // ----- KPIs -----
  const metrics = useMemo(() => {
    if (species === 'all') return analytics;
    const pool = animals.filter(
      (a) => a.species === species && (!locationParam || a.location_id === locationParam)
    );
    return computeMetrics({ cycles: scoped, animals: pool, start: startOfDay(range.from), end: startOfDay(range.to), kooCount: kooCountFrom(kooData, startOfDay(range.from)) });
  }, [species, analytics, animals, scoped, range, kooData, locationParam]);

  const intervalRows = useMemo(() => {
    const from = startOfDay(range.from);
    const to = startOfDay(range.to);
    const bySpecies = {};
    scoped.forEach((c) => {
      if (c.calving_interval_days === null || c.calving_interval_days === undefined || !c.actual_calving_date) return;
      const d = parseDate(c.actual_calving_date);
      if (d < from || d > to) return;
      const sp = speciesOf(c);
      if (!sp) return;
      bySpecies[sp] = bySpecies[sp] || { days: [], animals: new Set() };
      bySpecies[sp].days.push(c.calving_interval_days);
      bySpecies[sp].animals.add(c.animal_id);
    });
    return SPECIES_ORDER.filter((sp) => bySpecies[sp]).map((sp) => ({
      species: sp,
      enough: bySpecies[sp].animals.size >= 2, // average needs at least 2 animals with 2+ calvings
      avg: Math.round(bySpecies[sp].days.reduce((a, b) => a + b, 0) / bySpecies[sp].days.length),
    }));
  }, [scoped, range, speciesOf]);

  const servedCount = scoped.filter((c) => c.status === 'served').length;
  const rate = (v) => (v === null || v === undefined ? null : Math.round(v * 1000) / 10);
  const calvingPct = rate(metrics?.calving_rate);
  const conceptionPct = rate(metrics?.conception_rate);
  const openShare = metrics && metrics.open_cows + metrics.pregnant_cows > 0
    ? (metrics.open_cows / (metrics.open_cows + metrics.pregnant_cows)) * 100
    : null;
  const openTone = openShare === null ? 'grey' : openShare > 15 ? 'red' : openShare >= 10 ? 'amber' : 'green';

  // ----- Needs attention -----
  const attention = useMemo(() => {
    const items = [];
    scoped.forEach((c) => {
      if (c.status === 'pregnant' && c.expected_calving_date) {
        const exp = parseDate(c.expected_calving_date);
        if (exp < today) items.push({ kind: 'overdue', cycle: c, days: differenceInCalendarDays(today, exp) });
        else if (differenceInCalendarDays(exp, today) <= 14) {
          items.push({ kind: 'due', cycle: c, days: differenceInCalendarDays(exp, today) });
        }
      }
      if (c.status === 'served' && !c.pd_check_date && c.service_date) {
        const since = differenceInCalendarDays(today, parseDate(c.service_date));
        if (since > 60) items.push({ kind: 'pd', cycle: c, days: since });
      }
    });
    const byAnimal = new Map();
    scoped.forEach((c) => byAnimal.set(c.animal_id, [...(byAnimal.get(c.animal_id) || []), c]));
    byAnimal.forEach((list) => {
      const latest = list.reduce((a, b) => (b.cycle_number > a.cycle_number ? b : a));
      if (!['open', 'calved', 'aborted'].includes(latest.status)) return;
      const calvings = list.filter((c) => c.actual_calving_date && c.calving_outcome !== 'abortion');
      if (!calvings.length) return;
      const last = calvings.map((c) => c.actual_calving_date).sort().pop();
      const since = differenceInCalendarDays(today, parseDate(last));
      if (since > 90) items.push({ kind: 'open', cycle: latest, days: since, lastDate: last });
    });
    const rank = { overdue: 0, due: 1, pd: 2, open: 3 };
    return items.sort((a, b) => rank[a.kind] - rank[b.kind]
      || (a.kind === 'due' ? a.days - b.days : b.days - a.days));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scoped]);

  const upcoming = useMemo(() => scoped
    .filter((c) => c.status === 'pregnant' && c.expected_calving_date)
    .filter((c) => {
      const left = differenceInCalendarDays(parseDate(c.expected_calving_date), today);
      return left >= 0 && left <= 30;
    })
    .sort((a, b) => a.expected_calving_date.localeCompare(b.expected_calving_date)),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [scoped]);

  const recent = useMemo(() => {
    const cutoff = addDays(today, -60);
    return scoped
      .filter((c) => ['calved', 'aborted'].includes(c.status) && c.actual_calving_date)
      .filter((c) => parseDate(c.actual_calving_date) >= cutoff)
      .sort((a, b) => b.actual_calving_date.localeCompare(a.actual_calving_date));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scoped]);

  const visibleBulls = bulls.filter((b) => species === 'all' || animalById.get(b.bull_animal_id)?.species === species);
  const males = useMemo(() => animals.filter((a) => a.sex === 'male' && a.status === 'active'), [animals]);
  const shownAttention = showAll ? attention : attention.slice(0, MAX_ATTENTION_ROWS);

  const closeDialog = () => setDialog({ type: null });
  const termsFor = (c) => getTerms(speciesOf(c));
  const offspringTag = (c) => {
    if (c.calf_animal_id && animalById.get(c.calf_animal_id)) return animalById.get(c.calf_animal_id).tag_number;
    const m = (c.notes || '').match(OFFSPRING_TAG_RE);
    return m ? m[1] : '—';
  };

  const attentionAction = (item) => {
    const t = termsFor(item.cycle);
    if (item.kind === 'overdue' || item.kind === 'due') {
      return { label: `Record ${t.event.toLowerCase()}`, open: { type: 'calving', cycleId: item.cycle.id } };
    }
    if (item.kind === 'pd') return { label: 'Record PD', open: { type: 'pd', cycleId: item.cycle.id } };
    return { label: 'Record service', open: { type: 'service', animalId: item.cycle.animal_id } };
  };

  const attentionBadge = (item) => {
    const t = termsFor(item.cycle);
    switch (item.kind) {
      case 'overdue': return <Pill tone="red" title={`${t.event} overdue`}>Overdue</Pill>;
      case 'due': return <Pill tone="amber" title={`${t.event} due within 14 days`}>Due soon</Pill>;
      case 'pd': return <Pill tone="amber" title="Pregnancy check due">PD check due</Pill>;
      default: return <Pill tone="grey" title={`Open for over 90 days since last ${t.event.toLowerCase()}`}>Long open</Pill>;
    }
  };

  const attentionDetail = (item) => {
    const c = item.cycle;
    if (item.kind === 'overdue') return `Expected ${fmt(c.expected_calving_date)}`;
    if (item.kind === 'due') return `Due ${fmt(c.expected_calving_date)}`;
    if (item.kind === 'pd') return `Served ${fmt(c.service_date)}`;
    return `Last ${termsFor(c).event.toLowerCase()} ${fmt(item.lastDate)}`;
  };

  const attentionDays = (item) => {
    if (item.kind === 'overdue') return `${item.days} d overdue`;
    if (item.kind === 'due') return item.days === 0 ? 'today' : `in ${item.days} d`;
    if (item.kind === 'pd') return `${item.days} d since service`;
    return `${item.days} d open`;
  };

  const outcomeBadge = (c) => {
    const t = termsFor(c);
    const map = {
      live_calf: ['green', `Live ${t.offspring.toLowerCase()}`],
      stillbirth: ['red', 'Stillbirth'],
      abortion: ['amber', 'Abortion'],
      assisted_live: ['orange', 'Assisted — live'],
      assisted_dead: ['orange', 'Assisted — dead'],
    };
    const [tone, label] = map[c.calving_outcome] || ['grey', '—'];
    return <Pill tone={tone}>{label}</Pill>;
  };

  const menuItems = [
    { label: 'Record service', type: 'service' },
    { label: 'Record PD check', type: 'pd' },
    { label: `Record ${terms.event.toLowerCase()}`, type: 'calving' },
    { label: 'Log BCS score', type: 'bcs' },
  ];
  const targetThreshold = species === 'all' ? null : INTERVAL_THRESHOLDS[species];

  return (
    <div className="space-y-6" data-testid="reproduction-page">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <h1 className="font-heading text-3xl font-bold text-primary">Reproduction</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={locationId} onValueChange={setLocationId}>
            <SelectTrigger className="w-40" data-testid="repro-location"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All farms</SelectItem>
              {locations.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <DateRangePicker value={range} onChange={setRange} />          {isDataEntry && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button className="gap-2" data-testid="log-event-btn"><Plus className="h-4 w-4" />Log event</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {menuItems.map((m) => (
                  <DropdownMenuItem key={m.type} onSelect={() => setDialog({ type: m.type })}>{m.label}</DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
      <SpeciesPills value={species} onChange={(v) => { setSpecies(v); setShowAll(false); }} />

      {/* KPI cards */}
      {loading || !metrics ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            testId="kpi-calving-rate" title={`${terms.event} rate`}
            value={calvingPct === null ? '—' : `${calvingPct}%`}
            tone={toneByThreshold(calvingPct, 60, 80)}
            subtitle={`Target: 80% · ${metrics.live_calvings} live ${terms.event.toLowerCase()} from ${metrics.koo_count} Koo`}
          />
          <KpiCard
            testId="kpi-conception-rate" title="Conception rate"
            value={conceptionPct === null ? '—' : `${conceptionPct}%`}
            tone={toneByThreshold(conceptionPct, 50, 75)}
            subtitle="PD checks confirmed pregnant"
          />
          <KpiCard testId="kpi-interval" title={`Avg ${terms.event.toLowerCase()} interval`}>
            {intervalRows.length === 0 ? (
              <>
                <p className="text-3xl font-heading font-bold mt-1 text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-1">Needs 2+ {terms.females.toLowerCase()} with 2+ events</p>
              </>
            ) : (
              <div className="mt-1 space-y-1">
                {intervalRows.map((row) => {
                  const th = INTERVAL_THRESHOLDS[row.species];
                  return (
                    <div key={row.species} className="flex items-baseline justify-between gap-2">
                      <span className="text-xs text-muted-foreground">
                        {intervalRows.length > 1 || species === 'all' ? SPECIES_LABEL[row.species] : ''} &lt;{th.green} d
                      </span>
                      <span className={cn('text-xl font-heading font-bold', TONE_TEXT[row.enough ? intervalTone(row.avg, row.species) : 'grey'])}>
                        {row.enough ? `${row.avg} days` : '—'}
                      </span>
                    </div>
                  );
                })}
                {targetThreshold && <p className="text-xs text-muted-foreground">Target: &lt;{targetThreshold.green} days</p>}
              </div>
            )}
          </KpiCard>
          <KpiCard
            testId="kpi-open" title={`Open ${terms.females.toLowerCase()}`}
            value={metrics.open_cows} tone={openTone}
            subtitle={`${metrics.pregnant_cows} pregnant, ${servedCount} served`}
          />
        </div>
      )}

      {/* Needs attention */}
      <Card data-testid="attention-section">
        <CardContent className="p-4 space-y-3">
          <h2 className="font-heading text-xl font-semibold">Needs attention</h2>
          {loading ? <Skeleton className="h-24" /> : attention.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing needs attention.</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{terms.female} tag</TableHead><TableHead>Farm</TableHead><TableHead>Status</TableHead>
                    <TableHead>Detail</TableHead><TableHead>Days</TableHead>
                    {isDataEntry && <TableHead className="text-right">Action</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shownAttention.map((item) => {
                    const action = attentionAction(item);
                    return (
                      <TableRow key={`${item.kind}-${item.cycle.id}`}>
                        <TableCell className="font-medium">{item.cycle.animal_tag_number}</TableCell>
                        <TableCell>{item.cycle.location_name}</TableCell>
                        <TableCell>{attentionBadge(item)}</TableCell>
                        <TableCell>{attentionDetail(item)}</TableCell>
                        <TableCell>{attentionDays(item)}</TableCell>
                        {isDataEntry && (
                          <TableCell className="text-right">
                            <Button size="sm" variant="outline" onClick={() => setDialog(action.open)}>{action.label}</Button>
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              {attention.length > MAX_ATTENTION_ROWS && (
                <Button variant="link" className="px-0" onClick={() => setShowAll(!showAll)}>
                  {showAll ? 'Show fewer' : `Show all (${attention.length})`}
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upcoming */}
      <Card data-testid="upcoming-section">
        <CardContent className="p-4 space-y-3">
          <h2 className="font-heading text-xl font-semibold">Upcoming (next 30 days)</h2>
          {loading ? <Skeleton className="h-24" /> : upcoming.length === 0 ? (
            <p className="text-sm text-muted-foreground">No upcoming {terms.event.toLowerCase()}s</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead><TableHead>{terms.female} tag</TableHead><TableHead>Farm</TableHead>
                    <TableHead>{terms.male}</TableHead><TableHead>Event</TableHead><TableHead>Cycle #</TableHead>
                    <TableHead>Days remaining</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {upcoming.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell>{fmt(c.expected_calving_date)}</TableCell>
                      <TableCell className="font-medium">{c.animal_tag_number}</TableCell>
                      <TableCell>{c.location_name}</TableCell>
                      <TableCell>{c.bull_tag_number || '—'}</TableCell>
                      <TableCell>{termsFor(c).event}</TableCell>
                      <TableCell>{c.cycle_number}</TableCell>
                      <TableCell>{differenceInCalendarDays(parseDate(c.expected_calving_date), today)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent */}
      <Card data-testid="recent-section">
        <CardContent className="p-4 space-y-3">
          <h2 className="font-heading text-xl font-semibold">Recent (last 60 days)</h2>
          {loading ? <Skeleton className="h-24" /> : recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">No {terms.event.toLowerCase()}s in the last 60 days</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead><TableHead>{terms.female} tag</TableHead><TableHead>Farm</TableHead>
                    <TableHead>Event</TableHead><TableHead>Outcome</TableHead>
                    <TableHead>{terms.offspring} sex</TableHead><TableHead>{terms.offspring} tag</TableHead>
                    <TableHead>Interval</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recent.map((c) => {
                    const sp = speciesOf(c);
                    const tone = intervalTone(c.calving_interval_days, sp);
                    return (
                      <TableRow key={c.id}>
                        <TableCell>{fmt(c.actual_calving_date)}</TableCell>
                        <TableCell className="font-medium">{c.animal_tag_number}</TableCell>
                        <TableCell>{c.location_name}</TableCell>
                        <TableCell>{termsFor(c).event}</TableCell>
                        <TableCell>{outcomeBadge(c)}</TableCell>
                        <TableCell className="capitalize">{c.calf_sex || '—'}</TableCell>
                        <TableCell>{offspringTag(c)}</TableCell>
                        <TableCell>
                          <Pill tone={tone}>
                            {c.calving_interval_days === null || c.calving_interval_days === undefined
                              ? '—' : `${c.calving_interval_days} d`}
                          </Pill>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bull assignments */}
      <Card data-testid="bulls-section">
        <CardContent className="p-4">
          <Collapsible open={bullsOpen} onOpenChange={setBullsOpen}>
            <div className="flex items-center justify-between">
              <CollapsibleTrigger asChild>
                <Button variant="ghost" className="gap-2 px-0 font-heading text-xl font-semibold" data-testid="bulls-toggle">
                  {bullsOpen ? <CaretDown className="h-4 w-4" /> : <CaretRight className="h-4 w-4" />}
                  {terms.male} assignments ({visibleBulls.length})
                </Button>
              </CollapsibleTrigger>
              {isAdmin && (
                <Button size="sm" className="gap-1" onClick={() => setBullState({ mode: 'create' })} data-testid="assign-bull-btn">
                  <Plus className="h-4 w-4" />Assign {terms.male.toLowerCase()}
                </Button>
              )}
            </div>
            <CollapsibleContent className="pt-3">
              {visibleBulls.length === 0 ? (
                <p className="text-sm text-muted-foreground">No active assignments.</p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{terms.male} tag</TableHead><TableHead>{terms.male} name</TableHead>
                        <TableHead>Farm</TableHead><TableHead>Assigned</TableHead><TableHead>Notes</TableHead>
                        {isAdmin && <TableHead className="text-right">Edit</TableHead>}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {visibleBulls.map((b) => (
                        <TableRow key={b.id}>
                          <TableCell className="font-medium">{b.bull_tag_number}</TableCell>
                          <TableCell>{b.bull_name || '—'}</TableCell>
                          <TableCell>{b.location_name}</TableCell>
                          <TableCell>{fmt(b.assigned_date)}</TableCell>
                          <TableCell className="max-w-xs truncate">{b.notes || '—'}</TableCell>
                          {isAdmin && (
                            <TableCell className="text-right">
                              <Button size="icon" variant="ghost" onClick={() => setBullState({ mode: 'edit', assignment: b })}>
                                <Pencil className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>
        </CardContent>
      </Card>

      {/* Dialogs */}
      <RecordServiceDialog
        open={dialog.type === 'service'} onClose={closeDialog} onSuccess={load}
        animalId={dialog.animalId} locationId={dialog.animalId ? undefined : locationParam}
      />
      <RecordPDDialog
        open={dialog.type === 'pd'} onClose={closeDialog} onSuccess={load}
        cycleId={dialog.cycleId} animalId={dialog.animalId}
      />
      <RecordCalvingDialog
        open={dialog.type === 'calving'} onClose={closeDialog} onSuccess={load}
        cycleId={dialog.cycleId} animalId={dialog.animalId}
      />
      <RecordBCSDialog open={dialog.type === 'bcs'} onClose={closeDialog} onSuccess={load} animalId={dialog.animalId} />
      <BullDialog
        state={bullState} onClose={() => setBullState(null)} onSaved={load}
        males={males} locations={locations} defaultLocationId={locationParam} terms={terms}
      />
    </div>
  );
}

export default Reproduction;
