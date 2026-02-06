import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getDailyLog, lockDailyLog, updateEvent, deleteEvent, getCategories, getLocations } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../components/ui/alert-dialog';
import { ArrowLeft, CalendarBlank, MapPin, Lock, CheckCircle, ArrowsLeftRight, ArrowsDownUp, Pencil, Trash } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { EVENT_TYPES, SPECIES_CONFIG, formatDate, formatDateTime } from '../lib/utils';

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

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);

  // Delete dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingEvent, setDeletingEvent] = useState(null);

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
        <CardHeader>
          <CardTitle className="font-heading">Events</CardTitle>
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

      {log.notes && (
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle className="font-heading">Additional Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">{log.notes}</p>
          </CardContent>
        </Card>
      )}

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
