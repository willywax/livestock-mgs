import React, { useCallback, useEffect, useState } from 'react';
import { ArrowClockwise, ArrowsClockwise, Bell } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { getLocations, getTransitionRules, getTransitionQueue, bulkConfirmTransitions } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Checkbox } from '../components/ui/checkbox';
import { Skeleton } from '../components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../components/ui/alert-dialog';
import { SPECIES_CONFIG, cn } from '../lib/utils';

// ---- pure helpers (unit-tested) ----

// "Ndama Dume → Achishwa Dume": the target is whichever sex-specific category the rule has.
export function ruleLabel(rule) {
  const to = rule.to_category_name_f && rule.to_category_name_m && rule.to_category_name_f !== rule.to_category_name_m
    ? `${rule.to_category_name_f} / ${rule.to_category_name_m}`
    : (rule.to_category_name_f || rule.to_category_name_m || '?');
  return `${rule.from_category_name} → ${to}`;
}

// The queue item carries no sex: infer it from which of the rule's targets the item is going to.
export function sexForItem(item, rule) {
  if (!rule) return null;
  const isF = item.to_category_id === rule.to_category_id_f;
  const isM = item.to_category_id === rule.to_category_id_m;
  if (isF && !isM) return 'female';
  if (isM && !isF) return 'male';
  return null;
}

export function overdueMonths(item, rule) {
  if (!rule || rule.trigger_age_months == null) return 0;
  return Math.max(0, item.age_months - rule.trigger_age_months);
}

// 0 = due now, 1-2 months = amber, 3+ = red (the queue only has whole months)
export function overdueTone(months) {
  if (months >= 3) return 'red';
  if (months >= 1) return 'amber';
  return 'none';
}

// One group per active age rule (empty groups included so each card can show its empty state).
export function groupQueue(rules, pending, species) {
  return rules
    .filter((r) => r.trigger_type === 'age' && r.is_active && (!species || r.species === species))
    .map((rule) => ({ rule, items: pending.filter((p) => p.rule_id === rule.id) }));
}

const TONE_CLASS = { red: 'bg-red-100 text-red-800', amber: 'bg-amber-100 text-amber-800', none: 'text-muted-foreground' };

function QueueCard({ group, selected, onToggle, onToggleAll, onConfirm, busy }) {
  const { rule, items } = group;
  const ids = items.map((i) => i.animal_id);
  const chosen = ids.filter((id) => selected.has(id));
  const allSelected = ids.length > 0 && chosen.length === ids.length;
  return (
    <Card className="border-border/60" data-testid={`transition-card-${rule.id}`}>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-3">
        <CardTitle className="font-heading text-base">
          {ruleLabel(rule)} <span className="font-normal text-muted-foreground">({rule.trigger_age_months} months)</span>
        </CardTitle>
        <span className="text-sm text-muted-foreground">{items.length} {items.length === 1 ? 'animal' : 'animals'} ready</span>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No animals ready for this transition.</p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10" />
                  <TableHead>Tag</TableHead>
                  <TableHead>Sex</TableHead>
                  <TableHead>Age</TableHead>
                  <TableHead>Farm</TableHead>
                  <TableHead>Months overdue</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => {
                  const months = overdueMonths(item, rule);
                  const sex = sexForItem(item, rule);
                  return (
                    <TableRow key={item.animal_id} data-testid={`transition-row-${item.animal_id}`}>
                      <TableCell>
                        <Checkbox
                          checked={selected.has(item.animal_id)}
                          onCheckedChange={() => onToggle(item.animal_id)}
                          aria-label={`Select ${item.tag_number}`}
                        />
                      </TableCell>
                      <TableCell className="font-mono font-medium">{item.tag_number}</TableCell>
                      <TableCell className="capitalize">{sex || '—'}</TableCell>
                      <TableCell>{item.age_months} months</TableCell>
                      <TableCell>{item.location_name || '—'}</TableCell>
                      <TableCell>
                        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', TONE_CLASS[overdueTone(months)])}>
                          {months === 0 ? 'Due now' : `${months} ${months === 1 ? 'month' : 'months'}`}
                        </span>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => onToggleAll(ids, !allSelected)}>
                {allSelected ? 'Clear selection' : 'Select all'}
              </Button>
              <Button
                size="sm"
                disabled={chosen.length === 0 || busy}
                onClick={() => onConfirm(group, chosen)}
                data-testid={`confirm-selected-${rule.id}`}
              >
                Confirm selected ({chosen.length})
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function TransitionQueue() {
  const [locations, setLocations] = useState([]);
  const [rules, setRules] = useState([]);
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [farm, setFarm] = useState('all');
  const [species, setSpecies] = useState('all');
  const [selected, setSelected] = useState(new Set());
  const [confirming, setConfirming] = useState(null); // { group, ids }
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getLocations().then((r) => setLocations(r.data)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = {};
      if (farm !== 'all') params.location_id = farm;
      if (species !== 'all') params.species = species;
      const [rulesRes, queueRes] = await Promise.all([getTransitionRules(), getTransitionQueue(params)]);
      setRules(rulesRes.data);
      setPending(queueRes.data.pending);
      setSelected(new Set());
    } catch {
      setError(true);
      toast.error('Failed to load the transition queue');
    } finally {
      setLoading(false);
    }
  }, [farm, species]);

  useEffect(() => { load(); }, [load]);

  const groups = groupQueue(rules, pending, species === 'all' ? null : species);
  const bySpecies = ['cattle', 'sheep', 'goat']
    .map((sp) => ({ sp, groups: groups.filter((g) => g.rule.species === sp) }))
    .filter((s) => s.groups.length > 0);

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleAll(ids, on) {
    setSelected((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
      return next;
    });
  }

  async function runConfirm() {
    const { group, ids } = confirming;
    setBusy(true);
    try {
      const items = group.items.filter((i) => ids.includes(i.animal_id));
      const res = await bulkConfirmTransitions({
        transitions: items.map((i) => ({ animal_id: i.animal_id, to_category_id: i.to_category_id })),
      });
      const { succeeded, failed, results } = res.data;
      if (succeeded > 0) toast.success(`${succeeded} ${succeeded === 1 ? 'animal' : 'animals'} transitioned`);
      if (failed > 0) {
        const first = results.find((r) => !r.success);
        toast.error(`${failed} could not be transitioned: ${first?.error || 'unknown error'}`);
      }
      setConfirming(null);
      await load(); // confirmed rows leave the queue; failures stay listed
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to confirm transitions');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6" data-testid="transition-queue-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold flex items-center gap-3">
            <ArrowsClockwise className="h-8 w-8 text-primary" />
            Category Transitions
          </h1>
          <p className="text-muted-foreground mt-1">Animals due to move up to their next category</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={farm} onValueChange={setFarm}>
            <SelectTrigger className="w-44" aria-label="Farm"><SelectValue placeholder="All Farms" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Farms</SelectItem>
              {locations.map((l) => <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={species} onValueChange={setSpecies}>
            <SelectTrigger className="w-36" aria-label="Species"><SelectValue placeholder="All Species" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Species</SelectItem>
              {Object.entries(SPECIES_CONFIG).map(([key, cfg]) => (
                <SelectItem key={key} value={key}>{cfg.label.split(' ')[0]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" className="gap-2" onClick={load} disabled={loading} data-testid="refresh-queue-btn">
            <ArrowClockwise className={cn('h-4 w-4', loading && 'animate-spin')} />
            Refresh
          </Button>
        </div>
      </div>

      {!loading && pending.length > 0 && (
        <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900" data-testid="transition-banner">
          <Bell className="h-4 w-4" />
          {pending.length} {pending.length === 1 ? 'animal' : 'animals'} ready to transition
        </div>
      )}

      {loading ? (
        <div className="space-y-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}</div>
      ) : error ? (
        <p className="text-sm text-red-600">Could not load the queue. Use Refresh to try again.</p>
      ) : bySpecies.length === 0 ? (
        <p className="text-muted-foreground">No active age-based transition rules. Rules are managed in Settings.</p>
      ) : (
        bySpecies.map(({ sp, groups: spGroups }) => (
          <section key={sp} className="space-y-3">
            <h2 className="font-heading text-lg font-semibold capitalize">{sp}</h2>
            {spGroups.map((group) => (
              <QueueCard
                key={group.rule.id}
                group={group}
                selected={selected}
                onToggle={toggle}
                onToggleAll={toggleAll}
                onConfirm={(g, ids) => setConfirming({ group: g, ids })}
                busy={busy}
              />
            ))}
          </section>
        ))
      )}

      <AlertDialog open={!!confirming} onOpenChange={(open) => { if (!open && !busy) setConfirming(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm category transition</AlertDialogTitle>
            <AlertDialogDescription>
              {confirming && `Move ${confirming.ids.length} ${confirming.ids.length === 1 ? 'animal' : 'animals'} (${ruleLabel(confirming.group.rule)}). Stock counts adjust automatically and this cannot be undone from here.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => { e.preventDefault(); runConfirm(); }}
              data-testid="confirm-transition-btn"
            >
              {busy ? 'Moving...' : 'Confirm'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default TransitionQueue;
