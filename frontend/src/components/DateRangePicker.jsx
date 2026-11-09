import React, { useState } from 'react';
import { format, subDays } from 'date-fns';
import { Calendar } from './ui/calendar';
import { Button } from './ui/button';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';

// Today in the ranch's timezone, as a local-midnight Date (so date-fns formats it correctly).
export function farmToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const v = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return new Date(Number(v.year), Number(v.month) - 1, Number(v.day));
}

export function lastDaysRange(days) {
  const to = farmToday();
  return { from: subDays(to, days - 1), to };
}

export function yearToDateRange() {
  const to = farmToday();
  return { from: new Date(to.getFullYear(), 0, 1), to };
}

const PRESETS = [
  { label: 'Last 7 days', range: () => lastDaysRange(7) },
  { label: 'Last 30 days', range: () => lastDaysRange(30) },
  { label: 'Last 90 days', range: () => lastDaysRange(90) },
  { label: 'This month', range: () => { const to = farmToday(); return { from: new Date(to.getFullYear(), to.getMonth(), 1), to }; } },
  { label: 'This year', range: yearToDateRange },
  { label: 'Last year', range: () => { const y = farmToday().getFullYear() - 1; return { from: new Date(y, 0, 1), to: new Date(y, 11, 31) }; } },
];

/**
 * value: { from: Date, to: Date } or null/undefined (shown as "All dates").
 * onChange(range) receives a complete range. With `clearable`, onChange(null) is also called by "Clear".
 */
export default function DateRangePicker({ value, onChange, clearable = false, presets = true }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value || undefined);
  const complete = value?.from && value?.to;
  return <Popover open={open} onOpenChange={(next) => { if (next) setDraft(value || undefined); setOpen(next); }}>
    <PopoverTrigger asChild><Button variant="outline" aria-label="Report date range">
      {complete ? `${format(value.from, 'dd MMM yyyy')} – ${format(value.to, 'dd MMM yyyy')}` : 'All dates'}
    </Button></PopoverTrigger>
    <PopoverContent align="end" className="w-auto p-0">
      {presets && <div className="flex flex-wrap gap-2 border-b p-3">
        {PRESETS.map((preset) => <Button key={preset.label} variant="outline" size="sm" onClick={() => { onChange(preset.range()); setOpen(false); }}>{preset.label}</Button>)}
      </div>}
      <Calendar mode="range" selected={draft} onSelect={setDraft} defaultMonth={value?.to || undefined} />
      <div className="flex justify-end gap-2 border-t p-3">
        {clearable && <Button variant="ghost" className="mr-auto" onClick={() => { onChange(null); setOpen(false); }}>Clear</Button>}
        <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
        <Button disabled={!draft?.from || !draft?.to} onClick={() => { onChange({ from: draft.from, to: draft.to }); setOpen(false); }}>Apply</Button>
      </div>
    </PopoverContent>
  </Popover>;
}
