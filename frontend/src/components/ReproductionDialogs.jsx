import React, { useState, useEffect, useMemo } from 'react';
import { addDays, format, parseISO } from 'date-fns';
import { toast } from 'sonner';
import { CalendarBlank, Check, CaretUpDown, Info } from '@phosphor-icons/react';
import {
  getAnimals, getAnimal, getBullAssignments, getReproductiveCycle, getReproductiveCycles,
  createReproductiveCycle, updateReproductiveCycle, createBCSRecord,
} from '../lib/api';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Calendar } from './ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './ui/command';
import { RadioGroup, RadioGroupItem } from './ui/radio-group';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { cn } from '../lib/utils';

// ---------------------------------------------------------------------------
// Species-aware constants. Keys are the API species values: cattle | sheep | goat.
// ---------------------------------------------------------------------------
export const GESTATION_DAYS = { cattle: 283, sheep: 147, goat: 150 };

export const SPECIES_TERMS = {
  cattle: { female: 'Cow', females: 'Cows', male: 'Bull', offspring: 'Calf', event: 'Calving' },
  sheep: { female: 'Ewe', females: 'Ewes', male: 'Ram', offspring: 'Lamb', event: 'Lambing' },
  goat: { female: 'Doe', females: 'Does', male: 'Buck', offspring: 'Kid', event: 'Kidding' },
};

const NEUTRAL_TERMS = { female: 'Animal', females: 'Animals', male: 'Sire', offspring: 'Offspring', event: 'Birth' };

// <green: green, <amber: amber, otherwise red (days between calvings).
export const INTERVAL_THRESHOLDS = {
  cattle: { green: 400, amber: 500 },
  sheep: { green: 240, amber: 300 },
  goat: { green: 240, amber: 300 },
};

export const SPECIES_PILLS = [
  { value: 'all', label: 'All species' },
  { value: 'cattle', label: 'Cattle' },
  { value: 'sheep', label: 'Sheep' },
  { value: 'goat', label: 'Goats' },
];

const SPECIES_NAMES = { cattle: 'cattle', sheep: 'sheep', goat: 'goat' };
const DAYS_PER_MONTH = 30.4375;
const BCS_OPTIONS = ['1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0'];

export const getTerms = (species) => SPECIES_TERMS[species] || NEUTRAL_TERMS;

// 'green' | 'amber' | 'red' | 'grey' (no interval, e.g. first calving)
export const intervalTone = (days, species) => {
  if (days === null || days === undefined) return 'grey';
  const t = INTERVAL_THRESHOLDS[species] || INTERVAL_THRESHOLDS.cattle;
  if (days < t.green) return 'green';
  if (days < t.amber) return 'amber';
  return 'red';
};

export const toISODate = (d) => format(d, 'yyyy-MM-dd');
export const parseDate = (s) => (s ? parseISO(s) : null); // local midnight, no UTC shift

const maxPregnancyMonths = (species) =>
  Math.max(1, Math.floor((GESTATION_DAYS[species] || GESTATION_DAYS.cattle) / DAYS_PER_MONTH));

const errMsg = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

// Notes are replaced by a PUT, so append to what is already stored.
const appendNote = (existing, label, text) => {
  const t = (text || '').trim();
  if (!t) return undefined;
  return `${existing ? `${existing}\n` : ''}${label}: ${t}`;
};

const latestBy = (cycles, status) =>
  cycles.filter((c) => c.status === status).sort((a, b) => b.cycle_number - a.cycle_number)[0] || null;

// ---------------------------------------------------------------------------
// Shared fields (also used by pages/Reproduction.jsx)
// ---------------------------------------------------------------------------
export function DateField({ value, onChange, testId, disabled }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          data-testid={testId}
          className={cn('w-full justify-start gap-2 font-normal', !value && 'text-muted-foreground')}
        >
          <CalendarBlank className="h-4 w-4" />
          {value ? format(value, 'dd MMM yyyy') : 'Pick a date'}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={value || undefined}
          onSelect={(d) => { if (d) { onChange(d); setOpen(false); } }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}

function SpeciesPills({ value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Species filter">
      {SPECIES_PILLS.map((p) => (
        <button
          key={p.value}
          type="button"
          onClick={() => onChange(p.value)}
          data-testid={`species-pill-${p.value}`}
          className={cn(
            'px-3 py-1 rounded-full text-xs font-medium border transition-colors',
            value === p.value
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-card text-muted-foreground hover:bg-muted'
          )}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

export { SpeciesPills };

// Searchable animal picker with a client-side species filter (no extra API call).
export function AnimalSelect({ animals, value, onChange, label, disabled, testId = 'animal-select' }) {
  const [open, setOpen] = useState(false);
  const [species, setSpecies] = useState('all');
  const selected = animals.find((a) => a.id === value);
  const visible = useMemo(
    () => animals.filter((a) => species === 'all' || a.species === species),
    [animals, species]
  );
  const describe = (a) => `${a.tag_number}${a.name ? ` · ${a.name}` : ''} · ${a.location_name || ''}`;

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {!disabled && <SpeciesPills value={species} onChange={setSpecies} />}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            disabled={disabled}
            data-testid={testId}
            className="w-full justify-between font-normal"
          >
            <span className="truncate">{selected ? describe(selected) : 'Search by tag or name…'}</span>
            <CaretUpDown className="h-4 w-4 opacity-50 shrink-0" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
          <Command>
            <CommandInput placeholder="Tag or name" />
            <CommandList>
              <CommandEmpty>No animals found.</CommandEmpty>
              <CommandGroup>
                {visible.map((a) => (
                  <CommandItem
                    key={a.id}
                    value={`${a.tag_number} ${a.name || ''} ${a.location_name || ''} ${a.id}`}
                    onSelect={() => { onChange(a); setOpen(false); }}
                  >
                    <Check className={cn('mr-2 h-4 w-4', value === a.id ? 'opacity-100' : 'opacity-0')} />
                    <span className="truncate">{describe(a)}</span>
                    <span className="ml-auto pl-2 text-xs text-muted-foreground capitalize">{a.species}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function BCSSelect({ value, onChange, label = 'Body condition score (BCS)', required, testId }) {
  return (
    <div className="space-y-2">
      <Label>{label}{required ? '' : ' (optional)'}</Label>
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger data-testid={testId}><SelectValue placeholder="Select score" /></SelectTrigger>
        <SelectContent>
          {BCS_OPTIONS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data hook: all animals once per dialog open. The fixed animal (animalId) is
// fetched by id so inactive/male animals still resolve.
// ---------------------------------------------------------------------------
function useDialogAnimals(open, { animalId, locationId, females = true }) {
  const [all, setAll] = useState([]);
  const [fixed, setFixed] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    getAnimals({ status: 'active' })
      .then((res) => { if (live) setAll(res.data); })
      .catch(() => toast.error('Failed to load animals'));
    if (animalId) {
      getAnimal(animalId)
        .then((res) => { if (live) setFixed(res.data); })
        .catch(() => toast.error('Failed to load animal'));
    } else {
      setFixed(null);
    }
    return () => { live = false; };
  }, [open, animalId]);

  const pickable = useMemo(
    () => all.filter((a) => (!females || a.sex === 'female') && (!locationId || a.location_id === locationId)),
    [all, females, locationId]
  );
  return { all, pickable, fixed };
}

function DialogShell({ open, onClose, title, description, children, onSubmit, submitting, submitLabel, canSubmit, testId }) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid={testId}>
        <DialogHeader>
          <DialogTitle className="font-heading">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-4">{children}</div>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button type="button" onClick={onSubmit} disabled={submitting || !canSubmit} data-testid={`${testId}-submit`}>
            {submitting ? 'Saving…' : submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const Helper = ({ children }) => (
  <p className="text-xs text-muted-foreground flex items-start gap-1">
    <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
    <span>{children}</span>
  </p>
);

// ---------------------------------------------------------------------------
// 1. Record service
// ---------------------------------------------------------------------------
export function RecordServiceDialog({ open, onClose, onSuccess, animalId, locationId }) {
  const { pickable, fixed } = useDialogAnimals(open, { animalId, locationId });
  const [picked, setPicked] = useState(null);
  const [serviceDate, setServiceDate] = useState(new Date());
  const [bulls, setBulls] = useState([]);
  const [bullId, setBullId] = useState('none');
  const [serviceType, setServiceType] = useState('natural');
  const [expected, setExpected] = useState(null);
  const [expectedEdited, setExpectedEdited] = useState(false);
  const [bcs, setBcs] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const animal = fixed || picked;
  const terms = getTerms(animal?.species);
  const gestation = animal ? GESTATION_DAYS[animal.species] : null;

  useEffect(() => {
    if (!open) return;
    setPicked(null); setServiceDate(new Date()); setBullId('none'); setServiceType('natural');
    setExpected(null); setExpectedEdited(false); setBcs(''); setNotes(''); setBulls([]);
  }, [open]);

  useEffect(() => {
    if (!animal) { setBulls([]); return undefined; }
    let live = true;
    getBullAssignments({ active_only: true, location_id: animal.location_id })
      .then((res) => { if (live) setBulls(res.data); })
      .catch(() => toast.error('Failed to load bulls'));
    return () => { live = false; };
  }, [animal]);

  useEffect(() => {
    if (!expectedEdited && gestation && serviceDate) setExpected(addDays(serviceDate, gestation));
  }, [serviceDate, gestation, expectedEdited]);

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await createReproductiveCycle({
        animal_id: animal.id,
        service_date: toISODate(serviceDate),
        service_type: serviceType,
        bull_assignment_id: bullId === 'none' ? null : Number(bullId),
        expected_calving_date: expected ? toISODate(expected) : null,
        bcs_at_service: bcs ? Number(bcs) : null,
        notes: notes.trim() || null,
        status: 'served',
      });
      toast.success('Service recorded');
      onSuccess?.(res.data);
      onClose();
    } catch (err) {
      toast.error(errMsg(err, 'Failed to record service'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DialogShell
      open={open} onClose={onClose} title="Record service" testId="service-dialog"
      onSubmit={submit} submitting={submitting} submitLabel="Save service" canSubmit={!!animal && !!serviceDate}
    >
      {animalId ? (
        <div className="space-y-2">
          <Label>{terms.female}</Label>
          <Input readOnly value={fixed ? `${fixed.tag_number}${fixed.name ? ` · ${fixed.name}` : ''}` : '…'} />
        </div>
      ) : (
        <AnimalSelect animals={pickable} value={picked?.id} onChange={setPicked} label={terms.female} />
      )}
      <div className="space-y-2">
        <Label>Service date</Label>
        <DateField value={serviceDate} onChange={setServiceDate} testId="service-date" />
      </div>
      <div className="space-y-2">
        <Label>{terms.male}</Label>
        <Select value={bullId} onValueChange={setBullId} disabled={!animal}>
          <SelectTrigger data-testid="service-bull"><SelectValue placeholder={`Select ${terms.male.toLowerCase()}`} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">Not recorded</SelectItem>
            {bulls.map((b) => (
              <SelectItem key={b.id} value={String(b.id)}>
                {b.bull_tag_number}{b.bull_name ? ` · ${b.bull_name}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {animal && bulls.length === 0 && <Helper>No active {terms.male.toLowerCase()} assignment at this farm.</Helper>}
      </div>
      <div className="space-y-2">
        <Label>Service type</Label>
        <RadioGroup value={serviceType} onValueChange={setServiceType} className="flex gap-6">
          <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="natural" />Natural</label>
          <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="ai" />AI</label>
        </RadioGroup>
      </div>
      <div className="space-y-2">
        <Label>Expected {terms.event.toLowerCase()} date</Label>
        <DateField
          value={expected}
          onChange={(d) => { setExpected(d); setExpectedEdited(true); }}
          testId="service-expected"
          disabled={!animal}
        />
        <Helper>
          {animal
            ? `Auto-filled: ${SPECIES_NAMES[animal.species]} gestation is ${gestation} days — edit if needed`
            : 'Select an animal to auto-fill from its species gestation period'}
        </Helper>
      </div>
      <BCSSelect value={bcs} onChange={setBcs} label="BCS at service" testId="service-bcs" />
      <div className="space-y-2">
        <Label>Notes (optional)</Label>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </div>
    </DialogShell>
  );
}

// Resolve the cycle a PD / calving dialog acts on. Returns { cycle, hint }.
function useTargetCycle(open, { cycleId, animalId, pickedId, status, fallbackStatus }) {
  const [cycle, setCycle] = useState(null);
  const [cycleAnimal, setCycleAnimal] = useState(null);
  const [hint, setHint] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) { setCycle(null); setCycleAnimal(null); setHint(''); return undefined; }
    let live = true;
    const run = async () => {
      setLoading(true);
      setHint('');
      try {
        if (cycleId) {
          const c = (await getReproductiveCycle(cycleId)).data;
          const a = (await getAnimal(c.animal_id)).data;
          if (live) { setCycle(c); setCycleAnimal(a); }
          return;
        }
        const targetAnimal = animalId || pickedId;
        if (!targetAnimal) { if (live) { setCycle(null); setCycleAnimal(null); } return; }
        const cycles = (await getReproductiveCycles({ animal_id: targetAnimal })).data;
        let found = latestBy(cycles, status);
        let note = '';
        if (!found && fallbackStatus) {
          found = latestBy(cycles, fallbackStatus);
          if (found) note = `No ${status} cycle found: using the latest ${fallbackStatus} cycle.`;
        }
        if (!found) note = `No ${status}${fallbackStatus ? ` or ${fallbackStatus}` : ''} cycle recorded for this animal.`;
        if (live) { setCycle(found); setHint(note); }
      } catch (err) {
        if (live) { setCycle(null); toast.error(errMsg(err, 'Failed to load cycle')); }
      } finally {
        if (live) setLoading(false);
      }
    };
    run();
    return () => { live = false; };
  }, [open, cycleId, animalId, pickedId, status, fallbackStatus]);

  return { cycle, cycleAnimal, hint, loading };
}

// ---------------------------------------------------------------------------
// 2. Record PD check
// ---------------------------------------------------------------------------
export function RecordPDDialog({ open, onClose, onSuccess, cycleId, animalId }) {
  const [picked, setPicked] = useState(null);
  const { pickable, fixed } = useDialogAnimals(open, { animalId: cycleId ? null : animalId });
  const target = useTargetCycle(open, { cycleId, animalId, pickedId: picked?.id, status: 'served' });
  const animal = target.cycleAnimal || fixed || picked;
  const terms = getTerms(animal?.species);
  const gestation = animal ? GESTATION_DAYS[animal.species] : null;

  const [pdDate, setPdDate] = useState(new Date());
  const [result, setResult] = useState('pregnant');
  const [months, setMonths] = useState('');
  const [expected, setExpected] = useState(null);
  const [expectedEdited, setExpectedEdited] = useState(false);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPicked(null); setPdDate(new Date()); setResult('pregnant'); setMonths('');
    setExpected(null); setExpectedEdited(false); setNotes('');
  }, [open]);

  useEffect(() => {
    if (!expectedEdited && result === 'pregnant' && gestation && months && pdDate) {
      const remaining = Math.max(0, Math.round(gestation - Number(months) * DAYS_PER_MONTH));
      setExpected(addDays(pdDate, remaining));
    }
  }, [pdDate, months, result, gestation, expectedEdited]);

  const monthOptions = Array.from({ length: animal ? maxPregnancyMonths(animal.species) : 9 }, (_, i) => String(i + 1));
  const canSubmit = !!target.cycle && !!pdDate && (result !== 'pregnant' || !!months);

  const submit = async () => {
    setSubmitting(true);
    try {
      const body = {
        pd_check_date: toISODate(pdDate),
        pd_result: result,
        status: result === 'pregnant' ? 'pregnant' : 'open',
      };
      if (result === 'pregnant') {
        body.pd_months_pregnant = Number(months);
        if (expected) body.expected_calving_date = toISODate(expected);
      }
      const note = appendNote(target.cycle.notes, 'PD', notes);
      if (note !== undefined) body.notes = note;
      const res = await updateReproductiveCycle(target.cycle.id, body);
      toast.success('PD check recorded');
      onSuccess?.(res.data);
      onClose();
    } catch (err) {
      toast.error(errMsg(err, 'Failed to record PD check'));
    } finally {
      setSubmitting(false);
    }
  };

  const showPicker = !cycleId && !animalId;
  return (
    <DialogShell
      open={open} onClose={onClose} title="Record PD check" testId="pd-dialog"
      onSubmit={submit} submitting={submitting} submitLabel="Save PD check" canSubmit={canSubmit}
    >
      {showPicker ? (
        <AnimalSelect animals={pickable} value={picked?.id} onChange={setPicked} label={terms.female} />
      ) : (
        <div className="space-y-2">
          <Label>{terms.female}</Label>
          <Input readOnly value={animal ? `${animal.tag_number}${animal.name ? ` · ${animal.name}` : ''}` : '…'} />
        </div>
      )}
      {target.hint && <Helper>{target.hint}</Helper>}
      <div className="space-y-2">
        <Label>PD check date</Label>
        <DateField value={pdDate} onChange={setPdDate} testId="pd-date" />
      </div>
      <div className="space-y-2">
        <Label>Result</Label>
        <RadioGroup value={result} onValueChange={setResult} className="flex gap-6">
          <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="pregnant" />Pregnant</label>
          <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="open" />Open</label>
          <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="repeat" />Repeat</label>
        </RadioGroup>
      </div>
      {result === 'pregnant' && (
        <>
          <div className="space-y-2">
            <Label>Estimated months pregnant</Label>
            <Select value={months || undefined} onValueChange={setMonths}>
              <SelectTrigger data-testid="pd-months"><SelectValue placeholder="Select months" /></SelectTrigger>
              <SelectContent>
                {monthOptions.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Expected {terms.event.toLowerCase()} date</Label>
            <DateField
              value={expected}
              onChange={(d) => { setExpected(d); setExpectedEdited(true); }}
              testId="pd-expected"
            />
            {animal && (
              <Helper>
                Auto-filled: {SPECIES_NAMES[animal.species]} gestation is {gestation} days — edit if needed
              </Helper>
            )}
          </div>
        </>
      )}
      <div className="space-y-2">
        <Label>Notes (optional)</Label>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </div>
    </DialogShell>
  );
}

// ---------------------------------------------------------------------------
// 3. Record calving / lambing / kidding
// ---------------------------------------------------------------------------
export function RecordCalvingDialog({ open, onClose, onSuccess, cycleId, animalId }) {
  const [picked, setPicked] = useState(null);
  const { all, pickable, fixed } = useDialogAnimals(open, { animalId: cycleId ? null : animalId });
  const target = useTargetCycle(open, {
    cycleId, animalId, pickedId: picked?.id, status: 'pregnant', fallbackStatus: 'served',
  });
  const animal = target.cycleAnimal || fixed || picked;
  const terms = getTerms(animal?.species);

  const [date, setDate] = useState(new Date());
  const [outcome, setOutcome] = useState('');
  const [sex, setSex] = useState('');
  const [tag, setTag] = useState('');
  const [stage, setStage] = useState('');
  const [bcs, setBcs] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPicked(null); setDate(new Date()); setOutcome(''); setSex(''); setTag('');
    setStage(''); setBcs(''); setNotes('');
  }, [open]);

  const isLive = outcome === 'live_calf' || outcome === 'assisted_live';
  const isAbortion = outcome === 'abortion';
  const multiBirth = animal && animal.species !== 'cattle';
  const canSubmit = !!target.cycle && !!date && !!outcome && (!isLive || !!sex);

  const submit = async () => {
    const serviceDate = parseDate(target.cycle.service_date);
    if (serviceDate && date < serviceDate) {
      toast.error(`${terms.event} date is before the service date`);
      return;
    }
    setSubmitting(true);
    try {
      const body = {
        actual_calving_date: toISODate(date),
        calving_outcome: outcome,
        status: isAbortion ? 'aborted' : 'calved',
      };
      if (bcs) body.bcs_at_calving = Number(bcs);
      if (isAbortion && stage) body.abortion_stage = stage;
      let noteText = notes;
      if (isLive) {
        body.calf_sex = sex;
        const wanted = tag.trim().toLowerCase();
        if (wanted) {
          const match = all.find((a) => a.species === animal.species && a.tag_number.toLowerCase() === wanted);
          if (match) body.calf_animal_id = match.id;
          else noteText = `${noteText ? `${noteText.trim()}\n` : ''}${terms.offspring} tag: ${tag.trim()}`;
        }
      }
      const note = appendNote(target.cycle.notes, terms.event, noteText);
      if (note !== undefined) body.notes = note;
      const res = await updateReproductiveCycle(target.cycle.id, body);
      toast.success(`${terms.event} recorded`);
      const days = res.data.calving_interval_days;
      if (days !== null && days !== undefined) {
        const message = `${terms.event} interval: ${days} days`;
        const tone = intervalTone(days, animal.species);
        if (tone === 'green') toast.success(message);
        else if (tone === 'amber') toast.warning(message);
        else toast.error(message);
      }
      onSuccess?.(res.data);
      onClose();
    } catch (err) {
      toast.error(errMsg(err, `Failed to record ${terms.event.toLowerCase()}`));
    } finally {
      setSubmitting(false);
    }
  };

  const showPicker = !cycleId && !animalId;
  return (
    <DialogShell
      open={open} onClose={onClose} title={`Record ${terms.event.toLowerCase()}`} testId="calving-dialog"
      onSubmit={submit} submitting={submitting} submitLabel={`Save ${terms.event.toLowerCase()}`} canSubmit={canSubmit}
    >
      {showPicker ? (
        <AnimalSelect animals={pickable} value={picked?.id} onChange={setPicked} label={terms.female} />
      ) : (
        <div className="space-y-2">
          <Label>{terms.female}</Label>
          <Input readOnly value={animal ? `${animal.tag_number}${animal.name ? ` · ${animal.name}` : ''}` : '…'} />
        </div>
      )}
      {target.hint && <Helper>{target.hint}</Helper>}
      <div className="space-y-2">
        <Label>{terms.event} date</Label>
        <DateField value={date} onChange={setDate} testId="calving-date" />
      </div>
      <div className="space-y-2">
        <Label>Outcome</Label>
        <Select value={outcome || undefined} onValueChange={setOutcome}>
          <SelectTrigger data-testid="calving-outcome"><SelectValue placeholder="Select outcome" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="live_calf">Live {terms.offspring.toLowerCase()}</SelectItem>
            <SelectItem value="stillbirth">Stillbirth</SelectItem>
            <SelectItem value="abortion">Abortion</SelectItem>
            <SelectItem value="assisted_live">Assisted — live</SelectItem>
            <SelectItem value="assisted_dead">Assisted — dead</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {isLive && (
        <>
          <div className="space-y-2">
            <Label>{terms.offspring} sex</Label>
            <RadioGroup value={sex} onValueChange={setSex} className="flex gap-6">
              <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="male" />Male</label>
              <label className="flex items-center gap-2 text-sm"><RadioGroupItem value="female" />Female</label>
            </RadioGroup>
          </div>
          <div className="space-y-2">
            <Label>{terms.offspring} tag (optional)</Label>
            <Input value={tag} onChange={(e) => setTag(e.target.value)} data-testid="calving-tag" />
          </div>
          {multiBirth && (
            <Helper>
              Sheep and goats often have multiple offspring — record additional lambs/kids in the cycle notes below
            </Helper>
          )}
        </>
      )}
      {isAbortion && (
        <div className="space-y-2">
          <Label>Stage</Label>
          <Select value={stage || undefined} onValueChange={setStage}>
            <SelectTrigger data-testid="calving-stage"><SelectValue placeholder="Select stage" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="early">Early</SelectItem>
              <SelectItem value="mid">Mid</SelectItem>
              <SelectItem value="late">Late</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}
      <BCSSelect value={bcs} onChange={setBcs} label={`BCS at ${terms.event.toLowerCase()}`} testId="calving-bcs" />
      <div className="space-y-2">
        <Label>Notes (optional)</Label>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </div>
    </DialogShell>
  );
}

// ---------------------------------------------------------------------------
// 4. Record BCS
// ---------------------------------------------------------------------------
export function RecordBCSDialog({ open, onClose, onSuccess, animalId }) {
  const [picked, setPicked] = useState(null);
  const { pickable, fixed } = useDialogAnimals(open, { animalId });
  const animal = fixed || picked;
  const terms = getTerms(animal?.species);
  const [date, setDate] = useState(new Date());
  const [bcs, setBcs] = useState('');
  const [scoredBy, setScoredBy] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPicked(null); setDate(new Date()); setBcs(''); setScoredBy(''); setNotes('');
  }, [open]);

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await createBCSRecord({
        animal_id: animal.id,
        score_date: toISODate(date),
        bcs: Number(bcs),
        scored_by: scoredBy.trim() || null,
        notes: notes.trim() || null,
      });
      toast.success('BCS recorded');
      onSuccess?.(res.data);
      onClose();
    } catch (err) {
      toast.error(errMsg(err, 'Failed to record BCS'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <DialogShell
      open={open} onClose={onClose} title="Log BCS score" testId="bcs-dialog"
      onSubmit={submit} submitting={submitting} submitLabel="Save score" canSubmit={!!animal && !!bcs && !!date}
    >
      {animalId ? (
        <div className="space-y-2">
          <Label>{terms.female}</Label>
          <Input readOnly value={fixed ? `${fixed.tag_number}${fixed.name ? ` · ${fixed.name}` : ''}` : '…'} />
        </div>
      ) : (
        <AnimalSelect animals={pickable} value={picked?.id} onChange={setPicked} label={terms.female} />
      )}
      <div className="space-y-2">
        <Label>Score date</Label>
        <DateField value={date} onChange={setDate} testId="bcs-date" />
      </div>
      <BCSSelect value={bcs} onChange={setBcs} label="BCS" required testId="bcs-score" />
      <div className="space-y-2">
        <Label>Scored by</Label>
        <Input value={scoredBy} onChange={(e) => setScoredBy(e.target.value)} />
      </div>
      <div className="space-y-2">
        <Label>Notes (optional)</Label>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </div>
    </DialogShell>
  );
}
