import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from './ui/command';
import { Button } from './ui/button';
import { CaretUpDown, Check, Spinner, WarningCircle, ArrowClockwise, X } from '@phosphor-icons/react';
import { searchRegistryTags } from '../lib/api';

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 300;

/**
 * Combobox over the Herd Tag Registry (GET /api/integration/registry/tags), for picking
 * a specific animal by tag rather than typing a tag number free-hand.
 *
 * value / onChange hold/emit { tag_id, status, category, location } | null.
 */
function RegistryTagPicker({
  species,
  location,
  category,
  value,
  onChange,
  placeholder = 'Search Herd Tag Registry…',
  disabled = false,
  ...triggerProps
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState('idle'); // idle | loading | error | ready
  const requestIdRef = useRef(0);

  const runSearch = useCallback(async (q) => {
    const requestId = ++requestIdRef.current;
    setStatus('loading');
    try {
      const res = await searchRegistryTags({
        q,
        species: species || undefined,
        location: location || undefined,
        category: category || undefined,
        limit: 20,
      });
      if (requestId !== requestIdRef.current) return; // a newer search superseded this one
      const items = Array.isArray(res.data) ? res.data : (res.data?.items || []);
      setResults(items);
      setStatus('ready');
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setResults([]);
      setStatus('error');
    }
  }, [species, location, category]);

  useEffect(() => {
    if (!open) return undefined;

    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      requestIdRef.current += 1; // invalidate any in-flight search
      setStatus('idle');
      setResults([]);
      return undefined;
    }

    const handle = setTimeout(() => { runSearch(trimmed); }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query, open, runSearch]);

  function handleSelect(tag) {
    onChange({
      tag_id: tag.tag_id,
      status: tag.status,
      category: tag.category,
      location: tag.location,
    });
    setOpen(false);
    setQuery('');
  }

  function handleClear(e) {
    e.stopPropagation();
    onChange(null);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="w-full justify-between font-normal"
          {...triggerProps}
        >
          {value ? (
            <span className="flex items-center gap-2 truncate">
              <span className="font-mono text-sm">{value.tag_id}</span>
              {value.category && (
                <span className="text-muted-foreground text-xs truncate">· {value.category}</span>
              )}
            </span>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <span className="flex items-center gap-1 shrink-0">
            {value && (
              <X
                className="h-3.5 w-3.5 opacity-50 hover:opacity-100"
                onClick={handleClear}
              />
            )}
            <CaretUpDown className="h-4 w-4 opacity-50" />
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Type a tag number…"
          />
          <CommandList>
            {status === 'idle' && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Type at least {MIN_QUERY_LENGTH} characters to search
              </div>
            )}

            {status === 'loading' && (
              <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                <Spinner className="h-4 w-4 animate-spin" />
                Searching Herd Tag Registry…
              </div>
            )}

            {status === 'error' && (
              <div className="flex flex-col items-center gap-2 py-6 px-4 text-center">
                <WarningCircle className="h-5 w-5 text-destructive" />
                <p className="text-sm font-medium text-destructive">Herd Tag Registry is unreachable</p>
                <p className="text-xs text-muted-foreground">
                  We couldn't load tags right now. Check your connection and try again.
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="gap-2 mt-1"
                  onClick={() => runSearch(query.trim())}
                >
                  <ArrowClockwise className="h-3.5 w-3.5" />
                  Retry
                </Button>
              </div>
            )}

            {status === 'ready' && results.length === 0 && (
              <CommandEmpty>No matching tags</CommandEmpty>
            )}

            {status === 'ready' && results.length > 0 && (
              <CommandGroup>
                {results.map((tag) => (
                  <CommandItem
                    key={tag.tag_id}
                    value={tag.tag_id}
                    onSelect={() => handleSelect(tag)}
                    className="flex flex-col items-start gap-0.5 py-2"
                  >
                    <div className="flex items-center gap-2 w-full">
                      <span className="font-mono text-sm">{tag.tag_id}</span>
                      {value?.tag_id === tag.tag_id && <Check className="h-4 w-4 ml-auto text-primary" />}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {[tag.category, tag.location, tag.sex].filter(Boolean).join(' · ') || '—'}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export default RegistryTagPicker;
