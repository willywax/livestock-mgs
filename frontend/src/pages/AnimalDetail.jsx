import DailyLogTimeline from '../components/DailyLogTimeline';
import ReproductiveEventDialog from '../components/ReproductiveEventDialog';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { differenceInCalendarDays, format, intervalToDuration } from 'date-fns';
import { toast } from 'sonner';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  ArrowLeft, ArrowRight, ArrowsLeftRight, Baby, Camera, CaretDown, CaretRight, LinkSimple, Pencil, Plus, Star, Stethoscope, Trash, Warning, X,
} from '@phosphor-icons/react';
import { useAuth } from '../context/AuthContext';
import {
  getAnimalDetail, getAnimalPhotos, uploadAnimalPhoto, updateAnimalPhoto, deleteAnimalPhoto,
  getAnimalTimeline, getAnimalReproductiveHistory, getAnimalBCSHistory,
  getAnimalNotes, createAnimalNote, updateAnimalNote, deleteAnimalNote, getAnimalLocationHistory,
  replaceAnimalTag,
  getAnimalIdentifiers, createAnimalIdentifier, updateAnimalIdentifier,
  getReproductiveSummary, listReproductiveEvents,
  getAnimalTransitionHistory,
} from '../lib/api';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Skeleton } from '../components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../components/ui/collapsible';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../components/ui/alert-dialog';
import {
  DateField, RecordBCSDialog, RecordCalvingDialog, RecordPDDialog, RecordServiceDialog,
  getTerms, intervalTone, parseDate, toISODate,
} from '../components/ReproductionDialogs';
import { cn } from '../lib/utils';

const MAX_PHOTO_BYTES = 10 * 1024 * 1024;
const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const SPECIES_BADGE = {
  cattle: 'bg-amber-900/10 text-amber-900',
  sheep: 'bg-blue-100 text-blue-700',
  goat: 'bg-amber-100 text-amber-700',
};
const SEX_BADGE = { male: 'bg-blue-100 text-blue-700', female: 'bg-pink-100 text-pink-700' };
const STATUS_BADGE = {
  active: 'bg-green-100 text-green-700',
  sold: 'bg-gray-100 text-gray-600',
  dead: 'bg-red-100 text-red-700',
  transferred: 'bg-blue-100 text-blue-700',
  missing: 'bg-amber-100 text-amber-700',
};
const CYCLE_STATUS_BADGE = {
  open: 'bg-gray-100 text-gray-600',
  served: 'bg-blue-100 text-blue-700',
  pregnant: 'bg-green-100 text-green-700',
  calved: 'bg-purple-100 text-purple-700',
  aborted: 'bg-red-100 text-red-700',
};
const PD_BADGE = { pregnant: 'bg-green-100 text-green-700', open: 'bg-red-100 text-red-700', repeat: 'bg-amber-100 text-amber-700' };
const OUTCOME_BADGE = {
  live_calf: 'bg-green-100 text-green-700',
  stillbirth: 'bg-red-100 text-red-700',
  abortion: 'bg-amber-100 text-amber-700',
  assisted_live: 'bg-orange-100 text-orange-700',
  assisted_dead: 'bg-orange-100 text-orange-700',
};
const NOTE_BADGE = {
  observation: 'bg-blue-100 text-blue-700',
  weight: 'bg-purple-100 text-purple-700',
  measurement: 'bg-teal-100 text-teal-700',
  incident: 'bg-red-100 text-red-700',
  health: 'bg-green-100 text-green-700',
  other: 'bg-gray-100 text-gray-600',
};
const NOTE_TYPES = ['observation', 'weight', 'measurement', 'incident', 'health', 'other'];
const TIMELINE_COLORS = {
  REPRODUCTION: '#7C3AED',
  HEALTH: '#0D9488',
  BCS: '#D97706',
  NOTE: '#6B7280',
  STOCK_EVENT: '#2563EB', // not returned by the timeline endpoint today
};
const TONE_TEXT = { green: 'text-green-700', amber: 'text-amber-600', red: 'text-red-600', grey: 'text-muted-foreground' };

const fmt = (s) => (s ? format(parseDate(s), 'dd MMM yyyy') : '—');
const failToast = (what) => () => toast.error(`Failed to load ${what}`);
const errText = (err, fallback) => {
  const d = err?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
};

function Badge({ className, children, title }) {
  return (
    <span title={title} className={cn('px-2 py-0.5 rounded-full text-xs font-semibold capitalize whitespace-nowrap', className)}>
      {children}
    </span>
  );
}

function formatAge(birthDate) {
  if (!birthDate) return 'Age unknown';
  const start = parseDate(birthDate);
  const now = new Date();
  if (start > now) return 'Age unknown';
  const d = intervalToDuration({ start, end: now });
  const parts = [];
  if (d.years) parts.push(`${d.years} ${d.years === 1 ? 'yr' : 'yrs'}`);
  if (d.months) parts.push(`${d.months} mo`);
  if (!parts.length) parts.push(`${d.days || 0} d`);
  return parts.join(' ');
}

// ---------------------------------------------------------------------------
// Photo gallery
// ---------------------------------------------------------------------------
function PhotoGallery({ animalId, photos, loading, canWrite, isAdmin, onChanged }) {
  const fileRef = useRef(null);
  const [activeId, setActiveId] = useState(null);
  const [file, setFile] = useState(null);
  const [caption, setCaption] = useState('');
  const [takenDate, setTakenDate] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const shown = photos.find((p) => p.id === activeId) || photos[0] || null;
  const warning = photos.find((p) => p.warning)?.warning;

  const resetForm = () => {
    setFile(null); setCaption(''); setTakenDate(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const onFile = (e) => {
    const picked = e.target.files[0];
    if (!picked) return;
    if (!PHOTO_TYPES.includes(picked.type)) {
      toast.error('Only JPEG, PNG or WebP images are accepted');
      e.target.value = '';
      return;
    }
    if (picked.size > MAX_PHOTO_BYTES) {
      toast.error('Photo is larger than 10 MB');
      e.target.value = '';
      return;
    }
    setFile(picked);
  };

  const upload = async () => {
    const form = new FormData();
    form.append('file', file);
    if (caption.trim()) form.append('caption', caption.trim());
    if (takenDate) form.append('taken_date', toISODate(takenDate));
    setUploading(true);
    try {
      const res = await uploadAnimalPhoto(animalId, form);
      toast.success('Photo added');
      setActiveId(res.data.id);
      resetForm();
      onChanged();
    } catch (err) {
      toast.error(errText(err, 'Failed to upload photo'));
    } finally {
      setUploading(false);
    }
  };

  const makePrimary = async (photo) => {
    try {
      await updateAnimalPhoto(animalId, photo.id, { is_primary: true });
      toast.success('Primary photo updated');
      onChanged();
    } catch (err) {
      toast.error(errText(err, 'Failed to update photo'));
    }
  };

  const confirmDelete = async () => {
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await deleteAnimalPhoto(animalId, target.id);
      toast.success('Photo deleted');
      if (activeId === target.id) setActiveId(null);
      onChanged();
    } catch (err) {
      toast.error(errText(err, 'Failed to delete photo'));
    }
  };

  return (
    <div className="space-y-3" data-testid="photo-gallery">
      {warning && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <Warning className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{warning}</span>
        </div>
      )}
      <div className="aspect-[4/3] w-full overflow-hidden rounded-lg bg-muted flex items-center justify-center">
        {loading ? (
          <Skeleton className="h-full w-full" />
        ) : shown && shown.photo_url ? (
          <img src={shown.photo_url} alt={shown.caption || 'Animal photo'} className="h-full w-full object-cover" />
        ) : (
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Camera className="h-12 w-12" />
            <span className="text-sm">{shown ? 'Photo unavailable' : 'No photos yet'}</span>
          </div>
        )}
      </div>
      {shown?.caption && <p className="text-sm text-muted-foreground">{shown.caption}</p>}

      {photos.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {photos.map((p) => (
            <div key={p.id} className="group relative shrink-0">
              <button
                type="button"
                onClick={() => setActiveId(p.id)}
                title={p.caption || undefined}
                data-testid={`photo-thumb-${p.id}`}
                className={cn(
                  'relative h-16 w-16 overflow-hidden rounded-md bg-muted',
                  shown && shown.id === p.id && 'ring-2 ring-primary'
                )}
              >
                {p.photo_url ? (
                  <img src={p.photo_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Camera className="m-auto h-6 w-6 text-muted-foreground" />
                )}
                {p.caption && (
                  <span className="absolute inset-x-0 bottom-0 truncate bg-black/60 px-1 text-[10px] text-white opacity-0 group-hover:opacity-100">
                    {p.caption}
                  </span>
                )}
              </button>
              {p.is_primary && (
                <Star weight="fill" className="pointer-events-none absolute left-0.5 top-0.5 h-4 w-4 text-amber-400 drop-shadow" />
              )}
              <div className="absolute right-0 top-0 flex flex-col gap-0.5 opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
                {canWrite && !p.is_primary && (
                  <button
                    type="button" title="Make primary" aria-label="Make primary"
                    onClick={() => makePrimary(p)}
                    data-testid={`photo-primary-${p.id}`}
                    className="rounded-full bg-white/90 p-0.5 shadow"
                  >
                    <Star className="h-3.5 w-3.5 text-amber-600" />
                  </button>
                )}
                {isAdmin && (
                  <button
                    type="button" title="Delete photo" aria-label="Delete photo"
                    onClick={() => setDeleteTarget(p)}
                    data-testid={`photo-delete-${p.id}`}
                    className="rounded-full bg-white/90 p-0.5 shadow"
                  >
                    <X className="h-3.5 w-3.5 text-red-600" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {canWrite && (
        <div className="space-y-2">
          <input
            ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
            onChange={onFile} data-testid="photo-file-input"
          />
          {!file ? (
            <Button variant="outline" size="sm" className="gap-2" onClick={() => fileRef.current?.click()} data-testid="add-photo-btn">
              <Camera className="h-4 w-4" />Add photo
            </Button>
          ) : (
            <div className="space-y-2 rounded-lg border p-3">
              <p className="truncate text-xs text-muted-foreground">{file.name}</p>
              <Input placeholder="Caption (optional)" value={caption} maxLength={255} onChange={(e) => setCaption(e.target.value)} />
              <DateField value={takenDate} onChange={setTakenDate} testId="photo-date" />
              <div className="flex gap-2">
                <Button size="sm" onClick={upload} disabled={uploading} data-testid="photo-upload-btn">
                  {uploading ? 'Uploading…' : 'Upload'}
                </Button>
                <Button size="sm" variant="outline" onClick={resetForm} disabled={uploading}>Cancel</Button>
              </div>
            </div>
          )}
        </div>
      )}

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => { if (!o) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this photo?</AlertDialogTitle>
            <AlertDialogDescription>The image is removed from storage and cannot be recovered.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Identity card
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Replace-temporary-tag dialog (POST /animals/{id}/replace-tag)
// ---------------------------------------------------------------------------
function ReplaceTagDialog({ open, onClose, animal, onReplaced }) {
  const [newTag, setNewTag] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setNewTag(''); setError(''); }
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    const tag = newTag.trim();
    if (!tag) return;
    setSaving(true);
    setError('');
    try {
      await replaceAnimalTag(animal.id, tag);
      toast.success(`Tag replaced — ${animal.tag_number} → ${tag}`);
      onReplaced();
      onClose();
    } catch (err) {
      const status = err?.response?.status;
      if (status === 409) setError('This tag is already in use at this location');
      else if (status === 400) setError(errText(err, 'Could not replace the tag'));
      else toast.error(errText(err, 'Failed to replace tag'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-sm" data-testid="replace-tag-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">Replace temporary tag</DialogTitle>
          <DialogDescription>
            Current tag: <span className="font-mono">{animal.tag_number}</span>
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="new_tag_number">New tag number</Label>
            <Input
              id="new_tag_number"
              value={newTag}
              onChange={(e) => { setNewTag(e.target.value); setError(''); }}
              required
              minLength={1}
              className="font-mono"
              data-testid="new-tag-input"
            />
            <p className="text-xs text-muted-foreground">Enter the real tag from the ear tag or EID chip</p>
            {error && <p className="text-sm text-red-600" data-testid="replace-tag-error">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={saving || !newTag.trim()} data-testid="replace-tag-submit">
              {saving ? 'Replacing...' : 'Replace tag'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const IDENTIFIER_LABELS = {
  eid: 'EID (ISO)', uhf_tag: 'UHF Tag', reader_code: 'Reader / EPC',
  visual_tag: 'Visual Tag', branding_mark: 'Branding Mark', other: 'Other',
};

function Identifiers({ animalId, canWrite }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await getAnimalIdentifiers(animalId);
      setItems(response.data);
    } catch (err) {
      setError(errText(err, 'Failed to load identifiers'));
    } finally {
      setLoading(false);
    }
  }, [animalId]);
  useEffect(() => { load(); }, [load]);
  const open = (item) => setForm({
    id: item?.id, id_type: item?.id_type || 'eid', id_value: item?.id_value || '',
    recorded_date: item?.recorded_date || '', notes: item?.notes || '',
  });
  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const data = { id_value: form.id_value.trim(), recorded_date: form.recorded_date || null, notes: form.notes || null };
      if (form.id) await updateAnimalIdentifier(animalId, form.id, data);
      else await createAnimalIdentifier(animalId, { ...data, id_type: form.id_type });
      setForm(null);
      toast.success('Identifier saved');
      await load();
    } catch (err) {
      toast.error(errText(err, 'Failed to save identifier'));
    } finally { setBusy(false); }
  };
  const toggleActive = async (item) => {
    setBusy(true);
    try {
      await updateAnimalIdentifier(animalId, item.id, { is_active: !item.is_active });
      toast.success('Identifier saved');
      await load();
    } catch (err) {
      toast.error(errText(err, 'Failed to deactivate identifier'));
    } finally { setBusy(false); }
  };
  return (
    <section className="space-y-2 border-t pt-3" aria-label="Identifiers">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">Identifiers</h2>
        {canWrite && <Button size="sm" variant="outline" disabled={busy} onClick={() => open(null)}><Plus className="mr-1 h-4 w-4" />Add ID</Button>}
      </div>
      {loading ? <Skeleton className="h-16" /> : error ? (
        <div role="alert" className="text-sm text-red-600">{error}<Button variant="link" onClick={load}>Retry</Button></div>
      ) : items.length === 0 ? <p className="text-sm text-muted-foreground">No identifiers recorded</p> : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Type</TableHead><TableHead>Value</TableHead><TableHead>Active</TableHead><TableHead>Recorded</TableHead>{canWrite && <TableHead>Actions</TableHead>}</TableRow></TableHeader>
            <TableBody>{items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className={!item.is_active ? 'line-through' : ''}>{IDENTIFIER_LABELS[item.id_type]}</TableCell>
                <TableCell className={cn('font-mono break-all', !item.is_active && 'line-through')} title={item.notes || undefined}>{item.id_value}</TableCell>
                <TableCell>{item.is_active ? <span aria-label="Active">✓</span> : <Badge className="bg-amber-100 text-amber-800">inactive</Badge>}</TableCell>
                <TableCell className="whitespace-nowrap">{fmt(item.recorded_date)}</TableCell>
                {canWrite && <TableCell><div className="flex gap-1">
                  <Button size="icon" variant="ghost" disabled={busy} aria-label={`Edit ${IDENTIFIER_LABELS[item.id_type]}`} onClick={() => open(item)}><Pencil className="h-4 w-4" /></Button>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => toggleActive(item)}>{item.is_active ? 'Deactivate' : 'Activate'}</Button>
                </div></TableCell>}
              </TableRow>
            ))}</TableBody>
          </Table>
        </div>
      )}
      {canWrite && <Dialog open={!!form} onOpenChange={(value) => { if (!value && !busy) setForm(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>{form?.id ? 'Edit identifier' : 'Add identifier'}</DialogTitle><DialogDescription>Record an additional animal ID.</DialogDescription></DialogHeader>
          {form && <form onSubmit={save} className="space-y-4">
            <div className="space-y-2"><Label htmlFor="identifier-type">Type</Label>
              <Select value={form.id_type} disabled={!!form.id || busy} onValueChange={(value) => setForm({ ...form, id_type: value })}>
                <SelectTrigger id="identifier-type"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(IDENTIFIER_LABELS).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2"><Label htmlFor="identifier-value">Value</Label><Input id="identifier-value" required maxLength={100} value={form.id_value} disabled={busy} onChange={(e) => setForm({ ...form, id_value: e.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="identifier-date">Recorded date (optional)</Label><Input id="identifier-date" type="date" value={form.recorded_date} disabled={busy} onChange={(e) => setForm({ ...form, recorded_date: e.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="identifier-notes">Notes (optional)</Label><Textarea id="identifier-notes" value={form.notes} disabled={busy} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
            <DialogFooter><Button type="button" variant="outline" disabled={busy} onClick={() => setForm(null)}>Cancel</Button><Button type="submit" disabled={busy || !form.id_value.trim()}>{busy ? 'Saving…' : 'Save'}</Button></DialogFooter>
          </form>}
        </DialogContent>
      </Dialog>}
    </section>
  );
}

// Inline collapsible: last 3 category transitions; "Show all" lists the full history.
function CategoryHistory({ animalId }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAnimalTransitionHistory(animalId)
      .then((res) => { if (!cancelled) setRows(res.data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [animalId]);

  const visible = rows ? (showAll ? rows : rows.slice(0, 3)) : [];
  const triggerLabel = (t) => {
    if (t === 'manual') return 'Manual';
    if (t === 'first_calving') return 'First calving';
    const age = /^age_(\d+)m$/.exec(t || '');
    return age ? `Age ${age[1]} months` : (t || '—');
  };
  return (
    <Collapsible open={open} onOpenChange={setOpen} data-testid="category-history">
      <CollapsibleTrigger asChild>
        <button type="button" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          {open ? <CaretDown className="h-3 w-3" /> : <CaretRight className="h-3 w-3" />}
          Category history{rows ? ` (${rows.length})` : ''}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-2">
        {error ? (
          <p className="text-xs text-muted-foreground">Category history unavailable</p>
        ) : !rows ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">No category changes yet.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {visible.map((t) => (
              <li key={t.id} className="flex flex-wrap gap-x-2">
                <span className="text-muted-foreground">{fmt(t.transition_date)}</span>
                <span>{t.from_category} → {t.to_category}</span>
                <span className="text-muted-foreground">{triggerLabel(t.trigger)}</span>
              </li>
            ))}
          </ul>
        )}
        {rows && rows.length > 3 && (
          <button type="button" className="mt-1 text-xs underline" onClick={() => setShowAll((v) => !v)}>
            {showAll ? 'Show fewer' : `Show all (${rows.length})`}
          </button>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

function IdentityCard({ animal, canWrite, isAdmin, onReplaceTag, reproductiveSummary }) {
  const navigate = useNavigate();
  return (
    <Card data-testid="identity-card">
      <CardContent className="p-4 space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-bold font-mono">{animal.tag_number}</h1>
            {animal.is_temp_tag && canWrite && (
              <Button
                size="sm"
                className="bg-amber-500 text-white hover:bg-amber-600"
                onClick={onReplaceTag}
                data-testid="replace-tag-btn"
              >
                Replace tag
              </Button>
            )}
          </div>
          {animal.is_temp_tag && (
            <p
              className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-800"
              data-testid="temp-tag-banner"
            >
              ⚠ Temporary tag — replace when the animal is physically tagged
            </p>
          )}
          {animal.name && <p className="text-lg text-muted-foreground">{animal.name}</p>}
        </div>
        <Identifiers key={animal.id} animalId={animal.id} canWrite={canWrite} />
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={SPECIES_BADGE[animal.species]}>{animal.species}</Badge>
          <span className="text-sm">{animal.category_name_sw || '—'}</span>
        </div>
        <CategoryHistory key={`${animal.id}-${animal.category_id}`} animalId={animal.id} />
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={SEX_BADGE[animal.sex]}>{animal.sex}</Badge>
          <span className="text-sm">{formatAge(animal.birth_date)}</span>
        </div>
        {reproductiveSummary ? <div className="space-y-2" aria-label="Reproductive summary">
          <Badge className={{ open: 'bg-green-100 text-green-700', pregnant: 'bg-blue-100 text-blue-700',
            unknown: 'bg-gray-100 text-gray-600' }[reproductiveSummary.status] || 'bg-gray-100 text-gray-600'}>
            {reproductiveSummary.status || 'unknown'}
          </Badge>
          {reproductiveSummary.status === 'pregnant' && reproductiveSummary.months_pregnant != null && (
            <p className="text-sm">~{reproductiveSummary.months_pregnant} months pregnant</p>
          )}
          <p className="text-sm text-muted-foreground">Last {getTerms(animal.species).event.toLowerCase()}: {fmt(reproductiveSummary.last_calving_date)}</p>
          {reproductiveSummary.is_repeat_breeder && <Badge className="bg-amber-100 text-amber-800">
            Repeat breeder ({reproductiveSummary.services_without_conception} services)
          </Badge>}
        </div> : <p className="text-sm text-muted-foreground">Reproductive summary unavailable</p>}
        {animal.mother_tag && (
          <p className="text-sm" data-testid="dam-tag">
            <span className="text-muted-foreground">Dam: </span>
            {animal.mother_animal_id ? (
              <Link to={`/animals/${animal.mother_animal_id}`} className="text-primary underline underline-offset-2">
                {animal.mother_tag}
              </Link>
            ) : animal.mother_tag}
          </p>
        )}
        <p className="text-sm">{animal.location_name || '—'}</p>
        <div><Badge className={STATUS_BADGE[animal.status]}>{animal.status}</Badge></div>
        <p className="text-sm text-muted-foreground">
          <span className="capitalize">{animal.acquisition_type?.replace('_', ' ')}</span>
          {animal.acquisition_date ? ` · ${fmt(animal.acquisition_date)}` : ''}
        </p>
        {animal.registry_tag_id && (
          <span
            title="Legacy value from the removed Registry integration; read-only"
            className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
          >
            <LinkSimple className="h-3 w-3" />Legacy registry ID: {animal.registry_tag_id}
          </span>
        )}
        {canWrite && (
          <div className="flex gap-2 pt-1">
            <Button className="flex-1 gap-2" onClick={() => navigate(`/animals?edit=${animal.id}`)} data-testid="edit-animal-btn">
              <Pencil className="h-4 w-4" />Edit
            </Button>
            {isAdmin && animal.status === 'active' && (
              <Button
                variant="outline" className="flex-1 gap-2"
                onClick={() => navigate(`/animals?transfer=${animal.id}`)} data-testid="transfer-animal-btn"
              >
                <ArrowsLeftRight className="h-4 w-4" />Transfer
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Add-note dialog (shared by the Timeline and Notes tabs)
// ---------------------------------------------------------------------------
function AddNoteDialog({ open, onClose, onSaved, animalId }) {
  const [date, setDate] = useState(new Date());
  const [type, setType] = useState('observation');
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) { setDate(new Date()); setType('observation'); setContent(''); }
  }, [open]);

  const save = async () => {
    setSaving(true);
    try {
      await createAnimalNote(animalId, { note_date: toISODate(date), note_type: type, content: content.trim() });
      toast.success('Note added');
      onSaved();
      onClose();
    } catch (err) {
      toast.error(errText(err, 'Failed to add note'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-md" data-testid="note-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">Add note</DialogTitle>
          <DialogDescription>Notes appear in the timeline and the Notes tab.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Date</Label>
            <DateField value={date} onChange={setDate} testId="note-date" />
          </div>
          <div className="space-y-2">
            <Label>Type</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger data-testid="note-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                {NOTE_TYPES.map((t) => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Note</Label>
            <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={4} data-testid="note-content" />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving || !content.trim() || !date} data-testid="note-save">
            {saving ? 'Saving…' : 'Save note'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Tab 1: timeline
// ---------------------------------------------------------------------------
function TimelineTab({ items, loading, canWrite, onAddNote }) {
  return (
    <div className="space-y-4" data-testid="timeline-tab">
      {canWrite && (
        <div className="flex justify-end">
          <Button size="sm" className="gap-1" onClick={onAddNote} data-testid="timeline-add-note">
            <Plus className="h-4 w-4" />Add note
          </Button>
        </div>
      )}
      {loading ? (
        <div className="space-y-3">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No events recorded yet — service, health and note events will appear here
        </p>
      ) : (
        <ol>
          {items.map((item) => (
            <li
              key={`${item.source_table}-${item.source_id}-${item.title}`}
              className="relative ml-1.5 border-l-2 border-border pb-5 pl-5 last:border-transparent"
            >
              <span
                className="absolute -left-[7px] top-1 h-3 w-3 rounded-full"
                style={{ backgroundColor: TIMELINE_COLORS[item.event_category] || TIMELINE_COLORS.NOTE }}
              />
              <p className="text-sm text-muted-foreground">{fmt(item.date)}</p>
              <p className="font-medium">{item.title}</p>
              {item.detail && <p className="text-sm text-muted-foreground whitespace-pre-line">{item.detail}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 5: movement history (backend: animal_location_history, decision 0009)
// ---------------------------------------------------------------------------
function MovementHistoryTab({ items, loading }) {
  return (
    <div className="space-y-4" data-testid="movement-history-tab">
      {loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No location history recorded — movements are logged automatically when transfer events are saved
        </p>
      ) : (
        <ol>
          {items.map((m) => (
            <li
              key={m.id}
              className="relative ml-1.5 border-l-2 border-border pb-5 pl-5 last:border-transparent"
              data-testid={`movement-${m.id}`}
            >
              <span className="absolute -left-[7px] top-1 h-3 w-3 rounded-full bg-blue-600" />
              <p className="text-sm text-muted-foreground">{fmt(m.moved_date)}</p>
              {m.from_location_id || m.from_location_name ? (
                <p className="font-medium flex flex-wrap items-center gap-2">
                  <span>From {m.from_location_name || `location ${m.from_location_id}`}</span>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  <span>To {m.to_location_name || `location ${m.to_location_id}`}</span>
                </p>
              ) : (
                <p className="font-medium">
                  First recorded location: {m.to_location_name || `location ${m.to_location_id}`}
                </p>
              )}
              {m.event_id && (
                <Badge className="mt-1 bg-blue-100 text-blue-700 normal-case">via transfer event</Badge>
              )}
              {m.notes && <p className="text-sm text-muted-foreground whitespace-pre-line mt-1">{m.notes}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: reproduction
// ---------------------------------------------------------------------------
function CycleCard({ cycle, terms, species, isLatest, canWrite, onAction }) {
  const [open, setOpen] = useState(isLatest);
  const today = new Date();
  const expected = cycle.expected_calving_date ? parseDate(cycle.expected_calving_date) : null;
  const left = expected ? differenceInCalendarDays(expected, today) : null;
  const interval = cycle.calving_interval_days;
  const outcomeLabel = {
    live_calf: `Live ${terms.offspring.toLowerCase()}`,
    stillbirth: 'Stillbirth',
    abortion: 'Abortion',
    assisted_live: 'Assisted — live',
    assisted_dead: 'Assisted — dead',
  };
  const action = {
    open: { label: 'Record service', type: 'service' },
    served: { label: 'Record PD', type: 'pd' },
    pregnant: { label: `Record ${terms.event.toLowerCase()}`, type: 'calving' },
  }[cycle.status];

  return (
    <Card data-testid={`cycle-card-${cycle.id}`}>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between gap-2">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="gap-2 px-0 font-heading text-lg font-semibold">
                {open ? <CaretDown className="h-4 w-4" /> : <CaretRight className="h-4 w-4" />}
                Cycle {cycle.cycle_number}
              </Button>
            </CollapsibleTrigger>
            <Badge className={CYCLE_STATUS_BADGE[cycle.status]}>{cycle.status}</Badge>
          </div>
          <CollapsibleContent className="pt-3 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Service</p>
                <p>{fmt(cycle.service_date)}</p>
                <p className="text-muted-foreground">{terms.male}: {cycle.bull_tag_number || 'Unknown'}</p>
                {cycle.service_type && <Badge className="mt-1 bg-gray-100 text-gray-700">{cycle.service_type}</Badge>}
              </div>
              <div>
                <p className="text-xs text-muted-foreground">PD check</p>
                {cycle.pd_check_date ? (
                  <>
                    <p>{fmt(cycle.pd_check_date)}</p>
                    {cycle.pd_result && <Badge className={PD_BADGE[cycle.pd_result]}>{cycle.pd_result}</Badge>}
                    {cycle.pd_months_pregnant !== null && cycle.pd_months_pregnant !== undefined && (
                      <span className="ml-2 text-muted-foreground">{cycle.pd_months_pregnant} mo</span>
                    )}
                  </>
                ) : <p>—</p>}
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Expected {terms.event.toLowerCase()}</p>
                {expected ? (
                  <>
                    <p>{fmt(cycle.expected_calving_date)}</p>
                    {!cycle.actual_calving_date && left !== null && (
                      left < 0
                        ? <Badge className="bg-red-100 text-red-700">{-left} d overdue</Badge>
                        : <Badge className="bg-gray-100 text-gray-700">{left} d remaining</Badge>
                    )}
                  </>
                ) : <p>—</p>}
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Actual {terms.event.toLowerCase()}</p>
                {cycle.actual_calving_date ? (
                  <>
                    <p>{fmt(cycle.actual_calving_date)}</p>
                    {cycle.calving_outcome && (
                      <Badge className={OUTCOME_BADGE[cycle.calving_outcome]}>{outcomeLabel[cycle.calving_outcome]}</Badge>
                    )}
                    {cycle.calf_animal_id && (
                      <p className="mt-1">
                        <Link
                          to={`/animals/${cycle.calf_animal_id}`}
                          className="text-primary underline underline-offset-2"
                          data-testid={`calf-link-${cycle.id}`}
                        >
                          View {terms.offspring.toLowerCase()}
                        </Link>
                      </p>
                    )}
                  </>
                ) : <p>—</p>}
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{terms.event} interval</p>
                {interval !== null && interval !== undefined ? (
                  <p className={cn('font-medium', TONE_TEXT[intervalTone(interval, species)])}>{interval} days</p>
                ) : (
                  <p>{cycle.actual_calving_date ? `First ${terms.event.toLowerCase()}` : '—'}</p>
                )}
              </div>
              <div>
                <p className="text-xs text-muted-foreground">BCS</p>
                <p>
                  {cycle.bcs_at_service != null || cycle.bcs_at_calving != null
                    ? [
                      cycle.bcs_at_service != null ? `At service: ${cycle.bcs_at_service}` : null,
                      cycle.bcs_at_calving != null ? `At ${terms.event.toLowerCase()}: ${cycle.bcs_at_calving}` : null,
                    ].filter(Boolean).join(' | ')
                    : '—'}
                </p>
              </div>
            </div>
            {cycle.notes && (
              <div className="text-sm">
                <p className="text-xs text-muted-foreground">Notes</p>
                <p className="whitespace-pre-line">{cycle.notes}</p>
              </div>
            )}
            {canWrite && isLatest && action && (
              <Button size="sm" variant="outline" onClick={() => onAction(action.type, cycle.id)} data-testid={`cycle-action-${cycle.id}`}>
                {action.label}
              </Button>
            )}
          </CollapsibleContent>
        </CardContent>
      </Collapsible>
    </Card>
  );
}

const reproductiveLabels = (species) => ({ pd_test: 'PD Test', calving: getTerms(species).event, abortion: 'Abortion', service: 'Service' });
const EVENT_ICONS = { pd_test: Stethoscope, calving: Baby, abortion: Warning, service: ArrowRight };


function ReproductiveEvents({ animal, canWrite, onChanged }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const labels = reproductiveLabels(animal.species);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    listReproductiveEvents(animal.id).then(({ data }) => { if (active) setEvents(data.slice(0, 10)); })
      .catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [animal.id, refresh]);
  const resultLabel = (event) => {
    if (event.event_type === 'pd_test') return [event.pd_result && ({ pregnant: 'Pregnant', open: 'Open', recheck: 'Recheck' }[event.pd_result]),
      event.pd_result === 'pregnant' && event.months_pregnant != null ? `${event.months_pregnant} months` : null].filter(Boolean).join(', ');
    if (event.event_type === 'calving') return [event.calving_outcome === 'live' ? 'Live' : event.calving_outcome === 'stillbirth' ? 'Stillbirth' : null,
      event.offspring_count != null ? `${event.offspring_count} offspring` : null].filter(Boolean).join(', ');
    if (event.event_type === 'abortion') return event.abortion_stage ? `${event.abortion_stage} stage` : '';
    return event.service_type === 'ai' ? 'AI' : event.service_type === 'natural' ? 'Natural' : '';
  };
  return <section className="mt-6 space-y-4">
    {canWrite && <Button className="gap-2" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Record reproductive event</Button>}
    <h2 className="font-heading text-lg font-semibold">Recent events</h2>
    {loading ? <Skeleton className="h-24" /> : error ? <div role="alert" className="space-y-2">
      <p className="text-sm text-red-600">Could not load reproductive events.</p>
      <Button variant="outline" onClick={() => setRefresh((value) => value + 1)}>Retry</Button>
    </div> : events.length === 0 ? <p className="text-sm text-muted-foreground">No reproductive events recorded yet.</p> : (
      <ol className="relative border-l border-border ml-3 space-y-5">
        {events.map((event) => {
          const Icon = EVENT_ICONS[event.event_type] || ArrowRight;
          const result = resultLabel(event);
          return <li key={event.id} className="relative pl-6">
            <span className="absolute -left-3 top-0 rounded-full bg-muted p-1"><Icon className="h-4 w-4" /></span>
            <p className="text-sm text-muted-foreground">{fmt(event.event_date)}</p>
            <p className="font-medium">{labels[event.event_type]}{result ? ` — ${result}` : ''}</p>
          </li>;
        })}
      </ol>
    )}
    {open && <ReproductiveEventDialog animal={animal} onClose={() => setOpen(false)} onSaved={() => {
      setRefresh((value) => value + 1); onChanged();
    }} />}
  </section>;
}

function ReproductionTab({ animal, history, loading, canWrite, onChanged }) {
  const [dialog, setDialog] = useState({ type: null });
  const terms = getTerms(animal.species);
  const close = () => setDialog({ type: null });

  if (animal.sex !== 'female') {
    return <p className="text-sm text-muted-foreground">Reproductive cycles are recorded for females only.</p>;
  }
  if (loading || !history) return <Skeleton className="h-40" />;

  const latest = history.cycles.length ? history.cycles[history.cycles.length - 1] : null;
  const avgTone = history.avg_interval_days == null ? 'grey' : intervalTone(history.avg_interval_days, animal.species);
  const stats = [
    { label: `Total ${terms.event.toLowerCase()}s`, value: history.total_calvings },
    {
      label: 'Avg interval',
      value: history.avg_interval_days == null ? '—' : `${Math.round(history.avg_interval_days)} days`,
      tone: avgTone,
    },
    { label: `Last ${terms.event.toLowerCase()}`, value: fmt(history.last_calving_date) },
    { label: 'Current status', badge: history.current_status },
  ];

  return (
    <div className="space-y-4" data-testid="reproduction-tab">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              {s.badge !== undefined ? (
                s.badge ? <Badge className={cn('mt-1', CYCLE_STATUS_BADGE[s.badge])}>{s.badge}</Badge> : <p className="text-lg font-bold">—</p>
              ) : (
                <p className={cn('text-lg font-heading font-bold', s.tone && TONE_TEXT[s.tone])}>
                  {s.value}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      {history.offspring?.length > 0 && (
        <Card data-testid="offspring-list">
          <CardContent className="p-4 space-y-2">
            <h3 className="font-heading text-lg font-semibold">{terms.offspring} records</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tag</TableHead>
                  <TableHead>Sex</TableHead>
                  <TableHead>Born</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Cycle</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.offspring.map((o) => (
                  <TableRow key={o.animal_id}>
                    <TableCell>
                      <Link to={`/animals/${o.animal_id}`} className="text-primary underline underline-offset-2">
                        {o.tag_number}
                      </Link>
                      {o.name && <span className="ml-2 text-muted-foreground">{o.name}</span>}
                    </TableCell>
                    <TableCell className="capitalize">{o.sex || '—'}</TableCell>
                    <TableCell>{fmt(o.birth_date || o.calving_date)}</TableCell>
                    <TableCell className="capitalize">{o.status || '—'}</TableCell>
                    <TableCell>#{o.cycle_number}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      {history.cycles.length === 0 ? (
        <p className="text-sm text-muted-foreground">No reproductive history recorded</p>
      ) : (
        history.cycles.map((c) => (
          <CycleCard
            key={c.id} cycle={c} terms={terms} species={animal.species}
            isLatest={latest && c.id === latest.id} canWrite={canWrite}
            onAction={(type, cycleId) => setDialog({ type, cycleId })}
          />
        ))
      )}
      {canWrite && (
        <Button className="gap-2" onClick={() => setDialog({ type: 'service' })} data-testid="new-cycle-btn">
          <Plus className="h-4 w-4" />Start new cycle
        </Button>
      )}
      <RecordServiceDialog open={dialog.type === 'service'} onClose={close} onSuccess={onChanged} animalId={animal.id} />
      <RecordPDDialog open={dialog.type === 'pd'} onClose={close} onSuccess={onChanged} cycleId={dialog.cycleId} />
      <RecordCalvingDialog open={dialog.type === 'calving'} onClose={close} onSuccess={onChanged} cycleId={dialog.cycleId} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: BCS history
// ---------------------------------------------------------------------------
const scoreClass = (v) => (v <= 2 ? 'text-red-600' : v < 3 ? 'text-amber-600' : 'text-green-700');

function BCSTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border bg-card p-2 text-xs shadow">
      <p className="font-medium">{fmt(p.date)}</p>
      <p>Score: {p.bcs}</p>
      {p.scored_by && <p className="text-muted-foreground">By {p.scored_by}</p>}
    </div>
  );
}

function BCSTab({ animalId, records, loading, canWrite, onChanged }) {
  const [open, setOpen] = useState(false);
  const chartData = [...records]
    .sort((a, b) => a.score_date.localeCompare(b.score_date) || a.id - b.id)
    .map((r) => ({ date: r.score_date, bcs: Number(r.bcs), scored_by: r.scored_by }));

  return (
    <div className="space-y-4" data-testid="bcs-tab">
      {canWrite && (
        <div className="flex justify-end">
          <Button size="sm" className="gap-1" onClick={() => setOpen(true)} data-testid="record-bcs-btn">
            <Plus className="h-4 w-4" />Record BCS
          </Button>
        </div>
      )}
      {loading ? <Skeleton className="h-48" /> : records.length === 0 ? (
        <p className="text-sm text-muted-foreground">No BCS scores recorded</p>
      ) : (
        <>
          {records.length >= 2 && (
            <div className="h-64 w-full">
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={(d) => format(parseDate(d), 'MMM yy')} />
                  <YAxis domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} />
                  <Tooltip content={<BCSTooltip />} />
                  <ReferenceLine y={2} stroke="#DC2626" strokeDasharray="5 5" label={{ value: 'Thin', position: 'insideTopRight', fill: '#DC2626', fontSize: 11 }} />
                  <ReferenceLine y={3} stroke="#16A34A" strokeDasharray="5 5" label={{ value: 'Target', position: 'insideTopRight', fill: '#16A34A', fontSize: 11 }} />
                  <Line type="monotone" dataKey="bcs" stroke="#2D5A27" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow><TableHead>Date</TableHead><TableHead>Score</TableHead><TableHead>Scored by</TableHead><TableHead>Notes</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {records.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{fmt(r.score_date)}</TableCell>
                    <TableCell className={cn('font-bold', scoreClass(Number(r.bcs)))}>{Number(r.bcs).toFixed(1)}</TableCell>
                    <TableCell>{r.scored_by || '—'}</TableCell>
                    <TableCell>{r.notes || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
      <RecordBCSDialog open={open} onClose={() => setOpen(false)} onSuccess={onChanged} animalId={animalId} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: notes
// ---------------------------------------------------------------------------
function NotesTab({ animalId, notes, loading, canWrite, isAdmin, onChanged, onAddNote }) {
  const [editing, setEditing] = useState(null); // { id, content, note_type }
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [saving, setSaving] = useState(false);

  const saveEdit = async () => {
    setSaving(true);
    try {
      await updateAnimalNote(animalId, editing.id, { content: editing.content.trim(), note_type: editing.note_type });
      toast.success('Note updated');
      setEditing(null);
      onChanged();
    } catch (err) {
      toast.error(errText(err, 'Failed to update note'));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    const target = deleteTarget;
    setDeleteTarget(null);
    try {
      await deleteAnimalNote(animalId, target.id);
      toast.success('Note deleted');
      onChanged();
    } catch (err) {
      toast.error(errText(err, 'Failed to delete note'));
    }
  };

  return (
    <div className="space-y-4" data-testid="notes-tab">
      {canWrite && (
        <div className="flex justify-end">
          <Button size="sm" className="gap-1" onClick={onAddNote} data-testid="notes-add-note">
            <Plus className="h-4 w-4" />Add note
          </Button>
        </div>
      )}
      {loading ? <Skeleton className="h-32" /> : notes.length === 0 ? (
        <p className="text-sm text-muted-foreground">No notes recorded</p>
      ) : (
        <ul className="space-y-3">
          {notes.map((n) => (
            <li key={n.id} className="rounded-lg border p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">{fmt(n.note_date)}</span>
                  <Badge className={NOTE_BADGE[n.note_type]}>{n.note_type}</Badge>
                </div>
                {canWrite && editing?.id !== n.id && (
                  <div className="flex gap-1">
                    <Button
                      size="icon" variant="ghost" aria-label="Edit note"
                      onClick={() => setEditing({ id: n.id, content: n.content, note_type: n.note_type })}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    {isAdmin && (
                      <Button size="icon" variant="ghost" aria-label="Delete note" onClick={() => setDeleteTarget(n)}>
                        <Trash className="h-4 w-4 text-red-600" />
                      </Button>
                    )}
                  </div>
                )}
              </div>
              {editing?.id === n.id ? (
                <div className="space-y-2">
                  <Select value={editing.note_type} onValueChange={(v) => setEditing({ ...editing, note_type: v })}>
                    <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {NOTE_TYPES.map((t) => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Textarea value={editing.content} onChange={(e) => setEditing({ ...editing, content: e.target.value })} rows={3} />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={saveEdit} disabled={saving || !editing.content.trim()}>Save</Button>
                    <Button size="sm" variant="outline" onClick={() => setEditing(null)} disabled={saving}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <p className="text-sm whitespace-pre-line">{n.content}</p>
              )}
            </li>
          ))}
        </ul>
      )}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => { if (!o) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this note?</AlertDialogTitle>
            <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
function AnimalDetail() {
  const { id } = useParams();
  const { isAdmin, isDataEntry } = useAuth();
  const [animal, setAnimal] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [photos, setPhotos] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [history, setHistory] = useState(null);
  const [reproductiveSummary, setReproductiveSummary] = useState(null);
  const summaryRequest = useRef(0);
  const [bcs, setBcs] = useState([]);
  const [notes, setNotes] = useState([]);
  const [locHistory, setLocHistory] = useState([]);
  const [loading, setLoading] = useState({
    animal: true, photos: true, timeline: true, history: true, bcs: true, notes: true, locHistory: true,
  });
  const [noteDialog, setNoteDialog] = useState(false);
  const [replaceDialog, setReplaceDialog] = useState(false);

  const markLoaded = useCallback((key) => setLoading((l) => ({ ...l, [key]: false })), []);

  const loadReproductiveSummary = useCallback(async () => {
    const request = ++summaryRequest.current;
    try {
      const { data } = await getReproductiveSummary(id);
      if (request === summaryRequest.current) setReproductiveSummary({ animalId: id, data });
    } catch {
      if (request === summaryRequest.current) {
        setReproductiveSummary(null);
        toast.error('Failed to load reproductive summary');
      }
    }
  }, [id]);

  useEffect(() => {
    loadReproductiveSummary();
    return () => { summaryRequest.current += 1; };
  }, [loadReproductiveSummary]);

  const loadPhotos = useCallback(
    () => getAnimalPhotos(id).then((r) => setPhotos(r.data)).catch(failToast('photos')).finally(() => markLoaded('photos')),
    [id, markLoaded]
  );
  const loadTimeline = useCallback(
    () => getAnimalTimeline(id).then((r) => setTimeline(r.data)).catch(failToast('timeline')).finally(() => markLoaded('timeline')),
    [id, markLoaded]
  );
  const loadHistory = useCallback(
    () => getAnimalReproductiveHistory(id).then((r) => setHistory(r.data)).catch(failToast('reproductive history')).finally(() => markLoaded('history')),
    [id, markLoaded]
  );
  const loadBcs = useCallback(
    () => getAnimalBCSHistory(id).then((r) => setBcs(r.data)).catch(failToast('BCS records')).finally(() => markLoaded('bcs')),
    [id, markLoaded]
  );
  const loadNotes = useCallback(
    () => getAnimalNotes(id).then((r) => setNotes(r.data)).catch(failToast('notes')).finally(() => markLoaded('notes')),
    [id, markLoaded]
  );

  const loadLocHistory = useCallback(
    () => getAnimalLocationHistory(id).then((r) => setLocHistory(r.data)).catch(failToast('movement history')).finally(() => markLoaded('locHistory')),
    [id, markLoaded]
  );

  const reloadAnimal = useCallback(
    () => getAnimalDetail(id).then((r) => setAnimal(r.data)).catch(failToast('animal')),
    [id]
  );

  useEffect(() => {
    setNotFound(false);
    setLoading({ animal: true, photos: true, timeline: true, history: true, bcs: true, notes: true, locHistory: true });
    getAnimalDetail(id)
      .then((r) => setAnimal(r.data))
      .catch((err) => {
        if (err?.response?.status === 404) setNotFound(true);
        else toast.error('Failed to load animal');
      })
      .finally(() => markLoaded('animal'));
    loadPhotos(); loadTimeline(); loadHistory(); loadBcs(); loadNotes(); loadLocHistory();
  }, [id, markLoaded, loadPhotos, loadTimeline, loadHistory, loadBcs, loadNotes, loadLocHistory]);

  const afterNoteChange = () => { loadNotes(); loadTimeline(); };
  const afterCycleChange = () => { loadHistory(); loadTimeline(); loadReproductiveSummary(); };
  const afterBcsChange = () => { loadBcs(); loadTimeline(); };

  if (loading.animal) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Skeleton className="h-96" /><Skeleton className="h-96 lg:col-span-2" />
      </div>
    );
  }
  if (notFound || !animal) {
    return (
      <div className="space-y-4">
        <p className="text-muted-foreground">Animal not found.</p>
        <Button asChild variant="outline"><Link to="/animals">Back to animals</Link></Button>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="animal-detail-page">
      <Button asChild variant="ghost" size="sm" className="gap-2 px-0">
        <Link to="/animals"><ArrowLeft className="h-4 w-4" />Animals</Link>
      </Button>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4">
          <PhotoGallery
            animalId={animal.id} photos={photos} loading={loading.photos}
            canWrite={isDataEntry} isAdmin={isAdmin} onChanged={loadPhotos}
          />
          <IdentityCard animal={animal} canWrite={isDataEntry} isAdmin={isAdmin} onReplaceTag={() => setReplaceDialog(true)}
            reproductiveSummary={reproductiveSummary?.animalId === id ? reproductiveSummary.data : null} />
        </div>
        <div className="lg:col-span-2">
          <Tabs defaultValue="timeline" onValueChange={(tab) => { if (tab === 'reproduction') loadReproductiveSummary(); }}>
            <TabsList>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="daily-log-timeline">Daily Log Timeline</TabsTrigger>
              <TabsTrigger value="reproduction">Breeding</TabsTrigger>
              <TabsTrigger value="bcs">BCS</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="movements">Movement history</TabsTrigger>
            </TabsList>
            <TabsContent value="daily-log-timeline" className="pt-4"><DailyLogTimeline key={id} animalId={id} /></TabsContent>
            <TabsContent value="timeline" className="pt-4">
              <TimelineTab items={timeline} loading={loading.timeline} canWrite={isDataEntry} onAddNote={() => setNoteDialog(true)} />
            </TabsContent>
            <TabsContent value="reproduction" className="pt-4">
              <ReproductionTab
                animal={animal} history={history} loading={loading.history}
                canWrite={isDataEntry} onChanged={afterCycleChange}
              />
              <ReproductiveEvents key={id} animal={animal} canWrite={isDataEntry} onChanged={loadReproductiveSummary} />
            </TabsContent>
            <TabsContent value="bcs" className="pt-4">
              <BCSTab animalId={animal.id} records={bcs} loading={loading.bcs} canWrite={isDataEntry} onChanged={afterBcsChange} />
            </TabsContent>
            <TabsContent value="notes" className="pt-4">
              <NotesTab
                animalId={animal.id} notes={notes} loading={loading.notes} canWrite={isDataEntry}
                isAdmin={isAdmin} onChanged={afterNoteChange} onAddNote={() => setNoteDialog(true)}
              />
            </TabsContent>
            <TabsContent value="movements" className="pt-4">
              <MovementHistoryTab items={locHistory} loading={loading.locHistory} />
            </TabsContent>
          </Tabs>
        </div>
      </div>
      <ReplaceTagDialog open={replaceDialog} onClose={() => setReplaceDialog(false)} animal={animal} onReplaced={reloadAnimal} />
      <AddNoteDialog open={noteDialog} onClose={() => setNoteDialog(false)} onSaved={afterNoteChange} animalId={animal.id} />
    </div>
  );
}

export default AnimalDetail;
