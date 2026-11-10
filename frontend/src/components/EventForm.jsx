import React from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Badge } from './ui/badge';
import AnimalTagPicker, { parseTags } from './AnimalTagPicker';
import { Plus, Trash, X } from '@phosphor-icons/react';
import { SPECIES_CONFIG, EVENT_TYPES } from '../lib/utils';
import { format } from 'date-fns';

// Shared event form: used by New Daily Log and by the Add/Edit event dialogs on the log detail page.

export const EVENT_TYPE_OPTIONS = [
  { value: 'birth', label: 'Birth' },
  { value: 'death', label: 'Death' },
  { value: 'sold', label: 'Sold' },
  { value: 'missing', label: 'Missing' },
  { value: 'gift_in', label: 'Gift In' },
  { value: 'gift_out', label: 'Gift Out' },
  { value: 'bought', label: 'Bought' },
  { value: 'transfer', label: 'Transfer' },
  { value: 'category_change', label: 'Category Change' },
  { value: 'abortion', label: 'Abortion (Note)' },
  { value: 'pd_test', label: 'PD Test (Non-stock)' },
  { value: 'service', label: 'Service / Mating (Non-stock)' },
];

// Event types whose animals already exist in the register -> searchable picker.
// bought / gift_in (animals not registered yet) and birth keep the plain text input.
const PICKER_EVENT_TYPES = ['death', 'sold', 'missing', 'gift_out', 'transfer', 'category_change', 'weaning', 'abortion', 'pd_test', 'service'];

const ABORTION_STAGES = [
  { value: 'early', label: 'Early (0-3 months)' },
  { value: 'mid', label: 'Mid (3-6 months)' },
  { value: 'late', label: 'Late (6-9 months)' }
];

// Offspring tags string sent to the backend: real tags as typed, untagged rows as empty entries
// ("KK-001, , KK-003"). When EVERY row is untagged the string is blank, so the backend creates
// `count` temp-tag animals (and an edited Count is respected).
export function buildOffspringTags(rows) {
  if (rows.every(function(r) { return !r.has_tag; })) return '';
  return rows.map(function(r) { return r.has_tag ? r.tag.trim() : ''; }).join(', ');
}

function OffspringEntries({ event, index, locationName, logDate, onPatch }) {
  const rows = event.offspring_rows && event.offspring_rows.length > 0
    ? event.offspring_rows
    : [{ has_tag: true, tag: '' }];
  const allTemp = rows.every(function(r) { return !r.has_tag; });
  const countNum = parseInt(event.count, 10) || 0;
  const prefix = (locationName || '').replace(/[^A-Za-z0-9]/g, '').slice(0, 3).toUpperCase() || 'UNK';
  const example = `TEMP-${prefix}-${format(logDate, 'yyyyMMdd')}-001 (example)`;

  // Count follows the number of rows only when rows are added/removed (so typing never overwrites it)
  function commit(nextRows, resizeCount) {
    const patch = { offspring_rows: nextRows, offspring_tags: buildOffspringTags(nextRows) };
    if (resizeCount) patch.count = nextRows.length;
    onPatch(index, patch);
  }
  function setRow(i, change) {
    commit(rows.map(function(r, k) { return k === i ? { ...r, ...change } : r; }), false);
  }

  return (
    <div className="space-y-2" data-testid={`offspring-entries-${index}`}>
      {rows.map(function(row, i) {
        return (
          <div key={i} className="flex items-center gap-2" data-testid={`offspring-row-${index}-${i}`}>
            <div className="flex shrink-0 rounded-md border border-input p-0.5">
              <Button
                type="button"
                size="sm"
                variant={row.has_tag ? 'default' : 'ghost'}
                className="h-7 px-2 text-xs"
                onClick={function() { setRow(i, { has_tag: true }); }}
                data-testid={`offspring-has-tag-${index}-${i}`}
              >
                Has tag
              </Button>
              <Button
                type="button"
                size="sm"
                variant={!row.has_tag ? 'default' : 'ghost'}
                className="h-7 px-2 text-xs"
                onClick={function() { setRow(i, { has_tag: false }); }}
                data-testid={`offspring-no-tag-${index}-${i}`}
              >
                No tag yet
              </Button>
            </div>
            {row.has_tag ? (
              <Input
                value={row.tag}
                onChange={function(e) { setRow(i, { tag: e.target.value }); }}
                placeholder="Newborn tag number"
                data-testid={`offspring-tag-${index}-${i}`}
              />
            ) : allTemp ? (
              <span className="flex-1 text-xs text-muted-foreground">Temp tag</span>
            ) : (
              <Input
                disabled
                value=""
                placeholder={example}
                title="Temp tag will be auto-generated"
                data-testid={`offspring-temp-${index}-${i}`}
              />
            )}
            {i === 0 ? (
              <span className="h-9 w-9 shrink-0" aria-hidden="true" />
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0"
                aria-label={`Remove offspring ${i + 1}`}
                onClick={function() { commit(rows.filter(function(_, k) { return k !== i; }), true); }}
                data-testid={`offspring-remove-${index}-${i}`}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        );
      })}
      {allTemp && (
        <p className="text-xs text-amber-700" data-testid={`offspring-temp-note-${index}`}>
          {countNum > 0
            ? `${countNum} temp tag${countNum !== 1 ? 's' : ''} will be auto-generated based on count (e.g. ${example.replace(' (example)', '')})`
            : 'Set a count above 0 to auto-generate temp tags'}
        </p>
      )}
      {!allTemp && rows.some(function(r) { return !r.has_tag; }) && (
        <p className="text-xs text-muted-foreground">Temp tag will be auto-generated for “No tag yet” rows</p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={function() { commit(rows.concat({ has_tag: true, tag: '' }), true); }}
        data-testid={`offspring-add-${index}`}
      >
        <Plus className="h-3 w-3" />
        Add offspring
      </Button>
    </div>
  );
}

export function EventFormItem({ event, index, categories, locations, diseases, locationId, logDate, onUpdate, onPatch, onRemove, mode = 'create', deathCauses = [] }) {
  const editing = mode === 'edit';
  // Editing a past event: its animals may no longer be active (sold, dead), so list every status.
  const pickerStatus = editing ? null : 'active';
  const causeOptions = deathCauses.filter(function(c) { return c.is_active || String(c.id) === String(event.cause_of_death_id); });
  const selectedCause = causeOptions.find(function(c) {
    return event.cause_of_death_id ? String(c.id) === String(event.cause_of_death_id) : (event.cause_of_death && c.name.toLowerCase() === event.cause_of_death.toLowerCase());
  });
  const isDiseaseCause = selectedCause ? selectedCause.name.toLowerCase() === 'disease' : (event.cause_of_death || '').toLowerCase() === 'disease';
  const speciesCategories = categories[event.species] || [];
  const eventType = event.event_type;
  const usePicker = PICKER_EVENT_TYPES.includes(eventType);
  const logLocation = locations.find(function(l) { return String(l.id) === String(locationId); });
  // Animals being transferred live at the source location; otherwise the log's location.
  const pickerLocationId = eventType === 'transfer' ? (event.from_location_id || locationId) : locationId;
  // An auto-filled category must not narrow the picker, or animals of other categories could not be added.
  const pickerCategoryId = eventType === 'category_change'
    ? event.from_category_id
    : (event.category_auto_filled ? '' : event.category_id);
  const autoFilled = Boolean(event.category_auto_filled);

  // Picking animals fills Count with the number picked (still editable afterwards).
  function handlePickedTags(next) {
    const n = parseTags(next).length;
    onPatch(index, n > 0 ? { animal_tags: next, count: n } : { animal_tags: next });
  }

  // Picked animals that all share one category fill (and lock) the Category field.
  // Mixed categories or an empty selection release an auto-filled value; a manual choice is left alone.
  function handleAnimalsPicked(picked) {
    if (eventType === 'category_change' || eventType === 'abortion') return;
    const ids = Array.from(new Set(picked.map(function(a) { return a.category_id; })));
    if (ids.length === 1) {
      onPatch(index, { category_id: String(ids[0]), category_auto_filled: true });
    } else if (autoFilled) {
      onPatch(index, { category_id: '', category_auto_filled: false });
    }
  }
  return (
    <div className="p-4 rounded-lg border border-border bg-muted/30 space-y-4" data-testid={`event-${index}`}>
      {onRemove && (
        <div className="flex items-center justify-between">
          <Badge className={EVENT_TYPES[eventType]?.color}>
            Event {index + 1}: {EVENT_TYPE_OPTIONS.find(e => e.value === eventType)?.label}
          </Badge>
          <Button variant="ghost" size="icon" onClick={() => onRemove(index)} data-testid={`remove-event-${index}`}>
            <Trash className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="space-y-2">
          <Label>Event Type</Label>
          <Select value={eventType} onValueChange={(v) => onUpdate(index, 'event_type', v)}>
            <SelectTrigger data-testid={`event-type-${index}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {EVENT_TYPE_OPTIONS.map(function(opt) {
                return <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>;
              })}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Species</Label>
          <Select value={event.species} onValueChange={(v) => onUpdate(index, 'species', v)}>
            <SelectTrigger data-testid={`species-${index}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(SPECIES_CONFIG).map(function([key, config]) {
                return <SelectItem key={key} value={key}>{config.label}</SelectItem>;
              })}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Count</Label>
          <Input
            type="number"
            min="0"
            value={event.count}
            onChange={(e) => onUpdate(index, 'count', e.target.value)}
            data-testid={`count-${index}`}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Animal Tag(s)</Label>
        {usePicker ? (
          <AnimalTagPicker
            locationId={pickerLocationId}
            species={event.species}
            categoryId={pickerCategoryId}
            sex={['pd_test', 'service', 'abortion'].includes(eventType) ? 'female' : undefined}
            value={event.animal_tags || ''}
            onChange={handlePickedTags}
            onAnimalsPicked={handleAnimalsPicked}
            testId={`tags-${index}`}
            status={pickerStatus}
          />
        ) : (
          <Input
            value={event.animal_tags || ''}
            onChange={(e) => onUpdate(index, 'animal_tags', e.target.value)}
            placeholder="Enter tag numbers (comma-separated for multiple)"
            data-testid={`tags-${index}`}
          />
        )}
        {!usePicker && (eventType === 'bought' || eventType === 'gift_in') && (
          <p className="text-xs text-muted-foreground">New arrivals are not in the register yet, so enter their tags by hand.</p>
        )}
      </div>

      {!['category_change', 'abortion', 'pd_test', 'service'].includes(eventType) && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Label>Category</Label>
            {autoFilled && (
              <>
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0" data-testid={`category-auto-badge-${index}`}>
                  auto-filled
                </Badge>
                <button
                  type="button"
                  className="text-xs text-muted-foreground underline"
                  onClick={() => onPatch(index, { category_auto_filled: false })}
                  data-testid={`category-override-${index}`}
                >
                  Override
                </button>
              </>
            )}
          </div>
          <Select
            value={event.category_id?.toString() || ''}
            onValueChange={(v) => onUpdate(index, 'category_id', v)}
            disabled={autoFilled}
          >
            <SelectTrigger data-testid={`category-${index}`}>
              <SelectValue placeholder="Select category" />
            </SelectTrigger>
            <SelectContent>
              {speciesCategories.map(function(cat) {
                return (
                  <SelectItem key={cat.id} value={cat.id.toString()}>
                    {cat.name_sw} ({cat.name_en})
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
      )}

      {eventType === 'pd_test' && (
        <div className="grid grid-cols-1 gap-4 rounded-lg bg-pink-50 p-3 md:grid-cols-2">
          <div className="space-y-2"><Label>PD result</Label>
            <Select value={event.pd_result || ''} onValueChange={(v) => onUpdate(index, 'pd_result', v)}>
              <SelectTrigger data-testid={`pd-result-${index}`}><SelectValue placeholder="Select result" /></SelectTrigger>
              <SelectContent><SelectItem value="pregnant">Pregnant / positive</SelectItem><SelectItem value="open">Open / not pregnant</SelectItem></SelectContent>
            </Select>
          </div>
          {event.pd_result === 'pregnant' && <div className="space-y-2"><Label>Months pregnant (optional)</Label>
            <Input type="number" min="0" max="12" step="1" value={event.months_pregnant ?? ''} onChange={(e) => onUpdate(index, 'months_pregnant', e.target.value)} data-testid={`pd-months-${index}`} />
          </div>}
        </div>
      )}
      {['pd_test', 'service'].includes(eventType) && <p className="text-sm text-muted-foreground">Select female animal tags to update their reproductive records. This event does not change stock.</p>}

      {/* Death-specific fields */}
      {eventType === 'death' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-3 bg-red-50 rounded-lg">
          <div className="space-y-2">
            <Label>Cause of Death</Label>
            <Select
              value={selectedCause ? String(selectedCause.id) : ''}
              onValueChange={(v) => {
                const cause = causeOptions.find(function(c) { return String(c.id) === v; });
                onPatch(index, { cause_of_death_id: v, cause_of_death: cause ? cause.name : '' });
              }}
            >
              <SelectTrigger data-testid={`cause-${index}`}>
                <SelectValue placeholder={event.cause_of_death && !selectedCause ? event.cause_of_death : 'Select cause'} />
              </SelectTrigger>
              <SelectContent>
                {causeOptions.map(function(cause) {
                  return <SelectItem key={cause.id} value={String(cause.id)}>{cause.name}{cause.is_active ? '' : ' (inactive)'}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          {isDiseaseCause && (
            <div className="space-y-2">
              <Label>Specific Disease</Label>
              <Select 
                value={event.disease_id?.toString() || ''} 
                onValueChange={(v) => onUpdate(index, 'disease_id', v)}
              >
                <SelectTrigger data-testid={`disease-${index}`}>
                  <SelectValue placeholder="Select disease" />
                </SelectTrigger>
                <SelectContent>
                  {diseases.map(function(disease) {
                    return <SelectItem key={disease.id} value={disease.id.toString()}>{disease.name}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-2">
            <Label>Days Sick</Label>
            <Input
              type="number"
              min="0"
              value={event.days_sick || ''}
              onChange={(e) => onUpdate(index, 'days_sick', e.target.value)}
              placeholder="0"
              data-testid={`days-sick-${index}`}
            />
          </div>
          <div className="space-y-2">
            <Label>Attending Vet/DK</Label>
            <Input
              value={event.attending_vet || ''}
              onChange={(e) => onUpdate(index, 'attending_vet', e.target.value)}
              placeholder="Vet name"
              data-testid={`vet-${index}`}
            />
          </div>
        </div>
      )}

      {/* Birth-specific fields */}
      {eventType === 'birth' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 bg-green-50 rounded-lg">
          <div className="space-y-2">
            <Label>Mother Tag (Dam)</Label>
            <AnimalTagPicker
              locationId={locationId}
              species={event.species}
              sex="female"
              maxSelect={1}
              value={event.mother_tag || ''}
              onChange={(v) => onUpdate(index, 'mother_tag', v)}
              placeholder="Search dam by tag or name..."
              testId={`mother-tag-${index}`}
              status={pickerStatus}
            />
          </div>
          <div className="space-y-2">
            <Label>Offspring Tag(s)</Label>
            <OffspringEntries
              event={event}
              index={index}
              locationName={logLocation ? logLocation.name : ''}
              logDate={logDate}
              onPatch={onPatch}
            />
          </div>
        </div>
      )}

      {/* Sale-specific fields */}
      {eventType === 'sold' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 bg-blue-50 rounded-lg">
          <div className="space-y-2">
            <Label>Buyer Name</Label>
            <Input
              value={event.buyer_name || ''}
              onChange={(e) => onUpdate(index, 'buyer_name', e.target.value)}
              placeholder="Buyer's full name"
              data-testid={`buyer-name-${index}`}
            />
          </div>
          <div className="space-y-2">
            <Label>Buyer Phone</Label>
            <Input
              value={event.buyer_phone || ''}
              onChange={(e) => onUpdate(index, 'buyer_phone', e.target.value)}
              placeholder="Phone number"
              data-testid={`buyer-phone-${index}`}
            />
          </div>
          <div className="space-y-2">
            <Label>Buyer Address</Label>
            <Input
              value={event.buyer_address || ''}
              onChange={(e) => onUpdate(index, 'buyer_address', e.target.value)}
              placeholder="Address"
              data-testid={`buyer-address-${index}`}
            />
          </div>
          <div className="space-y-2">
            <Label>Sale Price (TZS)</Label>
            <Input
              type="number"
              min="0"
              value={event.sale_price || ''}
              onChange={(e) => onUpdate(index, 'sale_price', e.target.value)}
              placeholder="Price per animal"
              data-testid={`sale-price-${index}`}
            />
          </div>
        </div>
      )}

      {/* Transfer fields */}
      {eventType === 'transfer' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 bg-orange-50 rounded-lg">
          <div className="space-y-2">
            <Label>From Location</Label>
            <Select 
              value={event.from_location_id?.toString() || ''} 
              onValueChange={(v) => onUpdate(index, 'from_location_id', v)}
            >
              <SelectTrigger data-testid={`from-location-${index}`}>
                <SelectValue placeholder="Source location" />
              </SelectTrigger>
              <SelectContent>
                {locations.map(function(loc) {
                  return <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>To Location</Label>
            <Select 
              value={event.to_location_id?.toString() || ''} 
              onValueChange={(v) => onUpdate(index, 'to_location_id', v)}
            >
              <SelectTrigger data-testid={`to-location-${index}`}>
                <SelectValue placeholder="Destination location" />
              </SelectTrigger>
              <SelectContent>
                {locations.map(function(loc) {
                  return <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Category Change fields */}
      {eventType === 'category_change' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 bg-indigo-50 rounded-lg">
          <div className="space-y-2">
            <Label>From Category</Label>
            <Select 
              value={event.from_category_id?.toString() || ''} 
              onValueChange={(v) => onUpdate(index, 'from_category_id', v)}
            >
              <SelectTrigger data-testid={`from-category-${index}`}>
                <SelectValue placeholder="Source category" />
              </SelectTrigger>
              <SelectContent>
                {speciesCategories.map(function(cat) {
                  return <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>To Category</Label>
            <Select 
              value={event.to_category_id?.toString() || ''} 
              onValueChange={(v) => onUpdate(index, 'to_category_id', v)}
            >
              <SelectTrigger data-testid={`to-category-${index}`}>
                <SelectValue placeholder="Destination category" />
              </SelectTrigger>
              <SelectContent>
                {speciesCategories.map(function(cat) {
                  return <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Abortion-specific fields */}
      {eventType === 'abortion' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 bg-amber-50 rounded-lg">
          <div className="space-y-2">
            <Label>Abortion Stage</Label>
            <Select 
              value={event.abortion_stage || ''} 
              onValueChange={(v) => onUpdate(index, 'abortion_stage', v)}
            >
              <SelectTrigger data-testid={`abortion-stage-${index}`}>
                <SelectValue placeholder="Select stage" />
              </SelectTrigger>
              <SelectContent>
                {ABORTION_STAGES.map(function(stage) {
                  return <SelectItem key={stage.value} value={stage.value}>{stage.label}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Mother Tag (Optional)</Label>
            <AnimalTagPicker
              locationId={locationId}
              species={event.species}
              sex="female"
              maxSelect={1}
              value={event.mother_tag || ''}
              onChange={(v) => onUpdate(index, 'mother_tag', v)}
              placeholder="Search dam by tag or name..."
              testId={`abortion-mother-tag-${index}`}
              status={pickerStatus}
            />
          </div>
        </div>
      )}

      {/* Gift fields: the create endpoint does not accept them, so they are editable after saving only */}
      {editing && (eventType === 'gift_in' || eventType === 'gift_out') && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 bg-purple-50 rounded-lg">
          <div className="space-y-2">
            <Label>{eventType === 'gift_in' ? 'Received From' : 'Given To'}</Label>
            <Input
              value={event.gift_party_name || ''}
              onChange={(e) => onUpdate(index, 'gift_party_name', e.target.value)}
              placeholder="Name"
              data-testid={`gift-party-name-${index}`}
            />
          </div>
          <div className="space-y-2">
            <Label>Phone</Label>
            <Input
              value={event.gift_party_phone || ''}
              onChange={(e) => onUpdate(index, 'gift_party_phone', e.target.value)}
              placeholder="Phone number"
              data-testid={`gift-party-phone-${index}`}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Reason</Label>
            <Input
              value={event.gift_reason || ''}
              onChange={(e) => onUpdate(index, 'gift_reason', e.target.value)}
              placeholder="Reason for the gift"
              data-testid={`gift-reason-${index}`}
            />
          </div>
        </div>
      )}

      <div className="space-y-2">
        <Label>Notes (Optional)</Label>
        <Input
          value={event.notes || ''}
          onChange={(e) => onUpdate(index, 'notes', e.target.value)}
          placeholder="Additional details..."
          data-testid={`notes-${index}`}
        />
      </div>
    </div>
  );
}


export function blankEvent() {
  return {
    event_type: 'birth',
    species: 'cattle',
    category_id: '',
    category_auto_filled: false,
    count: 1,
    from_location_id: '',
    to_location_id: '',
    from_category_id: '',
    to_category_id: '',
    notes: '',
    is_stock_event: true,
    animal_tags: '',
    cause_of_death_id: '',
    cause_of_death: '',
    disease_id: '',
    days_sick: '',
    attending_vet: '',
    abortion_stage: '',
    pd_result: '',
    months_pregnant: '',
    mother_tag: '',
    offspring_tags: '',
    offspring_rows: [{ has_tag: true, tag: '' }],
    buyer_name: '',
    buyer_phone: '',
    buyer_address: '',
    sale_price: '',
    gift_party_name: '',
    gift_party_phone: '',
    gift_reason: '',
  };
}

// Pure version of the field-change rules (type/species changes reset dependent fields).
export function applyEventChange(event, field, value) {
  const next = { ...event, [field]: value };
  if (field === 'pd_result' && value === 'open') next.months_pregnant = '';
  if (field === 'category_id') next.category_auto_filled = false;
  if (field === 'event_type' || field === 'species') {
    // Tags are cleared or re-validated by these changes, so an auto-filled category no longer applies
    if (next.category_auto_filled) next.category_id = '';
    next.category_auto_filled = false;
  }
  if (field === 'event_type') {
    next.is_stock_event = !['abortion', 'pd_test', 'service'].includes(value);
    const fieldsByType = {
      death: ['cause_of_death_id', 'cause_of_death', 'disease_id', 'days_sick', 'attending_vet'],
      birth: ['mother_tag', 'offspring_tags'],
      sold: ['buyer_name', 'buyer_phone', 'buyer_address', 'sale_price'],
      gift_in: ['gift_party_name', 'gift_party_phone', 'gift_reason'],
      gift_out: ['gift_party_name', 'gift_party_phone', 'gift_reason'],
      abortion: ['abortion_stage', 'mother_tag'],
      pd_test: ['pd_result', 'months_pregnant'],
    };
    const allowed = fieldsByType[value] || [];
    Object.values(fieldsByType).flat().forEach((key) => {
      if (!allowed.includes(key)) next[key] = '';
    });
    if (value !== 'birth') next.offspring_rows = [{ has_tag: true, tag: '' }];
    if (value !== 'transfer') {
      next.from_location_id = '';
      next.to_location_id = '';
    }
    if (value !== 'category_change') {
      next.from_category_id = '';
      next.to_category_id = '';
    }
  }
  if (field === 'species') {
    next.category_id = '';
    next.from_category_id = '';
    next.to_category_id = '';
    // Registry-backed tags belong to the old species: clear them so a cow tag cannot stay on a goat event
    if (PICKER_EVENT_TYPES.includes(next.event_type)) next.animal_tags = '';
    if (next.event_type === 'birth' || next.event_type === 'abortion') next.mother_tag = '';
  }
  return next;
}

// API event -> form state (ids as strings, offspring tags split into rows).
export function eventFromApi(e) {
  const str = (v) => (v === null || v === undefined ? '' : String(v));
  const hasTags = (e.offspring_tags || '').trim() !== '';
  let rows;
  if (hasTags) {
    rows = e.offspring_tags.split(',').map((t) => ({ has_tag: t.trim() !== '', tag: t.trim() }));
  } else if (e.event_type === 'birth' && e.count > 0) {
    rows = Array.from({ length: e.count }, () => ({ has_tag: false, tag: '' }));
  } else {
    rows = [{ has_tag: true, tag: '' }];
  }
  return {
    ...blankEvent(),
    event_type: e.event_type,
    species: e.species,
    category_id: str(e.category_id),
    count: e.count,
    from_location_id: str(e.from_location_id),
    to_location_id: str(e.to_location_id),
    from_category_id: str(e.from_category_id),
    to_category_id: str(e.to_category_id),
    notes: e.notes || '',
    is_stock_event: e.is_stock_event,
    animal_tags: e.animal_tags || '',
    cause_of_death_id: str(e.cause_of_death_id),
    cause_of_death: e.cause_of_death || '',
    disease_id: str(e.disease_id),
    days_sick: str(e.days_sick),
    attending_vet: e.attending_vet || '',
    abortion_stage: e.abortion_stage || '',
    pd_result: e.pd_result || '',
    months_pregnant: str(e.months_pregnant),
    mother_tag: e.mother_tag || '',
    offspring_tags: e.offspring_tags || '',
    offspring_rows: rows,
    buyer_name: e.buyer_name || '',
    buyer_phone: e.buyer_phone || '',
    buyer_address: e.buyer_address || '',
    sale_price: str(e.sale_price),
    gift_party_name: e.gift_party_name || '',
    gift_party_phone: e.gift_party_phone || '',
    gift_reason: e.gift_reason || '',
  };
}

// Returns an error message, or null when the event is valid.
export function validateEvent(event) {
  if (event.event_type === 'pd_test') {
    if (!['pregnant', 'open'].includes(event.pd_result)) return 'Select a PD result';
    const months = Number(event.months_pregnant);
    if (event.pd_result === 'pregnant' && event.months_pregnant !== '' && (!Number.isInteger(months) || months < 0 || months > 12)) return 'Months pregnant must be a whole number from 0 to 12';
  }
  if (event.event_type === 'birth') {
    const rows = event.offspring_rows || [];
    for (let r = 0; r < rows.length; r++) {
      if (rows[r].has_tag && !rows[r].tag.trim()) return `Offspring ${r + 1} needs a tag number, or choose "No tag yet"`;
      if (rows[r].has_tag && rows[r].tag.includes(',')) return `Offspring ${r + 1} tag cannot contain a comma`;
    }
  }
  if (event.event_type === 'transfer') {
    if (!event.from_location_id || !event.to_location_id) return 'Transfer requires both source and destination locations';
    if (!event.category_id) return 'Please select a category';
  } else if (event.event_type === 'category_change') {
    if (!event.from_category_id || !event.to_category_id) return 'Category change requires both source and destination categories';
  } else if (!['abortion', 'pd_test', 'service'].includes(event.event_type)) {
    if (!event.category_id) return 'Please select a category';
  }
  return null;
}

const toInt = (v) => (v ? parseInt(v, 10) : null);

// Payload for POST (new log or add-event): unset fields are null.
export function eventToCreatePayload(e) {
  return {
    event_type: e.event_type,
    species: e.species,
    category_id: toInt(e.category_id),
    count: parseInt(e.count, 10) || 0,
    from_location_id: toInt(e.from_location_id),
    to_location_id: toInt(e.to_location_id),
    from_category_id: toInt(e.from_category_id),
    to_category_id: toInt(e.to_category_id),
    notes: e.notes || null,
    is_stock_event: e.is_stock_event,
    animal_tags: e.animal_tags || null,
    cause_of_death_id: toInt(e.cause_of_death_id),
    cause_of_death: e.cause_of_death || null,
    disease_id: toInt(e.disease_id),
    days_sick: toInt(e.days_sick),
    attending_vet: e.attending_vet || null,
    abortion_stage: e.abortion_stage || null,
    pd_result: e.event_type === 'pd_test' ? (e.pd_result || null) : null,
    months_pregnant: e.event_type === 'pd_test' && e.pd_result === 'pregnant' && e.months_pregnant !== '' ? Number(e.months_pregnant) : null,
    mother_tag: e.mother_tag || null,
    offspring_tags: e.offspring_tags || null,
    buyer_name: e.buyer_name || null,
    buyer_phone: e.buyer_phone || null,
    buyer_address: e.buyer_address || null,
    sale_price: toInt(e.sale_price),
    gift_party_name: e.gift_party_name || null,
    gift_party_phone: e.gift_party_phone || null,
    gift_reason: e.gift_reason || null,
  };
}

// Payload for PUT. The endpoint ignores nulls and rejects type-specific fields that do not belong to the
// event's type, so only the event's own fields are sent; text fields go as '' so they can be cleared.
export function eventToUpdatePayload(e) {
  const payload = {
    event_type: e.event_type,
    species: e.species,
    count: parseInt(e.count, 10) || 0,
    notes: e.notes || '',
    animal_tags: e.animal_tags || '',
  };
  ['category_id', 'from_location_id', 'to_location_id', 'from_category_id', 'to_category_id'].forEach((k) => {
    if (e[k]) payload[k] = parseInt(e[k], 10);
  });
  const type = e.event_type;
  if (type === 'pd_test') {
    payload.pd_result = e.pd_result;
    payload.months_pregnant = e.pd_result === 'pregnant' && e.months_pregnant !== '' ? Number(e.months_pregnant) : null;
  } else if (type === 'death') {
    payload.cause_of_death_id = toInt(e.cause_of_death_id);
    payload.cause_of_death = e.cause_of_death || '';
    payload.attending_vet = e.attending_vet || '';
    if (e.disease_id) payload.disease_id = parseInt(e.disease_id, 10);
    if (e.days_sick) payload.days_sick = parseInt(e.days_sick, 10);
  } else if (type === 'birth') {
    payload.mother_tag = e.mother_tag || '';
    payload.offspring_tags = buildOffspringTags(e.offspring_rows || []);
  } else if (type === 'sold') {
    payload.buyer_name = e.buyer_name || '';
    payload.buyer_phone = e.buyer_phone || '';
    payload.buyer_address = e.buyer_address || '';
    if (e.sale_price) payload.sale_price = parseInt(e.sale_price, 10);
  } else if (type === 'gift_in' || type === 'gift_out') {
    payload.gift_party_name = e.gift_party_name || '';
    payload.gift_party_phone = e.gift_party_phone || '';
    payload.gift_reason = e.gift_reason || '';
  } else if (type === 'abortion') {
    if (e.abortion_stage) payload.abortion_stage = e.abortion_stage;
    payload.mother_tag = e.mother_tag || '';
  }
  return payload;
}
