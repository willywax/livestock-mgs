import React, { useEffect, useState } from 'react';
import { Check, X } from '@phosphor-icons/react';
import { searchAnimals } from '../lib/api';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from './ui/command';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Skeleton } from './ui/skeleton';
import { cn } from '../lib/utils';

// Comma-separated tag string <-> array. The event payload keeps the string form.
export function parseTags(value) {
  if (!value) return [];
  return value.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
}

/**
 * Searchable multi-select of REGISTERED ACTIVE animals. The value is a controlled
 * comma-separated tag string, so it drops in wherever a free-text tag input was used.
 *
 * Props: locationId, species, categoryId (optional, client-side filter), sex (optional,
 * client-side filter), value, onChange(string), placeholder, maxSelect (optional), testId,
 * status (default 'active'; pass null to list animals of every status, e.g. when editing a past event).
 * If the animals fetch fails it falls back to a plain text input so events can still be saved.
 */
function AnimalTagPicker({
  locationId,
  species,
  categoryId,
  sex,
  value,
  onChange,
  placeholder = 'Search animals by tag or name...',
  maxSelect,
  testId,
  status = 'active',
}) {
  const [animals, setAnimals] = useState(null); // null while loading
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(function () {
    if (!locationId || !species) {
      setAnimals(null);
      setFailed(false);
      return undefined;
    }
    let cancelled = false;
    setAnimals(null);
    setFailed(false);
    searchAnimals({ location_id: locationId, species: species, ...(status ? { status: status } : {}) })
      .then(function (res) { if (!cancelled) setAnimals(res.data); })
      .catch(function () { if (!cancelled) setFailed(true); });
    return function () { cancelled = true; };
  }, [locationId, species, status]);

  const selected = parseTags(value);

  // Not usable yet: nothing to filter by
  if (!locationId || !species) {
    return <Input disabled value="" placeholder="Select a location and species first" data-testid={testId} />;
  }

  // Fallback: plain text input + warning (events must always be saveable)
  if (failed) {
    return (
      <div className="space-y-1">
        <Input
          value={value || ''}
          onChange={function (e) { onChange(e.target.value); }}
          placeholder="Enter tag numbers (comma-separated for multiple)"
          data-testid={testId}
        />
        <p className="text-xs text-amber-600">Could not load animals — enter tags manually</p>
      </div>
    );
  }

  if (animals === null) {
    return <Skeleton className="h-10 w-full" data-testid={testId ? `${testId}-loading` : undefined} />;
  }

  const catId = categoryId ? Number(categoryId) : null;
  const items = animals.filter(function (a) {
    if (catId && a.category_id !== catId) return false;
    if (sex && a.sex !== sex) return false;
    return true;
  });
  const atMax = Boolean(maxSelect) && selected.length >= maxSelect;

  function emit(next) {
    onChange(next.join(', '));
  }

  function toggle(tag) {
    if (selected.includes(tag)) {
      emit(selected.filter(function (t) { return t !== tag; }));
    } else if (maxSelect === 1) {
      emit([tag]);
      setOpen(false);
    } else if (!atMax) {
      emit(selected.concat(tag));
    }
  }

  function removeChip(e, tag) {
    e.stopPropagation();
    emit(selected.filter(function (t) { return t !== tag; }));
  }

  function clearAll(e) {
    e.stopPropagation();
    emit([]);
  }

  return (
    <div className="space-y-1" data-testid={testId}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <div
            role="combobox"
            aria-expanded={open}
            tabIndex={0}
            onKeyDown={function (e) {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setOpen(function (o) { return !o; });
              }
            }}
            className={cn(
              'flex min-h-10 w-full cursor-pointer flex-wrap items-center gap-1.5 rounded-md border border-input',
              'bg-background px-2 py-1.5 text-sm ring-offset-background',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
            )}
          >
            {selected.map(function (tag) {
              return (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 font-mono text-xs font-medium"
                >
                  {tag}
                  <button
                    type="button"
                    aria-label={`Remove ${tag}`}
                    onClick={function (e) { removeChip(e, tag); }}
                    className="rounded-full hover:text-destructive"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              );
            })}
            {!atMax && (
              <span className="px-1 text-muted-foreground">
                {selected.length === 0 ? placeholder : 'Add more...'}
              </span>
            )}
            {selected.length > 0 && (
              <button
                type="button"
                aria-label="Clear all selected animals"
                onClick={clearAll}
                className="ml-auto rounded-full p-0.5 text-muted-foreground hover:text-destructive"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-[18rem] p-0" align="start">
          <Command>
            <CommandInput placeholder={placeholder} />
            <CommandList>
              {items.length === 0 ? (
                <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                  No active animals found at this location
                </p>
              ) : (
                <>
                  <CommandEmpty>No matching animals</CommandEmpty>
                  {items.map(function (a) {
                    const isSelected = selected.includes(a.tag_number);
                    return (
                      <CommandItem
                        key={a.id}
                        value={`${a.tag_number} ${a.name || ''} ${a.category_name_sw || ''}${a.is_temp_tag ? ' temp' : ''}`}
                        onSelect={function () { toggle(a.tag_number); }}
                        disabled={!isSelected && atMax}
                        data-testid={`animal-option-${a.id}`}
                      >
                        <Check className={cn('mr-2 h-4 w-4', isSelected ? 'opacity-100' : 'opacity-0')} />
                        <span className="font-semibold">{a.tag_number}</span>
                        {a.is_temp_tag && (
                          <Badge
                            className="ml-2 rounded-full border-transparent bg-amber-100 px-1.5 py-0 text-[10px] font-semibold text-amber-800 shadow-none hover:bg-amber-100"
                            data-testid={`temp-badge-${a.id}`}
                          >
                            ⚠ Temp
                          </Badge>
                        )}
                        {a.name && <span className="ml-2 text-muted-foreground">{a.name}</span>}
                        {a.category_name_sw && (
                          <span className="ml-auto pl-2 text-xs text-muted-foreground">{a.category_name_sw}</span>
                        )}
                      </CommandItem>
                    );
                  })}
                </>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {selected.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {selected.length} animal{selected.length !== 1 ? 's' : ''} selected
        </p>
      )}
    </div>
  );
}

export default AnimalTagPicker;
