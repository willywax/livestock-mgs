import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getDailyLog, lockDailyLog, createEvent, updateEvent, deleteEvent, getCategories, getLocations, updateDailyLog } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../components/ui/alert-dialog';
import { ArrowLeft, CalendarBlank, MapPin, Lock, CheckCircle, ArrowsLeftRight, ArrowsDownUp, Pencil, Trash, Plus } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { EVENT_TYPES, SPECIES_CONFIG, formatDate, formatDateTime } from '../lib/utils';
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

const DailyLogDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [log, setLog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [locking, setLocking] = useState(false);
  const [categories, setCategories] = useState({});
  const [locations, setLocations] = useState([]);
  const { isAdmin } = useAuth();

  // Edit event dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);

  // Delete dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingEvent, setDeletingEvent] = useState(null);

  // Add event dialog state
  const [addEventDialogOpen, setAddEventDialogOpen] = useState(false);
  const [addEventForm, setAddEventForm] = useState({
    event_type: 'birth',
    species: 'cattle',
    category_id: '',
    count: 0,
    from_location_id: '',
    to_location_id: '',
    from_category_id: '',
    to_category_id: '',
    notes: '',
    is_stock_event: true,
  });
  const [addingEvent, setAddingEvent] = useState(false);

  // Edit log dialog state
  const [editLogDialogOpen, setEditLogDialogOpen] = useState(false);
  const [editLogForm, setEditLogForm] = useState({ location_id: '', log_date: null, notes: '' });
  const [savingLog, setSavingLog] = useState(false);
  const [logDateOpen, setLogDateOpen] = useState(false);

  const loadLog = useCallback(async () => {
    try {
      const response = await getDailyLog(id);
      setLog(response.data);
    } catch (error) {
      toast.error('Failed to load daily log');
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadCategories = useCallback(async () => {
    try {
      const [cattleRes, sheepRes, goatRes, locRes] = await Promise.all([
        getCategories('cattle'),
        getCategories('sheep'),
        getCategories('goat'),
        getLocations()
      ]);
      setCategories({
        cattle: cattleRes.data,
        sheep: sheepRes.data,
        goat: goatRes.data
      });
      setLocations(locRes.data);
    } catch (error) {
      console.error('Failed to load categories');
    }
  }, []);

  useEffect(() => {
    loadLog();
    loadCategories();
  }, [loadLog, loadCategories]);

  const handleLock = async () => {
    setLocking(true);
    try {
      await lockDailyLog(id);
      toast.success('Daily log locked successfully');
      loadLog();
    } catch (error) {
      toast.error('Failed to lock daily log');
    } finally {
      setLocking(false);
    }
  };

  const openEditDialog = (event) => {
    setEditingEvent(event);
    setEditForm({
      event_type: event.event_type,
      species: event.species,
      category_id: event.category_id?.toString() || '',
      count: event.count,
      from_location_id: event.from_location_id?.toString() || '',
      to_location_id: event.to_location_id?.toString() || '',
      from_category_id: event.from_category_id?.toString() || '',
      to_category_id: event.to_category_id?.toString() || '',
      notes: event.notes || ''
    });
    setEditDialogOpen(true);
  };

  const handleEditSubmit = async () => {
    setSaving(true);
    try {
      const payload = {
        event_type: editForm.event_type,
        species: editForm.species,
        count: parseInt(editForm.count) || 0,
        notes: editForm.notes || null
      };

      if (editForm.category_id) payload.category_id = parseInt(editForm.category_id);
      if (editForm.from_location_id) payload.from_location_id = parseInt(editForm.from_location_id);
      if (editForm.to_location_id) payload.to_location_id = parseInt(editForm.to_location_id);
      if (editForm.from_category_id) payload.from_category_id = parseInt(editForm.from_category_id);
      if (editForm.to_category_id) payload.to_category_id = parseInt(editForm.to_category_id);

      await updateEvent(editingEvent.id, payload);
      toast.success('Event updated successfully');
      setEditDialogOpen(false);
      loadLog();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update event');
    } finally {
      setSaving(false);
    }
  };

  const openDeleteDialog = (event) => {
    setDeletingEvent(event);
    setDeleteDialogOpen(true);
  };

  const openEditLogDialog = () => {
    setEditLogForm({
      location_id: log.location_id.toString(),
      log_date: new Date(log.log_date + 'T00:00:00'),
      notes: log.notes || ''
    });
    setEditLogDialogOpen(true);
  };

  const handleEditLogSubmit = async () => {
    if (!editLogForm.location_id) {
      toast.error('Please select a location');
      return;
    }
    if (!editLogForm.log_date) {
      toast.error('Please select a date');
      return;
    }
    setSavingLog(true);
    try {
      await updateDailyLog(id, {
        location_id: parseInt(editLogForm.location_id),
        log_date: format(editLogForm.log_date, 'yyyy-MM-dd'),
        notes: editLogForm.notes || null
      });
      toast.success('Daily log updated successfully');
      setEditLogDialogOpen(false);
      loadLog();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update daily log');
    } finally {
      setSavingLog(false);
    }
  };

  const handleDelete = async () => {
    try {
      await deleteEvent(deletingEvent.id);
      toast.success('Event deleted successfully');
      setDeleteDialogOpen(false);
      loadLog();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete event');
    }
  };

  const openAddEventDialog = () => {
    setAddEventForm({
      event_type: 'birth',
      species: 'cattle',
      category_id: '',
      count: 0,
      from_location_id: '',
      to_location_id: '',
      from_category_id: '',
      to_category_id: '',
      notes: '',
      is_stock_event: true,
    });
    setAddEventDialogOpen(true);
  };

  const handleAddEventSubmit = async () => {
    setAddingEvent(true);
    try {
      const payload = {
        event_type: addEventForm.event_type,
        species: addEventForm.species,
        count: parseInt(addEventForm.count) || 0,
        notes: addEventForm.notes || null,
        is_stock_event: addEventForm.is_stock_event,
      };
      if (addEventForm.category_id) payload.category_id = parseInt(addEventForm.category_id);
      if (addEventForm.from_location_id) payload.from_location_id = parseInt(addEventForm.from_location_id);
      if (addEventForm.to_location_id) payload.to_location_id = parseInt(addEventForm.to_location_id);
      if (addEventForm.from_category_id) payload.from_category_id = parseInt(addEventForm.from_category_id);
      if (addEventForm.to_category_id) payload.to_category_id = parseInt(addEventForm.to_category_id);

      await createEvent(id, payload);
      toast.success('Event added successfully');
      setAddEventDialogOpen(false);
      loadLog();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add event');
    } finally {
      setAddingEvent(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!log) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Daily log not found</p>
        <Link to="/daily-logs">
          <Button variant="link">Back to Daily Logs</Button>
        </Link>
      </div>
    );
  }

  const eventsList = log.events || [];
  const speciesCategories = categories[editForm.species] || [];
  const addSpeciesCategories = categories[addEventForm.species] || [];
  const canEdit = isAdmin; // Admin can edit even locked logs

  return (
    <div className="space-y-6 max-w-4xl mx-auto" data-testid="daily-log-detail-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-heading text-3xl font-bold">Daily Log</h1>
              {log.is_locked && (
                <Badge className="bg-green-100 text-green-800 gap-1">
                  <Lock className="h-3 w-3" />
                  Locked
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4 text-muted-foreground mt-1">
              <span className="flex items-center gap-1">
                <CalendarBlank className="h-4 w-4" />
                {formatDate(log.log_date)}
              </span>
              <span className="flex items-center gap-1">
                <MapPin className="h-4 w-4" />
                {log.location_name}
              </span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {isAdmin && (
            <Button
              onClick={openEditLogDialog}
              variant="outline"
              className="gap-2"
              data-testid="edit-log-btn"
            >
              <Pencil className="h-4 w-4" />
              Edit Log
            </Button>
          )}
          {!log.is_locked && isAdmin && (
            <Button 
              onClick={handleLock} 
              disabled={locking}
              variant="outline"
              className="gap-2"
              data-testid="lock-log-btn"
            >
              <Lock className="h-4 w-4" />
              {locking ? 'Locking...' : 'Lock Log'}
            </Button>
          )}
        </div>
      </div>

      <Card className="border-border/60">
        <CardContent className="p-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <p className="font-semibold mt-1">
                {log.has_events ? 'Has Events' : 'No Events'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Total Events</p>
              <p className="text-2xl font-bold font-heading">{eventsList.length}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Created</p>
              <p className="font-semibold mt-1">{formatDateTime(log.created_at)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Review Status</p>
              <p className="font-semibold mt-1 flex items-center gap-1">
                {log.is_locked ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-success" />
                    Reviewed
                  </>
                ) : (
                  'Pending Review'
                )}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="font-heading">Events</CardTitle>
          {isAdmin && (
            <Button onClick={openAddEventDialog} size="sm" className="gap-2" data-testid="add-event-btn">
              <Plus className="h-4 w-4" />
              Add Event
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {eventsList.length > 0 ? (
            <div className="space-y-4">
              {eventsList.map((event, idx) => {
                const eventConfig = EVENT_TYPES[event.event_type];
                const speciesConfig = SPECIES_CONFIG[event.species];
                
                return (
                  <div 
                    key={idx}
                    className="p-4 rounded-lg border border-border bg-muted/30"
                    data-testid={`event-detail-${idx}`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Badge className={eventConfig?.color}>
                          {eventConfig?.label || event.event_type}
                        </Badge>
                        <Badge variant="outline" style={{ borderColor: speciesConfig?.color, color: speciesConfig?.color }}>
                          {speciesConfig?.label?.split(' ')[0]}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-2xl font-bold font-heading">
                          {event.count}
                        </span>
                        {canEdit && (
                          <>
                            <Button 
                              variant="ghost" 
                              size="icon"
                              onClick={() => openEditDialog(event)}
                              data-testid={`edit-event-${idx}`}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button 
                              variant="ghost" 
                              size="icon"
                              onClick={() => openDeleteDialog(event)}
                              data-testid={`delete-event-${idx}`}
                            >
                              <Trash className="h-4 w-4 text-destructive" />
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                      {event.category_name_sw && (
                        <div>
                          <span className="text-muted-foreground">Category: </span>
                          <span className="font-medium">{event.category_name_sw}</span>
                        </div>
                      )}
                      
                      {event.event_type === 'transfer' && (
                        <div className="flex items-center gap-2 p-2 bg-orange-50 rounded">
                          <ArrowsLeftRight className="h-4 w-4 text-orange-600" />
                          <span>
                            {event.from_location_name || 'Unknown'} to {event.to_location_name || 'Unknown'}
                          </span>
                        </div>
                      )}
                      
                      {event.event_type === 'category_change' && (
                        <div className="flex items-center gap-2 p-2 bg-indigo-50 rounded">
                          <ArrowsDownUp className="h-4 w-4 text-indigo-600" />
                          <span>
                            {event.from_category_name_sw || 'Unknown'} to {event.to_category_name_sw || 'Unknown'}
                          </span>
                        </div>
                      )}
                      
                      {event.notes && (
                        <div className="col-span-full">
                          <span className="text-muted-foreground">Notes: </span>
                          <span>{event.notes}</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <CalendarBlank className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>No events recorded for this day</p>
            </div>
          )}
        </CardContent>
      </Card>

      {(log.notes || isAdmin) && (
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle className="font-heading">Additional Notes</CardTitle>
          </CardHeader>
          <CardContent>
            {log.notes ? (
              <p className="text-muted-foreground">{log.notes}</p>
            ) : (
              <p className="text-muted-foreground italic text-sm">No notes — click "Edit Log" to add notes.</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Add Event Dialog */}
      <Dialog open={addEventDialogOpen} onOpenChange={setAddEventDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Add Event</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Event Type</Label>
                <Select
                  value={addEventForm.event_type}
                  onValueChange={(v) => setAddEventForm({ ...addEventForm, event_type: v })}
                >
                  <SelectTrigger data-testid="add-event-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EVENT_TYPE_OPTIONS.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Species</Label>
                <Select
                  value={addEventForm.species}
                  onValueChange={(v) => setAddEventForm({ ...addEventForm, species: v, category_id: '', from_category_id: '', to_category_id: '' })}
                >
                  <SelectTrigger data-testid="add-species">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(SPECIES_CONFIG).map(([key, config]) => (
                      <SelectItem key={key} value={key}>{config.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Count</Label>
              <Input
                type="number"
                min="0"
                value={addEventForm.count}
                onChange={(e) => setAddEventForm({ ...addEventForm, count: e.target.value })}
                data-testid="add-count"
              />
            </div>

            {addEventForm.event_type !== 'category_change' && addEventForm.event_type !== 'abortion' && (
              <div className="space-y-2">
                <Label>Category</Label>
                <Select
                  value={addEventForm.category_id}
                  onValueChange={(v) => setAddEventForm({ ...addEventForm, category_id: v })}
                >
                  <SelectTrigger data-testid="add-category">
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {addSpeciesCategories.map(cat => (
                      <SelectItem key={cat.id} value={cat.id.toString()}>
                        {cat.name_sw} ({cat.name_en})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {addEventForm.event_type === 'transfer' && (
              <div className="grid grid-cols-2 gap-4 p-3 bg-orange-50 rounded-lg">
                <div className="space-y-2">
                  <Label>From Location</Label>
                  <Select
                    value={addEventForm.from_location_id}
                    onValueChange={(v) => setAddEventForm({ ...addEventForm, from_location_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      {locations.map(loc => (
                        <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>To Location</Label>
                  <Select
                    value={addEventForm.to_location_id}
                    onValueChange={(v) => setAddEventForm({ ...addEventForm, to_location_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Destination" />
                    </SelectTrigger>
                    <SelectContent>
                      {locations.map(loc => (
                        <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {addEventForm.event_type === 'category_change' && (
              <div className="grid grid-cols-2 gap-4 p-3 bg-indigo-50 rounded-lg">
                <div className="space-y-2">
                  <Label>From Category</Label>
                  <Select
                    value={addEventForm.from_category_id}
                    onValueChange={(v) => setAddEventForm({ ...addEventForm, from_category_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      {addSpeciesCategories.map(cat => (
                        <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>To Category</Label>
                  <Select
                    value={addEventForm.to_category_id}
                    onValueChange={(v) => setAddEventForm({ ...addEventForm, to_category_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Destination" />
                    </SelectTrigger>
                    <SelectContent>
                      {addSpeciesCategories.map(cat => (
                        <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>Notes</Label>
              <Input
                value={addEventForm.notes}
                onChange={(e) => setAddEventForm({ ...addEventForm, notes: e.target.value })}
                placeholder="Optional notes"
                data-testid="add-notes"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setAddEventDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleAddEventSubmit} disabled={addingEvent} data-testid="save-add-event-btn">
                {addingEvent ? 'Adding...' : 'Add Event'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Log Dialog */}
      <Dialog open={editLogDialogOpen} onOpenChange={setEditLogDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Edit Daily Log</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Location</Label>
              <Select
                value={editLogForm.location_id}
                onValueChange={(v) => setEditLogForm({ ...editLogForm, location_id: v })}
              >
                <SelectTrigger data-testid="edit-log-location">
                  <SelectValue placeholder="Select location" />
                </SelectTrigger>
                <SelectContent>
                  {locations.map(loc => (
                    <SelectItem key={loc.id} value={loc.id.toString()}>
                      <div className="flex items-center gap-2">
                        <MapPin className="h-4 w-4" />
                        {loc.name}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Date</Label>
              <Popover open={logDateOpen} onOpenChange={setLogDateOpen}>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="w-full justify-start gap-2" data-testid="edit-log-date">
                    <CalendarBlank className="h-4 w-4" />
                    {editLogForm.log_date ? format(editLogForm.log_date, 'PPP') : 'Pick a date'}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={editLogForm.log_date}
                    onSelect={(date) => {
                      if (date) {
                        setEditLogForm({ ...editLogForm, log_date: date });
                        setLogDateOpen(false);
                      }
                    }}
                  />
                </PopoverContent>
              </Popover>
            </div>

            <div className="space-y-2">
              <Label>Additional Notes</Label>
              <Textarea
                value={editLogForm.notes}
                onChange={(e) => setEditLogForm({ ...editLogForm, notes: e.target.value })}
                placeholder="Optional notes about this log..."
                rows={3}
                data-testid="edit-log-notes"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setEditLogDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleEditLogSubmit} disabled={savingLog} data-testid="save-log-btn">
                {savingLog ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Event Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Edit Event</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Event Type</Label>
                <Select 
                  value={editForm.event_type} 
                  onValueChange={(v) => setEditForm({ ...editForm, event_type: v })}
                >
                  <SelectTrigger data-testid="edit-event-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EVENT_TYPE_OPTIONS.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Species</Label>
                <Select 
                  value={editForm.species} 
                  onValueChange={(v) => setEditForm({ ...editForm, species: v, category_id: '', from_category_id: '', to_category_id: '' })}
                >
                  <SelectTrigger data-testid="edit-species">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(SPECIES_CONFIG).map(([key, config]) => (
                      <SelectItem key={key} value={key}>{config.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Count</Label>
              <Input
                type="number"
                min="0"
                value={editForm.count}
                onChange={(e) => setEditForm({ ...editForm, count: e.target.value })}
                data-testid="edit-count"
              />
            </div>

            {editForm.event_type !== 'category_change' && editForm.event_type !== 'abortion' && (
              <div className="space-y-2">
                <Label>Category</Label>
                <Select 
                  value={editForm.category_id} 
                  onValueChange={(v) => setEditForm({ ...editForm, category_id: v })}
                >
                  <SelectTrigger data-testid="edit-category">
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {speciesCategories.map(cat => (
                      <SelectItem key={cat.id} value={cat.id.toString()}>
                        {cat.name_sw} ({cat.name_en})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {editForm.event_type === 'transfer' && (
              <div className="grid grid-cols-2 gap-4 p-3 bg-orange-50 rounded-lg">
                <div className="space-y-2">
                  <Label>From Location</Label>
                  <Select 
                    value={editForm.from_location_id} 
                    onValueChange={(v) => setEditForm({ ...editForm, from_location_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      {locations.map(loc => (
                        <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>To Location</Label>
                  <Select 
                    value={editForm.to_location_id} 
                    onValueChange={(v) => setEditForm({ ...editForm, to_location_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Destination" />
                    </SelectTrigger>
                    <SelectContent>
                      {locations.map(loc => (
                        <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {editForm.event_type === 'category_change' && (
              <div className="grid grid-cols-2 gap-4 p-3 bg-indigo-50 rounded-lg">
                <div className="space-y-2">
                  <Label>From Category</Label>
                  <Select 
                    value={editForm.from_category_id} 
                    onValueChange={(v) => setEditForm({ ...editForm, from_category_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Source" />
                    </SelectTrigger>
                    <SelectContent>
                      {speciesCategories.map(cat => (
                        <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>To Category</Label>
                  <Select 
                    value={editForm.to_category_id} 
                    onValueChange={(v) => setEditForm({ ...editForm, to_category_id: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Destination" />
                    </SelectTrigger>
                    <SelectContent>
                      {speciesCategories.map(cat => (
                        <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>Notes</Label>
              <Input
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                placeholder="Optional notes"
                data-testid="edit-notes"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleEditSubmit} disabled={saving} data-testid="save-edit-btn">
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Event</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this event? This will reverse any stock changes made by this event. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleDelete} 
              className="bg-destructive text-destructive-foreground"
              data-testid="confirm-delete-btn"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default DailyLogDetail;
