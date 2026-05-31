import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import {
  getFarmHealthEvents, createFarmHealthEvent, updateFarmHealthEvent, deleteFarmHealthEvent,
  getLastEvents, getLocations, getCategories, getHealthIntervals,
  createHealthInterval, updateHealthInterval, deleteHealthInterval,
  getProductSuggestions, getVaccineTypes, createVaccineType,
} from '../lib/api';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Skeleton } from '../components/ui/skeleton';
import {
  FirstAidKit, Drop, Syringe, Virus, BookOpen,
  Plus, Gear, WarningCircle, CheckCircle, Clock, Trash, PencilSimple,
} from '@phosphor-icons/react';
import { toast } from 'sonner';
import { formatDate, SPECIES_CONFIG, cn } from '../lib/utils';

const EVENT_TYPE_CONFIG = {
  dipping: {
    label: 'Dipping', Icon: Drop,
    color: 'text-teal-600', bg: 'bg-teal-50', border: 'border-teal-200', dot: 'bg-teal-500',
  },
  vaccination: {
    label: 'Vaccination', Icon: Syringe,
    color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200', dot: 'bg-blue-500',
  },
  deworming: {
    label: 'Deworming', Icon: Virus,
    color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200', dot: 'bg-orange-500',
  },
  log: {
    label: 'Farm Diary', Icon: BookOpen,
    color: 'text-gray-600', bg: 'bg-gray-50', border: 'border-gray-200', dot: 'bg-gray-400',
  },
};

const SPECIES_OPTIONS = ['cattle', 'sheep', 'goat'];
const HEALTH_EVENT_TYPES = ['dipping', 'vaccination', 'deworming', 'log'];

const DEFAULT_FORM = {
  location_id: '',
  event_type: '',
  event_date: new Date().toISOString().slice(0, 10),
  species: '',
  category_scope: 'all',
  category_ids: [],
  product_name: '',
  dosage: '',
  cost_per_head: '',
  total_cost: '',
  head_count: '',
  notes: '',
  vaccine_type_id: '',
  next_due_date: '',
};

const DEFAULT_NEW_VACCINE = {
  name: '',
  default_interval_days: '',
  all_species: true,
  cattle: false,
  sheep: false,
  goat: false,
};

function HealthStatusBadge({ summary }) {
  if (summary.is_overdue) {
    return (
      <span className="flex items-center gap-1 text-xs font-semibold text-red-600">
        <WarningCircle className="h-3.5 w-3.5" weight="fill" />
        {summary.days_overdue ? `${summary.days_overdue}d overdue` : 'Overdue (never done)'}
      </span>
    );
  }
  if (!summary.next_due_date) {
    return <span className="text-xs text-muted-foreground">No schedule</span>;
  }
  const today = new Date();
  const due = new Date(summary.next_due_date);
  const daysLeft = Math.ceil((due - today) / (1000 * 60 * 60 * 24));
  if (daysLeft <= 7) {
    return (
      <span className="flex items-center gap-1 text-xs font-semibold text-amber-600">
        <Clock className="h-3.5 w-3.5" />
        Due in {daysLeft}d
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-xs text-green-600">
      <CheckCircle className="h-3.5 w-3.5" weight="fill" />
      Due {formatDate(summary.next_due_date)}
    </span>
  );
}

function FarmHealth() {
  const { isAdmin, isDataEntry } = useAuth();
  const [events, setEvents] = useState([]);
  const [lastEvents, setLastEvents] = useState([]);
  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [intervals, setIntervals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [productSuggestions, setProductSuggestions] = useState([]);

  const [filterLocation, setFilterLocation] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [filterSpecies, setFilterSpecies] = useState('all');
  const [filterOverdue, setFilterOverdue] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogStep, setDialogStep] = useState(1);
  const [editingEvent, setEditingEvent] = useState(null);
  const [formData, setFormData] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  const [intervalsOpen, setIntervalsOpen] = useState(false);
  const [intervalForm, setIntervalForm] = useState({ location_id: '', species: '', event_type: '', interval_days: '' });
  const [savingInterval, setSavingInterval] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState(null);

  const [vaccineTypes, setVaccineTypes] = useState([]);
  const [addVaccineOpen, setAddVaccineOpen] = useState(false);
  const [newVaccineForm, setNewVaccineForm] = useState(DEFAULT_NEW_VACCINE);
  const [savingVaccine, setSavingVaccine] = useState(false);

  useEffect(function () {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [locRes, catRes] = await Promise.all([getLocations(), getCategories()]);
      setLocations(locRes.data);
      setCategories(catRes.data);
    } catch {
      toast.error('Failed to load reference data');
    }
    try {
      const [evRes, lastRes, ivRes] = await Promise.all([
        getFarmHealthEvents({ limit: 200 }),
        getLastEvents(),
        getHealthIntervals(),
      ]);
      setEvents(evRes.data);
      setLastEvents(lastRes.data);
      setIntervals(ivRes.data);
    } catch {
      toast.error('Failed to load health events');
    } finally {
      setLoading(false);
    }
  }

  function setField(key, value) {
    setFormData(function (prev) { return { ...prev, [key]: value }; });
  }

  const filteredEvents = events.filter(function (ev) {
    if (filterLocation !== 'all' && ev.location_id !== parseInt(filterLocation)) return false;
    if (filterType !== 'all' && ev.event_type !== filterType) return false;
    if (filterSpecies !== 'all' && ev.species !== filterSpecies) return false;
    if (filterOverdue && (!ev.next_due_date || new Date(ev.next_due_date) >= new Date())) return false;
    return true;
  });

  const formCategories = categories.filter(function (c) { return c.species === formData.species; });
  const overdueCount = lastEvents.filter(function (s) { return s.is_overdue; }).length;

  const groupedEvents = {};
  filteredEvents.forEach(function (ev) {
    const key = ev.event_date;
    if (!groupedEvents[key]) groupedEvents[key] = [];
    groupedEvents[key].push(ev);
  });
  const sortedDates = Object.keys(groupedEvents).sort(function (a, b) { return b.localeCompare(a); });

  function loadVaccineTypes(species) {
    getVaccineTypes(species ? species.toUpperCase() : undefined)
      .then(function (r) { setVaccineTypes(r.data || []); })
      .catch(function () {});
  }

  function openAddDialog(eventType) {
    setEditingEvent(null);
    setFormData({ ...DEFAULT_FORM, event_type: eventType || '' });
    setDialogStep(eventType ? 2 : 1);
    setDialogOpen(true);
    if (eventType) {
      getProductSuggestions({ event_type: eventType })
        .then(function (r) { setProductSuggestions(r.data.suggestions || []); })
        .catch(function () {});
      if (eventType === 'vaccination') loadVaccineTypes();
    }
  }

  function openEditDialog(ev) {
    setEditingEvent(ev);
    setFormData({
      location_id: String(ev.location_id),
      event_type: ev.event_type,
      event_date: ev.event_date,
      species: ev.species || '',
      category_scope: ev.category_scope || 'all',
      category_ids: ev.category_ids || [],
      product_name: ev.product_name || '',
      dosage: ev.dosage || '',
      cost_per_head: ev.cost_per_head != null ? String(ev.cost_per_head) : '',
      total_cost: ev.total_cost != null ? String(ev.total_cost) : '',
      head_count: ev.head_count != null ? String(ev.head_count) : '',
      notes: ev.notes || '',
      vaccine_type_id: ev.vaccine_type_id ? String(ev.vaccine_type_id) : '',
      next_due_date: ev.next_due_date || '',
    });
    setDialogStep(2);
    setDialogOpen(true);
    getProductSuggestions({ event_type: ev.event_type })
      .then(function (r) { setProductSuggestions(r.data.suggestions || []); })
      .catch(function () {});
    if (ev.event_type === 'vaccination') loadVaccineTypes(ev.species);
  }

  async function handleSave() {
    if (!formData.location_id || !formData.event_date) {
      toast.error('Location and date are required');
      return;
    }
    if (formData.event_type !== 'log') {
      if (!formData.species) { toast.error('Species is required'); return; }
      if (!formData.product_name) { toast.error('Product name is required'); return; }
      if (formData.category_scope === 'specific' && formData.category_ids.length === 0) {
        toast.error('Select at least one category'); return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        location_id: parseInt(formData.location_id),
        event_type: formData.event_type,
        event_date: formData.event_date,
        notes: formData.notes || null,
      };
      if (formData.event_type !== 'log') {
        payload.species = formData.species;
        payload.category_scope = formData.category_scope;
        payload.category_ids = formData.category_scope === 'specific' ? formData.category_ids : null;
        payload.product_name = formData.product_name;
        payload.dosage = formData.dosage || null;
        payload.cost_per_head = formData.cost_per_head ? parseFloat(formData.cost_per_head) : null;
        payload.total_cost = formData.total_cost ? parseFloat(formData.total_cost) : null;
        payload.head_count = formData.head_count ? parseInt(formData.head_count) : null;
      }
      if (formData.event_type === 'vaccination') {
        payload.vaccine_type_id = formData.vaccine_type_id ? parseInt(formData.vaccine_type_id) : null;
        payload.next_due_date = formData.next_due_date || null;
      }
      if (editingEvent) {
        await updateFarmHealthEvent(editingEvent.id, payload);
        toast.success('Event updated');
      } else {
        await createFarmHealthEvent(payload);
        toast.success('Event logged');
      }
      setDialogOpen(false);
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save event');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(ev) {
    try {
      await deleteFarmHealthEvent(ev.id);
      toast.success('Event deleted');
      setDeleteTarget(null);
      await loadData();
    } catch {
      toast.error('Failed to delete event');
    }
  }

  function toggleCategoryId(id) {
    setFormData(function (prev) {
      const ids = prev.category_ids || [];
      if (ids.includes(id)) return { ...prev, category_ids: ids.filter(function (x) { return x !== id; }) };
      return { ...prev, category_ids: [...ids, id] };
    });
  }

  async function handleSaveInterval() {
    if (!intervalForm.location_id || !intervalForm.species || !intervalForm.event_type || !intervalForm.interval_days) {
      toast.error('All fields are required');
      return;
    }
    setSavingInterval(true);
    try {
      const existing = intervals.find(function (iv) {
        return iv.location_id === parseInt(intervalForm.location_id) &&
          iv.species === intervalForm.species &&
          iv.event_type === intervalForm.event_type;
      });
      if (existing) {
        await updateHealthInterval(existing.id, { interval_days: parseInt(intervalForm.interval_days) });
      } else {
        await createHealthInterval({
          location_id: parseInt(intervalForm.location_id),
          species: intervalForm.species,
          event_type: intervalForm.event_type,
          interval_days: parseInt(intervalForm.interval_days),
        });
      }
      toast.success('Interval saved');
      setIntervalForm({ location_id: '', species: '', event_type: '', interval_days: '' });
      const [ivRes, lastRes] = await Promise.all([getHealthIntervals(), getLastEvents()]);
      setIntervals(ivRes.data);
      setLastEvents(lastRes.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save interval');
    } finally {
      setSavingInterval(false);
    }
  }

  async function handleSaveVaccineType() {
    if (!newVaccineForm.name.trim()) { toast.error('Vaccine name is required'); return; }
    setSavingVaccine(true);
    try {
      let species_applicability = null;
      if (!newVaccineForm.all_species) {
        const selected = [];
        if (newVaccineForm.cattle) selected.push('CATTLE');
        if (newVaccineForm.sheep) selected.push('SHEEP');
        if (newVaccineForm.goat) selected.push('GOAT');
        if (selected.length === 0) { toast.error('Select at least one species or choose All'); setSavingVaccine(false); return; }
        species_applicability = selected;
      }
      const created = await createVaccineType({
        name: newVaccineForm.name.trim(),
        default_interval_days: newVaccineForm.default_interval_days ? parseInt(newVaccineForm.default_interval_days) : null,
        species_applicability,
      });
      const newVt = created.data;
      setAddVaccineOpen(false);
      setNewVaccineForm(DEFAULT_NEW_VACCINE);
      // Reload vaccine types and auto-select the new one
      loadVaccineTypes(formData.species || undefined);
      setField('vaccine_type_id', String(newVt.id));
      if (newVt.default_interval_days && formData.event_date) {
        const d = new Date(formData.event_date);
        d.setDate(d.getDate() + newVt.default_interval_days);
        setField('next_due_date', d.toISOString().slice(0, 10));
      }
      toast.success('Vaccine type added');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save vaccine type');
    } finally {
      setSavingVaccine(false);
    }
  }

  async function handleDeleteInterval(iv) {
    try {
      await deleteHealthInterval(iv.id);
      toast.success('Interval deleted');
      const ivRes = await getHealthIntervals();
      setIntervals(ivRes.data);
    } catch {
      toast.error('Failed to delete interval');
    }
  }

  const canEdit = isAdmin || isDataEntry;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-heading font-bold text-foreground">Farm Health</h1>
          <p className="text-muted-foreground text-sm">Dipping, vaccination, deworming &amp; diary</p>
        </div>
        <div className="flex gap-2">
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={function () { setIntervalsOpen(true); }}>
              <Gear className="h-4 w-4 mr-1.5" />
              Intervals
            </Button>
          )}
          {canEdit && (
            <Button size="sm" onClick={function () { openAddDialog(); }}>
              <Plus className="h-4 w-4 mr-1.5" />
              Log Event
            </Button>
          )}
        </div>
      </div>

      {/* Overdue Banner */}
      {!loading && overdueCount > 0 && (
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <WarningCircle className="h-5 w-5 text-red-600 flex-shrink-0" weight="fill" />
          <p className="text-sm text-red-700 font-medium">
            {overdueCount} health intervention{overdueCount > 1 ? 's are' : ' is'} overdue or never recorded.
          </p>
        </div>
      )}

      {/* Last Event Summary Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map(function (i) { return <Skeleton key={i} className="h-24 rounded-lg" />; })}
        </div>
      ) : lastEvents.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {lastEvents.slice(0, 12).map(function (s, i) {
            const cfg = EVENT_TYPE_CONFIG[s.event_type] || EVENT_TYPE_CONFIG.log;
            const Icon = cfg.Icon;
            return (
              <Card key={i} className={cn('border', s.is_overdue ? 'border-red-200 bg-red-50/30' : cfg.border)}>
                <CardContent className="p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className={cn('flex items-center gap-1 text-xs font-semibold', cfg.color)}>
                      <Icon className="h-3.5 w-3.5" />
                      {cfg.label}
                    </span>
                    {s.species && (
                      <span className={cn(
                        'px-1.5 py-0.5 rounded-full text-xs font-medium capitalize',
                        SPECIES_CONFIG[s.species]?.bgClass || '',
                        SPECIES_CONFIG[s.species]?.textClass || ''
                      )}>
                        {s.species}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-medium text-foreground truncate">{s.location_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {s.last_date ? `Last: ${formatDate(s.last_date)}` : 'Never done'}
                  </p>
                  <HealthStatusBadge summary={s} />
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-2 items-center">
        <Select value={filterLocation} onValueChange={setFilterLocation}>
          <SelectTrigger className="w-40 h-8 text-xs">
            <SelectValue placeholder="All locations" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All locations</SelectItem>
            {locations.map(function (l) {
              return <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>;
            })}
          </SelectContent>
        </Select>

        <div className="flex gap-1">
          {['all', ...HEALTH_EVENT_TYPES].map(function (t) {
            const cfg = t !== 'all' ? EVENT_TYPE_CONFIG[t] : null;
            const Icon = cfg ? cfg.Icon : FirstAidKit;
            return (
              <button
                key={t}
                onClick={function () { setFilterType(t); }}
                className={cn(
                  'flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border',
                  filterType === t
                    ? (cfg ? `${cfg.bg} ${cfg.color} ${cfg.border}` : 'bg-primary text-primary-foreground border-primary')
                    : 'bg-muted text-muted-foreground border-transparent hover:bg-muted/80'
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {cfg ? cfg.label : 'All'}
              </button>
            );
          })}
        </div>

        <Select value={filterSpecies} onValueChange={setFilterSpecies}>
          <SelectTrigger className="w-32 h-8 text-xs">
            <SelectValue placeholder="All species" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All species</SelectItem>
            {SPECIES_OPTIONS.map(function (s) {
              return <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>;
            })}
          </SelectContent>
        </Select>

        <button
          onClick={function () { setFilterOverdue(function (v) { return !v; }); }}
          className={cn(
            'flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border',
            filterOverdue
              ? 'bg-red-100 text-red-700 border-red-200'
              : 'bg-muted text-muted-foreground border-transparent hover:bg-muted/80'
          )}
        >
          <WarningCircle className="h-3.5 w-3.5" />
          Overdue only
        </button>
      </div>

      {/* Timeline */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(function (i) { return <Skeleton key={i} className="h-20 rounded-lg" />; })}
        </div>
      ) : filteredEvents.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center text-muted-foreground">
            <FirstAidKit className="h-12 w-12 mx-auto mb-3 opacity-20" />
            <p className="font-medium">No health events found</p>
            <p className="text-sm mt-1">Log your first dipping, vaccination, or deworming event.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {sortedDates.map(function (dateKey) {
            return (
              <div key={dateKey}>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  {formatDate(dateKey)}
                </p>
                <div className="space-y-2 pl-4 border-l-2 border-border ml-1">
                  {groupedEvents[dateKey].map(function (ev) {
                    const cfg = EVENT_TYPE_CONFIG[ev.event_type] || EVENT_TYPE_CONFIG.log;
                    const Icon = cfg.Icon;
                    return (
                      <div key={ev.id} className="relative">
                        <div className={cn(
                          'absolute -left-[21px] top-3 w-2.5 h-2.5 rounded-full border-2 border-background',
                          cfg.dot
                        )} />
                        <Card className={cn('border', cfg.border)}>
                          <CardContent className="p-3">
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-start gap-2 min-w-0 flex-1">
                                <div className={cn('p-1.5 rounded-md flex-shrink-0 mt-0.5', cfg.bg)}>
                                  <Icon className={cn('h-4 w-4', cfg.color)} />
                                </div>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className={cn('text-sm font-semibold', cfg.color)}>{cfg.label}</span>
                                    <span className="text-xs text-muted-foreground">{ev.location_name}</span>
                                    {ev.species && (
                                      <span className={cn(
                                        'px-1.5 py-0.5 rounded-full text-xs font-medium capitalize',
                                        SPECIES_CONFIG[ev.species]?.bgClass || '',
                                        SPECIES_CONFIG[ev.species]?.textClass || ''
                                      )}>
                                        {ev.species}
                                      </span>
                                    )}
                                  </div>
                                  {ev.product_name && (
                                    <p className="text-sm text-foreground mt-0.5">{ev.product_name}</p>
                                  )}
                                  {ev.event_type === 'vaccination' && ev.vaccine_type_name && (
                                    <span className="inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 mt-0.5">
                                      {ev.vaccine_type_name}
                                    </span>
                                  )}
                                  <div className="flex flex-wrap gap-x-3 mt-1 text-xs text-muted-foreground">
                                    {ev.head_count && <span>{ev.head_count.toLocaleString()} head</span>}
                                    {ev.dosage && <span>{ev.dosage}</span>}
                                    {ev.total_cost && <span>KES {ev.total_cost.toLocaleString()}</span>}
                                    {ev.category_scope === 'all' && ev.event_type !== 'log' && <span>All categories</span>}
                                    {ev.category_scope === 'specific' && ev.resolved_categories?.length > 0 && (
                                      <span>{ev.resolved_categories.map(function (c) { return c.name_sw; }).join(', ')}</span>
                                    )}
                                  </div>
                                  {ev.notes && (
                                    <p className="text-xs text-muted-foreground mt-1 italic">{ev.notes}</p>
                                  )}
                                  {ev.next_due_date && (
                                    <p className="text-xs text-muted-foreground mt-1">
                                      Next due: {formatDate(ev.next_due_date)}
                                    </p>
                                  )}
                                </div>
                              </div>
                              {isAdmin && (
                                <div className="flex gap-1 flex-shrink-0">
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    onClick={function () { openEditDialog(ev); }}
                                  >
                                    <PencilSimple className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-destructive hover:text-destructive"
                                    onClick={function () { setDeleteTarget(ev); }}
                                  >
                                    <Trash className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Log Event Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingEvent ? 'Edit Health Event' : dialogStep === 1 ? 'Log Event — Choose Type' : 'Log Event'}
            </DialogTitle>
          </DialogHeader>

          {dialogStep === 1 && !editingEvent ? (
            <div className="grid grid-cols-2 gap-3 mt-2">
              {HEALTH_EVENT_TYPES.map(function (t) {
                const cfg = EVENT_TYPE_CONFIG[t];
                const Icon = cfg.Icon;
                return (
                  <button
                    key={t}
                    onClick={function () {
                      setField('event_type', t);
                      setDialogStep(2);
                      getProductSuggestions({ event_type: t })
                        .then(function (r) { setProductSuggestions(r.data.suggestions || []); })
                        .catch(function () {});
                      if (t === 'vaccination') loadVaccineTypes();
                    }}
                    className={cn(
                      'flex flex-col items-center gap-2 p-5 rounded-xl border-2 transition-all hover:shadow-md',
                      cfg.bg, cfg.border
                    )}
                  >
                    <Icon className={cn('h-9 w-9', cfg.color)} />
                    <span className={cn('font-semibold text-sm', cfg.color)}>{cfg.label}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="space-y-4 mt-2">
              {formData.event_type && (
                <div className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium',
                  EVENT_TYPE_CONFIG[formData.event_type]?.bg,
                  EVENT_TYPE_CONFIG[formData.event_type]?.color
                )}>
                  {React.createElement(EVENT_TYPE_CONFIG[formData.event_type]?.Icon, { className: 'h-4 w-4' })}
                  {EVENT_TYPE_CONFIG[formData.event_type]?.label}
                  {!editingEvent && (
                    <button
                      onClick={function () { setDialogStep(1); }}
                      className="ml-auto text-xs underline opacity-70 hover:opacity-100"
                    >
                      Change
                    </button>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Location *</Label>
                  <Select value={formData.location_id} onValueChange={function (v) { setField('location_id', v); }}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Select location" />
                    </SelectTrigger>
                    <SelectContent>
                      {locations.map(function (l) {
                        return <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>;
                      })}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Date *</Label>
                  <Input
                    type="date"
                    className="mt-1"
                    value={formData.event_date}
                    onChange={function (e) { setField('event_date', e.target.value); }}
                  />
                </div>
              </div>

              {formData.event_type !== 'log' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Species *</Label>
                      <Select value={formData.species} onValueChange={function (v) {
                        setField('species', v);
                        setField('category_ids', []);
                      }}>
                        <SelectTrigger className="mt-1">
                          <SelectValue placeholder="Select species" />
                        </SelectTrigger>
                        <SelectContent>
                          {SPECIES_OPTIONS.map(function (s) {
                            return <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>;
                          })}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Category scope *</Label>
                      <Select value={formData.category_scope} onValueChange={function (v) {
                        setField('category_scope', v);
                        if (v === 'all') setField('category_ids', []);
                      }}>
                        <SelectTrigger className="mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All categories</SelectItem>
                          <SelectItem value="specific">Specific categories</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {formData.category_scope === 'specific' && formData.species && (
                    <div>
                      <Label>Select categories *</Label>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {formCategories.length === 0 ? (
                          <p className="text-xs text-muted-foreground">No categories for selected species</p>
                        ) : formCategories.map(function (c) {
                          const selected = (formData.category_ids || []).includes(c.id);
                          return (
                            <button
                              key={c.id}
                              type="button"
                              onClick={function () { toggleCategoryId(c.id); }}
                              className={cn(
                                'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
                                selected
                                  ? 'bg-primary text-primary-foreground border-primary'
                                  : 'bg-muted text-muted-foreground border-border hover:border-primary'
                              )}
                            >
                              {c.name_sw}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {formData.event_type === 'vaccination' && (
                    <div>
                      <Label>Vaccine type</Label>
                      <Select
                        value={formData.vaccine_type_id}
                        onValueChange={function (v) {
                          if (v === '__add_new__') { setAddVaccineOpen(true); return; }
                          setField('vaccine_type_id', v);
                          const vt = vaccineTypes.find(function (x) { return String(x.id) === v; });
                          if (vt && vt.default_interval_days && formData.event_date) {
                            const d = new Date(formData.event_date);
                            d.setDate(d.getDate() + vt.default_interval_days);
                            setField('next_due_date', d.toISOString().slice(0, 10));
                          } else if (!v) {
                            setField('next_due_date', '');
                          }
                        }}
                      >
                        <SelectTrigger className="mt-1">
                          <SelectValue placeholder="Select vaccine type..." />
                        </SelectTrigger>
                        <SelectContent>
                          {vaccineTypes.map(function (vt) {
                            return (
                              <SelectItem key={vt.id} value={String(vt.id)}>
                                {vt.name}{vt.default_interval_days ? ` (every ${vt.default_interval_days}d)` : ''}
                              </SelectItem>
                            );
                          })}
                          <SelectItem value="__add_new__" className="text-primary font-medium">
                            + Add new vaccine type
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {formData.event_type === 'vaccination' && (
                    <div>
                      <Label>Next due date</Label>
                      <Input
                        type="date"
                        className="mt-1"
                        value={formData.next_due_date}
                        onChange={function (e) { setField('next_due_date', e.target.value); }}
                      />
                    </div>
                  )}

                  <div>
                    <Label>Product name *</Label>
                    <Input
                      className="mt-1"
                      value={formData.product_name}
                      onChange={function (e) { setField('product_name', e.target.value); }}
                      placeholder="e.g. Diptank 200EC, Ivermectin..."
                      list="product-suggestions-list"
                    />
                    <datalist id="product-suggestions-list">
                      {productSuggestions.map(function (s, i) {
                        return <option key={i} value={s} />;
                      })}
                    </datalist>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Dosage</Label>
                      <Input
                        className="mt-1"
                        value={formData.dosage}
                        onChange={function (e) { setField('dosage', e.target.value); }}
                        placeholder="e.g. 5ml"
                      />
                    </div>
                    <div>
                      <Label>Head count</Label>
                      <Input
                        type="number"
                        min="0"
                        className="mt-1"
                        value={formData.head_count}
                        onChange={function (e) { setField('head_count', e.target.value); }}
                      />
                    </div>
                    <div>
                      <Label>Total cost (KES)</Label>
                      <Input
                        type="number"
                        min="0"
                        className="mt-1"
                        value={formData.total_cost}
                        onChange={function (e) { setField('total_cost', e.target.value); }}
                      />
                    </div>
                  </div>
                </>
              )}

              <div>
                <Label>Notes</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={formData.notes}
                  onChange={function (e) { setField('notes', e.target.value); }}
                  placeholder="Optional notes..."
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <Button variant="outline" onClick={function () { setDialogOpen(false); }}>Cancel</Button>
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving...' : editingEvent ? 'Update' : 'Log Event'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <Dialog open={!!deleteTarget} onOpenChange={function (o) { if (!o) setDeleteTarget(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete health event?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Permanently delete this{' '}
            {deleteTarget && (EVENT_TYPE_CONFIG[deleteTarget.event_type]?.label || '').toLowerCase()} event
            from {deleteTarget?.event_date}? This cannot be undone.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={function () { setDeleteTarget(null); }}>Cancel</Button>
            <Button variant="destructive" onClick={function () { handleDelete(deleteTarget); }}>Delete</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Interval Settings */}
      <Dialog open={intervalsOpen} onOpenChange={setIntervalsOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Health Interval Settings</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            Configure reminder intervals (days) per location, species, and event type to track upcoming schedules.
          </p>

          <div className="grid grid-cols-4 gap-2 mt-3">
            <div>
              <Label className="text-xs">Location</Label>
              <Select value={intervalForm.location_id} onValueChange={function (v) {
                setIntervalForm(function (p) { return { ...p, location_id: v }; });
              }}>
                <SelectTrigger className="mt-1 h-8 text-xs">
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {locations.map(function (l) {
                    return <SelectItem key={l.id} value={String(l.id)}>{l.name}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Species</Label>
              <Select value={intervalForm.species} onValueChange={function (v) {
                setIntervalForm(function (p) { return { ...p, species: v }; });
              }}>
                <SelectTrigger className="mt-1 h-8 text-xs">
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {SPECIES_OPTIONS.map(function (s) {
                    return <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Event type</Label>
              <Select value={intervalForm.event_type} onValueChange={function (v) {
                setIntervalForm(function (p) { return { ...p, event_type: v }; });
              }}>
                <SelectTrigger className="mt-1 h-8 text-xs">
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {['dipping', 'vaccination', 'deworming'].map(function (t) {
                    return <SelectItem key={t} value={t}>{EVENT_TYPE_CONFIG[t].label}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Every N days</Label>
              <div className="flex gap-1 mt-1">
                <Input
                  type="number"
                  min="1"
                  className="h-8 text-xs"
                  value={intervalForm.interval_days}
                  onChange={function (e) {
                    setIntervalForm(function (p) { return { ...p, interval_days: e.target.value }; });
                  }}
                  placeholder="14"
                />
                <Button size="sm" className="h-8 px-2 flex-shrink-0" onClick={handleSaveInterval} disabled={savingInterval}>
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>

          {intervals.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Configured Intervals</p>
              {intervals.map(function (iv) {
                const cfg = EVENT_TYPE_CONFIG[iv.event_type] || {};
                return (
                  <div key={iv.id} className="flex items-center justify-between px-3 py-2 rounded-md bg-muted/50 text-sm">
                    <div className="flex items-center gap-3">
                      <span className="text-muted-foreground text-xs">{iv.location_name}</span>
                      <span className={cn(
                        'px-1.5 py-0.5 rounded-full text-xs font-medium capitalize',
                        SPECIES_CONFIG[iv.species]?.bgClass || '',
                        SPECIES_CONFIG[iv.species]?.textClass || ''
                      )}>
                        {iv.species}
                      </span>
                      <span className={cn('text-xs font-medium', cfg.color)}>{cfg.label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold">Every {iv.interval_days} days</span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-destructive hover:text-destructive"
                        onClick={function () { handleDeleteInterval(iv); }}
                      >
                        <Trash className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {intervals.length === 0 && (
            <p className="text-xs text-muted-foreground mt-4 text-center py-4 border rounded-md border-dashed">
              No intervals configured yet. Add one above to enable due-date tracking.
            </p>
          )}
        </DialogContent>
      </Dialog>

      {/* Add Vaccine Type Dialog */}
      <Dialog open={addVaccineOpen} onOpenChange={setAddVaccineOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Add Vaccine Type</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div>
              <Label>Name *</Label>
              <Input
                className="mt-1"
                value={newVaccineForm.name}
                onChange={function (e) { setNewVaccineForm(function (p) { return { ...p, name: e.target.value }; }); }}
                placeholder="e.g. FMD, Blackleg..."
              />
            </div>
            <div>
              <Label>Default interval (days)</Label>
              <Input
                type="number"
                min="1"
                className="mt-1"
                value={newVaccineForm.default_interval_days}
                onChange={function (e) { setNewVaccineForm(function (p) { return { ...p, default_interval_days: e.target.value }; }); }}
                placeholder="e.g. 180"
              />
            </div>
            <div>
              <Label>Species applicability</Label>
              <div className="mt-2 space-y-1.5">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newVaccineForm.all_species}
                    onChange={function (e) {
                      setNewVaccineForm(function (p) {
                        return { ...p, all_species: e.target.checked, cattle: false, sheep: false, goat: false };
                      });
                    }}
                  />
                  All species
                </label>
                {!newVaccineForm.all_species && ['cattle', 'sheep', 'goat'].map(function (sp) {
                  return (
                    <label key={sp} className="flex items-center gap-2 text-sm cursor-pointer capitalize ml-4">
                      <input
                        type="checkbox"
                        checked={newVaccineForm[sp]}
                        onChange={function (e) {
                          setNewVaccineForm(function (p) { return { ...p, [sp]: e.target.checked }; });
                        }}
                      />
                      {sp}
                    </label>
                  );
                })}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={function () { setAddVaccineOpen(false); }}>Cancel</Button>
              <Button onClick={handleSaveVaccineType} disabled={savingVaccine}>
                {savingVaccine ? 'Saving...' : 'Add Vaccine Type'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default FarmHealth;
