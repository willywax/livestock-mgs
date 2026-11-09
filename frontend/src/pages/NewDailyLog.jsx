import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getLocations, getCategories, createDailyLog, getDiseases, listDeathCauses } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { CalendarBlank, MapPin, Plus, ArrowLeft, CheckCircle } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { EventFormItem, blankEvent, applyEventChange, validateEvent, eventToCreatePayload } from '../components/EventForm';

function NewDailyLog() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedLocation = searchParams.get('location');

  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState({});
  const [diseases, setDiseases] = useState([]);
  const [deathCauses, setDeathCauses] = useState([]);
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
      try {
        const causeRes = await listDeathCauses();
        setDeathCauses(causeRes.data);
      } catch (causeError) {
        // Cause list is optional: deaths can still be saved without a structured cause
      }
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  function addEvent() {
    setEvents([...events, blankEvent()]);
  }

  function updateEvent(index, field, value) {
    setEvents(function(prev) {
      return prev.map(function(ev, i) { return i === index ? applyEventChange(ev, field, value) : ev; });
    });
  }

  // Update several fields of one event atomically (functional update, safe to call back-to-back)
  function patchEvent(index, patch) {
    setEvents(function(prev) {
      return prev.map(function(ev, i) { return i === index ? { ...ev, ...patch } : ev; });
    });
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
      const problem = validateEvent(events[i]);
      if (problem) {
        toast.error(`Event ${i + 1}: ${problem}`);
        return;
      }
    }

    setSaving(true);
    try {
      const payload = {
        location_id: parseInt(locationId),
        log_date: format(logDate, 'yyyy-MM-dd'),
        has_events: hasEvents && events.length > 0,
        notes: notes || null,
        events: events.map(eventToCreatePayload)
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
                  deathCauses={deathCauses}
                  locationId={locationId}
                  logDate={logDate}
                  onUpdate={updateEvent}
                  onPatch={patchEvent}
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
