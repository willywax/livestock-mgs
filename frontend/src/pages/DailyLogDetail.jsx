import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getDailyLog, lockDailyLog, createEvent, updateEvent, deleteEvent, getCategories, getLocations, updateDailyLog, getDiseases, listDeathCauses } from '../lib/api';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/tooltip';
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
import { ArrowLeft, CalendarBlank, MapPin, Lock, CheckCircle, ArrowsLeftRight, ArrowsDownUp, Pencil, Trash, Plus, Eye } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { EVENT_TYPES, SPECIES_CONFIG, formatDate, formatDateTime } from '../lib/utils';
import { format } from 'date-fns';
import { EventFormItem, blankEvent, applyEventChange, eventFromApi, validateEvent, eventToCreatePayload, eventToUpdatePayload } from '../components/EventForm';

// Event types with their own detail block in the event sheet; every other type uses the generic block.
const typeSpecificTypes = ['death', 'birth', 'sold', 'gift_in', 'gift_out'];

const DailyLogDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [log, setLog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [locking, setLocking] = useState(false);
  const [categories, setCategories] = useState({});
  const [locations, setLocations] = useState([]);
  const { isAdmin, isDataEntry } = useAuth();

  // Detail sheet state
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Diseases for DEATH edit select
  const [diseases, setDiseases] = useState([]);
  const [deathCauses, setDeathCauses] = useState([]);

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
  const [addEventForm, setAddEventForm] = useState(blankEvent());
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
      const [cattleRes, sheepRes, goatRes, locRes, diseaseRes] = await Promise.all([
        getCategories('cattle'),
        getCategories('sheep'),
        getCategories('goat'),
        getLocations(),
        getDiseases(),
      ]);
      setCategories({
        cattle: cattleRes.data,
        sheep: sheepRes.data,
        goat: goatRes.data
      });
      setLocations(locRes.data);
      setDiseases(diseaseRes.data);
    } catch (error) {
      console.error('Failed to load categories');
    }
    try {
      // Inactive causes are included so an old event keeps showing its cause while it is edited
      const [active, inactive] = await Promise.all([listDeathCauses(), listDeathCauses({ is_active: false })]);
      setDeathCauses([...active.data, ...inactive.data]);
    } catch (error) {
      // Cause list is optional: deaths can still be saved without a structured cause
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
    setEditForm(eventFromApi(event));
    setEditDialogOpen(true);
  };

  const handleEditSubmit = async () => {
    const problem = validateEvent(editForm);
    if (problem) {
      toast.error(problem);
      return;
    }
    setSaving(true);
    try {
      await updateEvent(editingEvent.id, eventToUpdatePayload(editForm));
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
    setAddEventForm(blankEvent());
    setAddEventDialogOpen(true);
  };

  const handleAddEventSubmit = async () => {
    const problem = validateEvent(addEventForm);
    if (problem) {
      toast.error(problem);
      return;
    }
    setAddingEvent(true);
    try {
      await createEvent(id, eventToCreatePayload(addEventForm));
      toast.success('Event added successfully');
      setAddEventDialogOpen(false);
      loadLog();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add event');
    } finally {
      setAddingEvent(false);
    }
  };

  const formatTZS = (amount) =>
    amount != null ? `TZS ${Number(amount).toLocaleString()}` : '—';

  const DetailRow = ({ label, value }) => (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-medium text-sm">{value || '—'}</span>
    </div>
  );

  const openDetailSheet = (event) => {
    setSelectedEvent(event);
    setDetailSheetOpen(true);
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
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openDetailSheet(event)}
                          data-testid={`view-event-${idx}`}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
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

      {/* ===== Event Detail / Edit Sheet ===== */}
      <Sheet
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
      >
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          {selectedEvent && (() => {
            const eventConfig = EVENT_TYPES[selectedEvent.event_type];
            const speciesConfig = SPECIES_CONFIG[selectedEvent.species];
            const et = selectedEvent.event_type;
            const canEditInSheet = isDataEntry;
            const isLocked = log?.is_locked;
            return (
              <>
                <SheetHeader className="mb-4">
                  <SheetTitle className="font-heading">Event Details</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <Badge className={eventConfig?.color}>
                      {eventConfig?.label || et}
                    </Badge>
                    <Badge
                      variant="outline"
                      style={{ borderColor: speciesConfig?.color, color: speciesConfig?.color }}
                    >
                      {speciesConfig?.label?.split(' ')[0]}
                    </Badge>
                    {isLocked && (
                      <Badge className="bg-green-100 text-green-800 gap-1">
                        <Lock className="h-3 w-3" /> Locked
                      </Badge>
                    )}
                  </div>
                </SheetHeader>

                {/* Always-visible summary */}
                <div className="grid grid-cols-2 gap-3 mb-5 p-3 bg-muted/40 rounded-lg text-sm">
                  <div>
                    <p className="text-xs text-muted-foreground">Category</p>
                    <p className="font-medium">{selectedEvent.category_name_sw || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Count</p>
                    <p className="font-bold text-lg leading-tight">{selectedEvent.count}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-xs text-muted-foreground">Recorded</p>
                    <p className="font-medium">{formatDateTime(selectedEvent.created_at)}</p>
                  </div>
                </div>

                  <div className="space-y-3">
                    {et === 'death' && (
                      <>
                        <DetailRow label="Cause of Death" value={selectedEvent.cause_of_death} />
                        <DetailRow label="Disease" value={selectedEvent.disease_name} />
                        <DetailRow label="Days Sick" value={selectedEvent.days_sick?.toString()} />
                        <DetailRow label="Attending Vet" value={selectedEvent.attending_vet} />
                        <DetailRow label="Animal Tags" value={selectedEvent.animal_tags} />
                        <DetailRow label="Notes" value={selectedEvent.notes} />
                      </>
                    )}
                    {et === 'birth' && (
                      <>
                        <DetailRow label="Mother Tag" value={selectedEvent.mother_tag} />
                        <DetailRow label="Offspring Tags" value={selectedEvent.offspring_tags} />
                        <DetailRow label="Animal Tags" value={selectedEvent.animal_tags} />
                        <DetailRow label="Notes" value={selectedEvent.notes} />
                      </>
                    )}
                    {et === 'sold' && (
                      <>
                        <DetailRow label="Buyer Name" value={selectedEvent.buyer_name} />
                        <DetailRow label="Buyer Phone" value={selectedEvent.buyer_phone} />
                        <DetailRow label="Buyer Address" value={selectedEvent.buyer_address} />
                        <DetailRow label="Sale Price" value={formatTZS(selectedEvent.sale_price)} />
                        <DetailRow label="Animal Tags" value={selectedEvent.animal_tags} />
                        <DetailRow label="Notes" value={selectedEvent.notes} />
                      </>
                    )}
                    {(et === 'gift_in' || et === 'gift_out') && (
                      <>
                        <DetailRow
                          label={et === 'gift_in' ? 'Giver Name' : 'Recipient Name'}
                          value={selectedEvent.gift_party_name}
                        />
                        <DetailRow label="Phone" value={selectedEvent.gift_party_phone} />
                        <DetailRow label="Reason" value={selectedEvent.gift_reason} />
                        <DetailRow label="Animal Tags" value={selectedEvent.animal_tags} />
                        <DetailRow label="Notes" value={selectedEvent.notes} />
                      </>
                    )}
                    {!typeSpecificTypes.includes(et) && (
                      <>
                        {selectedEvent.from_location_name && (
                          <DetailRow label="From Location" value={selectedEvent.from_location_name} />
                        )}
                        {selectedEvent.to_location_name && (
                          <DetailRow label="To Location" value={selectedEvent.to_location_name} />
                        )}
                        {selectedEvent.from_category_name_sw && (
                          <DetailRow label="From Category" value={selectedEvent.from_category_name_sw} />
                        )}
                        {selectedEvent.to_category_name_sw && (
                          <DetailRow label="To Category" value={selectedEvent.to_category_name_sw} />
                        )}
                        <DetailRow label="Notes" value={selectedEvent.notes} />
                      </>
                    )}
                  </div>

                {/* Sheet footer */}
                <div className="flex items-center justify-between mt-6 pt-4 border-t gap-2">
                  <div>
                    {canEditInSheet && (
                      isLocked && !isAdmin ? (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="flex items-center gap-1 text-muted-foreground text-sm cursor-default select-none">
                                <Lock className="h-4 w-4" />
                                Locked
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>Locked — only an admin can edit</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      ) : (
                        <div className="flex items-center gap-2">
                          {isLocked && isAdmin && (
                            <Badge className="bg-amber-100 text-amber-800 text-xs">
                              Editing a locked log
                            </Badge>
                          )}
                          <Button size="sm" onClick={() => { setDetailSheetOpen(false); openEditDialog(selectedEvent); }}>
                            Edit
                          </Button>
                        </div>
                      )
                    )}
                  </div>
                </div>
              </>
            );
          })()}
        </SheetContent>
      </Sheet>

      {/* Add Event Dialog */}
      <Dialog open={addEventDialogOpen} onOpenChange={setAddEventDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Add Event</DialogTitle>
          </DialogHeader>
          <EventFormItem
            event={addEventForm}
            index={0}
            categories={categories}
            locations={locations}
            diseases={diseases}
            deathCauses={deathCauses}
            locationId={log.location_id}
            logDate={new Date(log.log_date + 'T00:00:00')}
            onUpdate={(i, field, value) => setAddEventForm((prev) => applyEventChange(prev, field, value))}
            onPatch={(i, patch) => setAddEventForm((prev) => ({ ...prev, ...patch }))}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setAddEventDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddEventSubmit} disabled={addingEvent} data-testid="save-add-event-btn">
              {addingEvent ? 'Adding...' : 'Add Event'}
            </Button>
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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">Edit Event</DialogTitle>
          </DialogHeader>
          <EventFormItem
            mode="edit"
            event={editForm}
            index={0}
            categories={categories}
            locations={locations}
            diseases={diseases}
            deathCauses={deathCauses}
            locationId={log.location_id}
            logDate={new Date(log.log_date + 'T00:00:00')}
            onUpdate={(i, field, value) => setEditForm((prev) => applyEventChange(prev, field, value))}
            onPatch={(i, patch) => setEditForm((prev) => ({ ...prev, ...patch }))}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleEditSubmit} disabled={saving} data-testid="save-edit-btn">
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
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
