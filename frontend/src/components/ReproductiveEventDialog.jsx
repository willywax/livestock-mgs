import { matchesAnimalTag } from '../lib/animalSearch';
import React, { useState } from 'react';
import { toast } from 'sonner';
import { createReproductiveEvent, getAnimals } from '../lib/api';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { getTerms, toISODate } from './ReproductionDialogs';
const reproductiveLabels = (species) => ({ pd_test: 'PD Test', calving: getTerms(species).event, abortion: 'Abortion', service: 'Service' });
const errText = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

export default function ReproductiveEventDialog({ animal, onClose, onSaved, initialType = null }) {
  const [type, setType] = useState(initialType);
  const [form, setForm] = useState({ event_date: toISODate(new Date()), pd_result: 'pregnant', months_pregnant: '',
    calving_outcome: 'live', offspring_count: '1', abortion_stage: 'early', service_type: 'natural', bull_tag: '', vet: '', notes: '' });
  const [busy, setBusy] = useState(false);
  const labels = reproductiveLabels(animal.species);
  const field = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const select = (key, label, options) => <div className="space-y-2">
    <Label htmlFor={`repro-${key}`}>{label}</Label>
    <Select value={form[key]} onValueChange={(value) => field(key, value)} disabled={busy}>
      <SelectTrigger id={`repro-${key}`}><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(([value, title]) => <SelectItem key={value} value={value}>{title}</SelectItem>)}</SelectContent>
    </Select>
  </div>;

  const save = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const data = { event_type: type, event_date: form.event_date, notes: form.notes.trim() || null };
      if (type === 'pd_test') {
        data.pd_result = form.pd_result;
        data.months_pregnant = form.pd_result === 'pregnant' && form.months_pregnant !== '' ? Number(form.months_pregnant) : null;
        data.vet = form.vet.trim() || null;
      } else if (type === 'calving') {
        data.calving_outcome = form.calving_outcome;
        data.offspring_count = Number(form.offspring_count);
      } else if (type === 'abortion') data.abortion_stage = form.abortion_stage;
      else if (type === 'service') {
        data.service_type = form.service_type;
        if (form.bull_tag.trim()) {
          const tag = form.bull_tag.trim();
          const { data: candidates } = await getAnimals({ search: tag, species: animal.species });
          const matches = candidates.filter((item) => item.sex === 'male' && matchesAnimalTag(item, tag));
          if (matches.length !== 1) {
            toast.error(matches.length ? 'This tag matches multiple males. Use a unique tag.' : 'No male animal found with that tag for this species.');
            return;
          }
          data.bull_animal_id = matches[0].id;
        }
      }
      await createReproductiveEvent(animal.id, data);
      toast.success('Event recorded');
      onSaved();
      onClose();
    } catch (err) {
      toast.error(errText(err, 'Failed to record event'));
    } finally { setBusy(false); }
  };

  return <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
      <DialogHeader><DialogTitle>{type ? `Record ${labels[type].toLowerCase()}` : 'Record reproductive event'}</DialogTitle>
        <DialogDescription>{type ? 'Step 2 of 2: Enter event details.' : 'Step 1 of 2: Choose an event type.'}</DialogDescription></DialogHeader>
      {!type ? <div className="grid grid-cols-2 gap-3">{Object.entries(labels).map(([value, label]) =>
        <Button key={value} variant="outline" onClick={() => setType(value)}>{label}</Button>)}</div> : (
        <form onSubmit={save} className="space-y-4">
          <div className="space-y-2"><Label htmlFor="repro-date">Date</Label>
            <Input id="repro-date" type="date" required value={form.event_date} disabled={busy} onChange={(e) => field('event_date', e.target.value)} /></div>
          {type === 'pd_test' && <>
            {select('pd_result', 'Result', [['pregnant', 'Pregnant'], ['open', 'Open'], ['recheck', 'Recheck']])}
            {form.pd_result === 'pregnant' && <div className="space-y-2"><Label htmlFor="repro-months">Months pregnant (optional)</Label>
              <Input id="repro-months" type="number" min="0" step="1" value={form.months_pregnant} disabled={busy} onChange={(e) => field('months_pregnant', e.target.value)} /></div>}
            <div className="space-y-2"><Label htmlFor="repro-vet">Vet (optional)</Label>
              <Input id="repro-vet" maxLength={100} value={form.vet} disabled={busy} onChange={(e) => field('vet', e.target.value)} /></div>
          </>}
          {type === 'calving' && <>
            {select('calving_outcome', 'Outcome', [['live', 'Live'], ['stillbirth', 'Stillbirth']])}
            <div className="space-y-2"><Label htmlFor="repro-count">Offspring count</Label>
              <Input id="repro-count" type="number" min="0" step="1" required value={form.offspring_count} disabled={busy} onChange={(e) => field('offspring_count', e.target.value)} /></div>
          </>}
          {type === 'abortion' && select('abortion_stage', 'Stage', [['early', 'Early'], ['mid', 'Mid'], ['late', 'Late']])}
          {type === 'service' && <>
            {select('service_type', 'Type', [['natural', 'Natural'], ['ai', 'AI']])}
            <div className="space-y-2"><Label htmlFor="repro-bull">{getTerms(animal.species).male} tag number (optional)</Label>
              <Input id="repro-bull" value={form.bull_tag} disabled={busy} onChange={(e) => field('bull_tag', e.target.value)} /></div>
          </>}
          <div className="space-y-2"><Label htmlFor="repro-notes">Notes (optional)</Label>
            <Textarea id="repro-notes" value={form.notes} disabled={busy} onChange={(e) => field('notes', e.target.value)} /></div>
          <DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={() => setType(null)}>Back</Button>
            <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save event'}</Button></DialogFooter>
        </form>
      )}
    </DialogContent>
  </Dialog>;
}

