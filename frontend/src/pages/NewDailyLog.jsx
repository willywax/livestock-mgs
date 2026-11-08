import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getLocations, getCategories, createDailyLog, getDiseases } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Badge } from '../components/ui/badge';
import { CalendarBlank, MapPin, Plus, Trash, ArrowLeft, CheckCircle } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { SPECIES_CONFIG, EVENT_TYPES } from '../lib/utils';
import { format } from 'date-fns';

const EVENT_TYPE_OPTIONS = [
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
];

const DEATH_CAUSES = [
  'Disease', 'Accident', 'Old Age', 'Predator Attack', 'Poisoning', 
  'Birthing Complications', 'Malnutrition', 'Unknown', 'Other'
];

const ABORTION_STAGES = [
  { value: 'early', label: 'Early (0-3 months)' },
  { value: 'mid', label: 'Mid (3-6 months)' },
  { value: 'late', label: 'Late (6-9 months)' }
];

function EventFormItem({ event, index, categories, locations, diseases, onUpdate, onRemove }) {
  const speciesCategories = categories[event.species] || [];
  const eventType = event.event_type;
  return (
    <div className="p-4 rounded-lg border border-border bg-muted/30 space-y-4" data-testid={`event-${index}`}>
      <div className="flex items-center justify-between">
        <Badge className={EVENT_TYPES[eventType]?.color}>
          Event {index + 1}: {EVENT_TYPE_OPTIONS.find(e => e.value === eventType)?.label}
        </Badge>
        <Button variant="ghost" size="icon" onClick={() => onRemove(index)} data-testid={`remove-event-${index}`}>
          <Trash className="h-4 w-4 text-destructive" />
        </Button>
      </div>

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
        <Input
          value={event.animal_tags || ''}
          onChange={(e) => onUpdate(index, 'animal_tags', e.target.value)}
          placeholder="Enter tag numbers (comma-separated for multiple)"
          data-testid={`tags-${index}`}
        />
      </div>

      {eventType !== 'category_change' && eventType !== 'abortion' && (
        <div className="space-y-2">
          <Label>Category</Label>
          <Select 
            value={event.category_id?.toString() || ''} 
            onValueChange={(v) => onUpdate(index, 'category_id', v)}
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

      {/* Death-specific fields */}
      {eventType === 'death' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-3 bg-red-50 rounded-lg">
          <div className="space-y-2">
            <Label>Cause of Death</Label>
            <Select 
              value={event.cause_of_death || ''} 
              onValueChange={(v) => onUpdate(index, 'cause_of_death', v)}
            >
              <SelectTrigger data-testid={`cause-${index}`}>
                <SelectValue placeholder="Select cause" />
              </SelectTrigger>
              <SelectContent>
                {DEATH_CAUSES.map(function(cause) {
                  return <SelectItem key={cause} value={cause}>{cause}</SelectItem>;
                })}
              </SelectContent>
            </Select>
          </div>
          {event.cause_of_death === 'Disease' && (
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
            <Input
              value={event.mother_tag || ''}
              onChange={(e) => onUpdate(index, 'mother_tag', e.target.value)}
              placeholder="Mother (dam) tag"
              data-testid={`mother-tag-${index}`}
            />
          </div>
          <div className="space-y-2">
            <Label>Offspring Tag(s)</Label>
            <Input
              value={event.offspring_tags || ''}
              onChange={(e) => onUpdate(index, 'offspring_tags', e.target.value)}
              placeholder="Newborn tag(s), comma-separated"
              data-testid={`offspring-tags-${index}`}
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
            <Input
              value={event.mother_tag || ''}
              onChange={(e) => onUpdate(index, 'mother_tag', e.target.value)}
              placeholder="Mother's tag number"
              data-testid={`abortion-mother-tag-${index}`}
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

function NewDailyLog() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedLocation = searchParams.get('location');

  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState({});
  const [diseases, setDiseases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [locationId, setLocationId] = useState(preselectedLocation || '');
  const [logDate, setLogDate] = useState(new Date());
  const [hasEvents, setHasEvents] = useState(true);
  const [notes, setNotes] = useState('');
  const [events, setEvents] = useState([]);

  useEffect(function() {
    loadData();
  }, []);

  async function loadData() {
    try {
      const locRes = await getLocations();
      const cattleRes = await getCategories('cattle');
      const sheepRes = await getCategories('sheep');
      const goatRes = await getCategories('goat');
      const diseaseRes = await getDiseases();
      
      setLocations(locRes.data);
      setCategories({
        cattle: cattleRes.data,
        sheep: sheepRes.data,
        goat: goatRes.data
      });
      setDiseases(diseaseRes.data);
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  function addEvent() {
    setEvents([...events, {
      event_type: 'birth',
      species: 'cattle',
      category_id: '',
      count: 1,
      from_location_id: '',
      to_location_id: '',
      from_category_id: '',
      to_category_id: '',
      notes: '',
      is_stock_event: true,
      animal_tags: '',
      cause_of_death: '',
      disease_id: '',
      days_sick: '',
      attending_vet: '',
      abortion_stage: '',
      mother_tag: '',
      offspring_tags: '',
      buyer_name: '',
      buyer_phone: '',
      buyer_address: '',
      sale_price: ''
    }]);
  }

  function updateEvent(index, field, value) {
    const newEvents = [...events];
    newEvents[index] = { ...newEvents[index], [field]: value };
    
    if (field === 'event_type') {
      newEvents[index].is_stock_event = value !== 'abortion';
      if (value !== 'transfer') {
        newEvents[index].from_location_id = '';
        newEvents[index].to_location_id = '';
      }
      if (value !== 'category_change') {
        newEvents[index].from_category_id = '';
        newEvents[index].to_category_id = '';
      }
    }
    
    if (field === 'species') {
      newEvents[index].category_id = '';
      newEvents[index].from_category_id = '';
      newEvents[index].to_category_id = '';
    }
    
    setEvents(newEvents);
  }

  function removeEvent(index) {
    setEvents(events.filter(function(_, i) { return i !== index; }));
  }

  async function handleSubmit() {
    if (!locationId) {
      toast.error('Please select a location');
      return;
    }

    if (hasEvents && events.length === 0) {
      toast.error('Please add at least one event or mark as "No events"');
      return;
    }

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      if (event.event_type === 'transfer') {
        if (!event.from_location_id || !event.to_location_id) {
          toast.error(`Event ${i + 1}: Transfer requires both source and destination locations`);
          return;
        }
        if (!event.category_id) {
          toast.error(`Event ${i + 1}: Please select a category`);
          return;
        }
      } else if (event.event_type === 'category_change') {
        if (!event.from_category_id || !event.to_category_id) {
          toast.error(`Event ${i + 1}: Category change requires both source and destination categories`);
          return;
        }
      } else if (event.event_type !== 'abortion') {
        if (!event.category_id) {
          toast.error(`Event ${i + 1}: Please select a category`);
          return;
        }
      }
    }

    setSaving(true);
    try {
      const payload = {
        location_id: parseInt(locationId),
        log_date: format(logDate, 'yyyy-MM-dd'),
        has_events: hasEvents && events.length > 0,
        notes: notes || null,
        events: events.map(function(e) {
          return {
            event_type: e.event_type,
            species: e.species,
            category_id: e.category_id ? parseInt(e.category_id) : null,
            count: parseInt(e.count) || 0,
            from_location_id: e.from_location_id ? parseInt(e.from_location_id) : null,
            to_location_id: e.to_location_id ? parseInt(e.to_location_id) : null,
            from_category_id: e.from_category_id ? parseInt(e.from_category_id) : null,
            to_category_id: e.to_category_id ? parseInt(e.to_category_id) : null,
            notes: e.notes || null,
            is_stock_event: e.is_stock_event,
            animal_tags: e.animal_tags || null,
            cause_of_death: e.cause_of_death || null,
            disease_id: e.disease_id ? parseInt(e.disease_id) : null,
            days_sick: e.days_sick ? parseInt(e.days_sick) : null,
            attending_vet: e.attending_vet || null,
            abortion_stage: e.abortion_stage || null,
            mother_tag: e.mother_tag || null,
            offspring_tags: e.offspring_tags || null,
            buyer_name: e.buyer_name || null,
            buyer_phone: e.buyer_phone || null,
            buyer_address: e.buyer_address || null,
            sale_price: e.sale_price ? parseInt(e.sale_price) : null
          };
        })
      };

      const response = await createDailyLog(payload);
      toast.success('Daily log created successfully');

      navigate('/daily-logs');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create daily log');
    } finally {
      setSaving(false);
    }
  }


  if (loading) {
    return <div className="flex items-center justify-center py-12">Loading...</div>;
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto" data-testid="new-daily-log-page">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={function() { navigate(-1); }}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="font-heading text-3xl font-bold">New Daily Log</h1>
          <p className="text-muted-foreground mt-1">Record daily stock events</p>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="font-heading flex items-center gap-2">
            <span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary text-primary-foreground text-sm">1</span>
            Location & Date
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Location</Label>
              <Select value={locationId} onValueChange={setLocationId}>
                <SelectTrigger data-testid="location-select">
                  <SelectValue placeholder="Select location" />
                </SelectTrigger>
                <SelectContent>
                  {locations.map(function(loc) {
                    return (
                      <SelectItem key={loc.id} value={loc.id.toString()}>
                        <div className="flex items-center gap-2">
                          <MapPin className="h-4 w-4" />
                          {loc.name}
                        </div>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Date</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="w-full justify-start gap-2" data-testid="date-select">
                    <CalendarBlank className="h-4 w-4" />
                    {format(logDate, 'PPP')}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={logDate}
                    onSelect={function(date) { if (date) setLogDate(date); }}
                  />
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="font-heading flex items-center gap-2">
              <span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary text-primary-foreground text-sm">2</span>
              Events
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant={!hasEvents ? "default" : "outline"}
                size="sm"
                onClick={function() { setHasEvents(false); setEvents([]); }}
                data-testid="no-events-btn"
              >
                No Events Today
              </Button>
              <Button
                variant={hasEvents ? "default" : "outline"}
                size="sm"
                onClick={function() { setHasEvents(true); }}
                data-testid="has-events-btn"
              >
                Add Events
              </Button>
            </div>
          </div>
          <CardDescription>
            {hasEvents 
              ? 'Add all events that occurred at this location on this date'
              : 'This will record that no events occurred today'
            }
          </CardDescription>
        </CardHeader>
        
        {hasEvents && (
          <CardContent className="space-y-4">
            {events.map(function(event, index) {
              return (
                <EventFormItem
                  key={index}
                  event={event}
                  index={index}
                  categories={categories}
                  locations={locations}
                  diseases={diseases}
                  onUpdate={updateEvent}
                  onRemove={removeEvent}
                />
              );
            })}

            <Button variant="outline" className="w-full gap-2" onClick={addEvent} data-testid="add-event-btn">
              <Plus className="h-4 w-4" />
              Add Event
            </Button>
          </CardContent>
        )}
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="font-heading flex items-center gap-2">
            <span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary text-primary-foreground text-sm">3</span>
            Additional Notes
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            value={notes}
            onChange={function(e) { setNotes(e.target.value); }}
            placeholder="Any additional notes for this daily log..."
            rows={3}
            data-testid="log-notes"
          />
        </CardContent>
      </Card>

      <div className="flex justify-end gap-4">
        <Button variant="outline" onClick={function() { navigate(-1); }}>
          Cancel
        </Button>
        <Button 
          onClick={handleSubmit} 
          disabled={saving || !locationId}
          className="gap-2"
          data-testid="submit-log-btn"
        >
          {saving ? 'Saving...' : (
            <>
              <CheckCircle className="h-4 w-4" />
              Submit Daily Log
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

export default NewDailyLog;
