import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  getAnimals, createAnimal, updateAnimal, transferAnimal,
  bulkImportAnimals, downloadAnimalsTemplate, getLocations, getCategories,
  getRegisterReconciliation,
} from '../lib/api';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Skeleton } from '../components/ui/skeleton';
import { Switch } from '../components/ui/switch';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../components/ui/collapsible';
import {
  Tag, Plus, UploadSimple, DownloadSimple, ArrowsLeftRight, CaretDown, CaretRight, ArrowClockwise,
} from '@phosphor-icons/react';
import { toast } from 'sonner';
import { formatDate, SPECIES_CONFIG } from '../lib/utils';
import {
  coverageTone, sortReconciliationRows, summariseReconciliation, TONE_BG, TONE_TEXT,
} from '../lib/registerCoverage';

const STATUS_BADGE = {
  active: 'bg-green-100 text-green-700',
  sold: 'bg-gray-100 text-gray-600',
  dead: 'bg-red-100 text-red-700',
  transferred: 'bg-blue-100 text-blue-700',
  missing: 'bg-amber-100 text-amber-700',
};

const DEFAULT_FORM = {
  tag_number: '',
  name: '',
  species: '',
  category_id: '',
  location_id: '',
  sex: '',
  birth_date: '',
  mother_tag: '',
  father_tag: '',
  acquisition_type: '',
  acquisition_date: '',
  notes: '',
};

// CSV cell: always quoted; a leading = + - @ gets a ' prefix so spreadsheets do not run it as a formula.
function csvCell(value) {
  let s = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return '"' + s.replace(/"/g, '""') + '"';
}

function slugify(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'farm';
}

function SpeciesBadge({ species }) {
  const cfg = SPECIES_CONFIG[species] || {};
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${cfg.bgClass || ''} ${cfg.textClass || ''}`}>
      {species}
    </span>
  );
}

function StatusBadge({ status }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${STATUS_BADGE[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  );
}

function GapCell({ row }) {
  if (row.unregistered > 0) {
    return <span className="text-red-600 font-medium">{row.unregistered} unregistered</span>;
  }
  if (row.unregistered < 0) {
    return <span className="text-amber-600 font-medium">{Math.abs(row.unregistered)} extra in register</span>;
  }
  return <span className="text-green-600 font-medium">✓ Matched</span>;
}

// Collapsible "Register completeness" panel (data: GET /api/animals/register-reconciliation).
function RegisterCompletenessPanel({ open, onOpenChange, rows, loading, error, onRefresh }) {
  const summary = rows ? summariseReconciliation(rows) : null;
  const sorted = rows ? sortReconciliationRows(rows) : [];

  let chip = null;
  if (loading && !rows) {
    chip = <span className="text-xs text-muted-foreground">Checking…</span>;
  } else if (error && !rows) {
    chip = <span className="text-xs text-muted-foreground">Unavailable</span>;
  } else if (summary && summary.pct !== null) {
    chip = (
      <>
        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${TONE_BG[coverageTone(summary.pct)]}`}>
          {summary.pct}% registered across all farms
        </span>
        {summary.attentionFarms > 0 && (
          <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${TONE_BG.red}`}>
            {summary.attentionFarms} farm{summary.attentionFarms !== 1 ? 's' : ''} need{summary.attentionFarms === 1 ? 's' : ''} attention
          </span>
        )}
      </>
    );
  } else if (summary) {
    chip = <span className="text-xs text-muted-foreground">No stock to compare</span>;
  }

  return (
    <Card className="border-border/60" data-testid="register-completeness-panel">
      <Collapsible open={open} onOpenChange={onOpenChange}>
        <div className="flex items-center justify-between gap-2 p-3">
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="gap-2 px-2 flex-wrap h-auto" data-testid="register-completeness-toggle">
              {open ? <CaretDown className="h-4 w-4" /> : <CaretRight className="h-4 w-4" />}
              <span className="font-heading font-semibold">Register completeness</span>
              {chip}
            </Button>
          </CollapsibleTrigger>
          {open && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onRefresh}
              disabled={loading}
              aria-label="Refresh register completeness"
              data-testid="register-completeness-refresh"
            >
              <ArrowClockwise className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          )}
        </div>
        <CollapsibleContent>
          <div className="px-3 pb-3 space-y-2">
            {error && !rows ? (
              <p className="text-sm text-red-600">Could not load register completeness. Use refresh to try again.</p>
            ) : !rows ? (
              <Skeleton className="h-24" />
            ) : sorted.length === 0 ? (
              <p className="text-sm text-muted-foreground">No stock or registered animals to compare yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Farm</TableHead>
                    <TableHead>Species</TableHead>
                    <TableHead className="text-right">Stock (events)</TableHead>
                    <TableHead className="text-right">Registered</TableHead>
                    <TableHead className="text-right">Coverage %</TableHead>
                    <TableHead>Gap</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sorted.map(function (r) {
                    const tone = coverageTone(r.registered_pct);
                    return (
                      <TableRow key={`${r.location_id}-${r.species}`}>
                        <TableCell className="font-medium">{r.location_name}</TableCell>
                        <TableCell><SpeciesBadge species={r.species} /></TableCell>
                        <TableCell className="text-right">{r.stock_count}</TableCell>
                        <TableCell className="text-right">{r.registered_active}</TableCell>
                        <TableCell className={`text-right font-semibold ${TONE_TEXT[tone]}`}>
                          {r.registered_pct === null || r.registered_pct === undefined ? '—' : `${Math.round(r.registered_pct)}%`}
                        </TableCell>
                        <TableCell><GapCell row={r} /></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
            <p className="text-xs text-muted-foreground">
              Stock counts from event log · Register counts active animals only
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

function Animals() {
  const [animals, setAnimals] = useState([]);
  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);

  const [filterSpecies, setFilterSpecies] = useState('all');
  const [filterReproductive, setFilterReproductive] = useState('all');
  const [filterSex, setFilterSex] = useState('all');
  const [filterLocation, setFilterLocation] = useState('all');
  const [filterStatus, setFilterStatus] = useState('active');
  const [filterTempOnly, setFilterTempOnly] = useState(false);
  const tempFilterMounted = useRef(false);
  const [search, setSearch] = useState('');

  const [selectedAnimal, setSelectedAnimal] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editingAnimal, setEditingAnimal] = useState(null);
  const [formData, setFormData] = useState(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);

  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const fileInputRef = useRef(null);

  const [transferDialogOpen, setTransferDialogOpen] = useState(false);
  const [transferForm, setTransferForm] = useState({ to_location_id: '', transfer_date: '', notes: '' });
  const [transferring, setTransferring] = useState(false);

  const { isAdmin, isDataEntry } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // Set when Edit/Transfer was opened from an animal profile (?edit=ID / ?transfer=ID):
  // after the dialog closes (saved or cancelled) we go back to that profile.
  const [returnTo, setReturnTo] = useState(null);

  // Register completeness panel (opened by the Dashboard link: /animals?panel=register)
  const [regOpen, setRegOpen] = useState(searchParams.get('panel') === 'register');
  const [regRows, setRegRows] = useState(null);
  const [regLoading, setRegLoading] = useState(true);
  const [regError, setRegError] = useState(false);

  async function loadReconciliation(showToast) {
    setRegLoading(true);
    setRegError(false);
    try {
      const res = await getRegisterReconciliation();
      setRegRows(res.data);
    } catch {
      setRegError(true);
      if (showToast) toast.error('Failed to load register completeness');
    } finally {
      setRegLoading(false);
    }
  }

  // "Temp tags only" re-fetches with is_temp_tag=true (skipped on first render: loadData does the initial load)
  async function loadAnimalsOnly() {
    try {
      const res = await getAnimals(filterTempOnly ? { is_temp_tag: true } : undefined);
      setAnimals(res.data);
    } catch {
      toast.error('Failed to load animals');
    }
  }

  useEffect(function () {
    if (!tempFilterMounted.current) {
      tempFilterMounted.current = true;
      return;
    }
    loadAnimalsOnly();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterTempOnly]);

  useEffect(function () {
    loadData();
    loadReconciliation(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(function () {
    if (loading) return;
    const editId = searchParams.get('edit');
    const transferId = searchParams.get('transfer');
    const id = parseInt(editId || transferId);
    if (!id) return;
    setSearchParams({}, { replace: true });
    const animal = animals.find(function (a) { return a.id === id; });
    if (!animal) {
      toast.error('Animal not found');
      return;
    }
    setReturnTo(id);
    if (editId) {
      handleOpenAddDialog(animal);
    } else {
      setSelectedAnimal(animal);
      handleOpenTransfer();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, animals, searchParams]);

  useEffect(function () {
    if (returnTo && !addDialogOpen && !transferDialogOpen) {
      navigate('/animals/' + returnTo);
      setReturnTo(null);
    }
  }, [returnTo, addDialogOpen, transferDialogOpen, navigate]);

  async function loadData() {
    // Load locations + categories independently — these are needed by the form
    // regardless of whether the animals endpoint is healthy yet.
    try {
      const [locationsRes, categoriesRes] = await Promise.all([getLocations(), getCategories()]);
      setLocations(locationsRes.data);
      setCategories(categoriesRes.data);
    } catch {
      toast.error('Failed to load reference data');
    }

    try {
      const animalsRes = await getAnimals(filterTempOnly ? { is_temp_tag: true } : undefined);
      setAnimals(animalsRes.data);
    } catch {
      toast.error('Failed to load animals');
    } finally {
      setLoading(false);
    }
  }

  const filteredAnimals = animals.filter(function (a) {
    if (filterReproductive !== 'all' && (a.reproductive_status || 'unknown') !== filterReproductive) return false;
    if (filterSpecies !== 'all' && a.species !== filterSpecies) return false;
    if (filterSex !== 'all' && a.sex !== filterSex) return false;
    if (filterLocation !== 'all' && a.location_id !== parseInt(filterLocation)) return false;
    if (filterStatus !== 'all' && a.status !== filterStatus) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      if (!a.tag_number.toLowerCase().includes(q) && !(a.name || '').toLowerCase().includes(q)) return false;
    }
    return true;
  });

  // "X animals" for the default view, "X of Y animals" once any filter narrows it.
  // Baseline Y: the default (active) view, or every loaded animal when the status filter was changed.
  const baselineCount = filterStatus === 'active'
    ? animals.filter(function (a) { return a.status === 'active'; }).length
    : animals.length;
  const isFiltered = filterSpecies !== 'all' || filterReproductive !== 'all' || filterLocation !== 'all'
    || filterSex !== 'all' || filterStatus !== 'active' || filterTempOnly || search.trim() !== '';
  const animalWord = (isFiltered ? baselineCount : filteredAnimals.length) === 1 ? 'animal' : 'animals';
  const countLabel = isFiltered
    ? `${filteredAnimals.length} of ${baselineCount} ${animalWord}`
    : `${filteredAnimals.length} ${animalWord}`;

  function handleExportCsv() {
    const header = ['tag_number', 'species', 'category', 'sex', 'farm', 'status', 'date_of_birth',
      'acquisition_date', 'reproductive_status', 'last_calving_date'];
    const rows = filteredAnimals.map(function (a) {
      return [a.tag_number, a.species, a.category_name_sw || a.category_name_en || '', a.sex,
        a.location_name || '', a.status, a.birth_date || '', a.acquisition_date || '',
        a.reproductive_status || '', a.last_calving_date || ''];
    });
    const csv = [header].concat(rows).map(function (row) {
      return row.map(csvCell).join(',');
    }).join('\r\n');
    const farm = filterLocation === 'all'
      ? 'all-farms'
      : slugify((locations.find(function (l) { return String(l.id) === filterLocation; }) || {}).name || 'farm');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `animals-${farm}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  const formCategories = categories.filter(function (c) { return c.species === formData.species; });

  function handleRowClick(animal) {
    navigate('/animals/' + animal.id);
  }

  function handleOpenAddDialog(animal) {
    if (animal) {
      setEditingAnimal(animal);
      setFormData({
        tag_number: animal.tag_number,
        name: animal.name || '',
        species: animal.species,
        category_id: String(animal.category_id),
        location_id: String(animal.location_id),
        sex: animal.sex,
        birth_date: animal.birth_date || '',
        mother_tag: animal.mother_tag || '',
        father_tag: animal.father_tag || '',
        acquisition_type: animal.acquisition_type,
        acquisition_date: animal.acquisition_date || '',
        notes: animal.notes || '',
      });
    } else {
      setEditingAnimal(null);
      setFormData(DEFAULT_FORM);
    }
    setAddDialogOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    const payload = {
      tag_number: formData.tag_number,
      name: formData.name || null,
      species: formData.species,
      category_id: parseInt(formData.category_id),
      location_id: parseInt(formData.location_id),
      sex: formData.sex,
      birth_date: formData.birth_date || null,
      mother_tag: formData.mother_tag || null,
      father_tag: formData.father_tag || null,
      acquisition_type: formData.acquisition_type,
      acquisition_date: formData.acquisition_date,
      notes: formData.notes || null,
    };
    try {
      if (editingAnimal) {
        await updateAnimal(editingAnimal.id, payload);
        toast.success('Animal updated');
      } else {
        await createAnimal(payload);
        toast.success('Animal added');
      }
      setAddDialogOpen(false);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save animal');
    } finally {
      setSaving(false);
    }
  }

  function handleOpenTransfer() {
    setTransferForm({
      to_location_id: '',
      transfer_date: new Date().toISOString().split('T')[0],
      notes: '',
    });
    setTransferDialogOpen(true);
  }

  async function handleTransfer(e) {
    e.preventDefault();
    if (!selectedAnimal) return;
    setTransferring(true);
    try {
      const res = await transferAnimal(selectedAnimal.id, {
        to_location_id: parseInt(transferForm.to_location_id),
        transfer_date: transferForm.transfer_date,
        notes: transferForm.notes || null,
      });
      toast.success('Animal transferred successfully');
      setTransferDialogOpen(false);
      setSheetOpen(false);
      setSelectedAnimal(res.data);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Transfer failed');
    } finally {
      setTransferring(false);
    }
  }

  async function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      toast.error('Please select a CSV file');
      return;
    }
    setImporting(true);
    setImportResult(null);
    try {
      const response = await bulkImportAnimals(file);
      setImportResult(response.data);
      toast.success(response.data.message);
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Import failed');
      setImportResult({ errors: [error.response?.data?.detail || 'Import failed'], created: 0, skipped: 0 });
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  function handleDownloadTemplate() {
    window.open(downloadAnimalsTemplate(), '_blank');
  }

  function setField(key, value) {
    setFormData(function (prev) { return { ...prev, [key]: value }; });
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="flex gap-3">
          <Skeleton className="h-10 w-36" />
          <Skeleton className="h-10 w-44" />
          <Skeleton className="h-10 w-36" />
          <Skeleton className="h-10 w-52" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="animals-page">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold">Animals</h1>
          <p className="text-muted-foreground mt-1">Track individual animals by tag number</p>
          <p className="text-sm font-medium mt-1" data-testid="animals-count">{countLabel}</p>
        </div>
        <div className="flex gap-2">
          {(isAdmin || isDataEntry) && (
            <Button
              variant="outline"
              className="gap-2"
              onClick={handleExportCsv}
              disabled={filteredAnimals.length === 0}
              data-testid="export-csv-btn"
            >
              <DownloadSimple className="h-4 w-4" />
              Export CSV
            </Button>
          )}
          {isAdmin && (
            <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
              <Button
                variant="outline"
                className="gap-2"
                onClick={function () { setImportResult(null); setImportDialogOpen(true); }}
                data-testid="bulk-import-btn"
              >
                <UploadSimple className="h-4 w-4" />
                Bulk Import
              </Button>
            </Dialog>
          )}
          {(isAdmin || isDataEntry) && (
            <Button className="gap-2" onClick={function () { handleOpenAddDialog(null); }} data-testid="add-animal-btn">
              <Plus className="h-4 w-4" />
              Add Animal
            </Button>
          )}
        </div>
      </div>

      {/* Register completeness (collapsed by default) */}
      <RegisterCompletenessPanel
        open={regOpen}
        onOpenChange={setRegOpen}
        rows={regRows}
        loading={regLoading}
        error={regError}
        onRefresh={function () { loadReconciliation(true); }}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Select value={filterSpecies} onValueChange={setFilterSpecies}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="All Species" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Species</SelectItem>
            <SelectItem value="cattle">Cattle</SelectItem>
            <SelectItem value="sheep">Sheep</SelectItem>
            <SelectItem value="goat">Goat</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterSex} onValueChange={setFilterSex}>
          <SelectTrigger className="w-36" aria-label="Sex" data-testid="sex-filter">
            <span className="mr-1 text-muted-foreground">Sex:</span><SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="male">Male ♂</SelectItem>
            <SelectItem value="female">Female ♀</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterReproductive} onValueChange={(value) => {
          if (value === 'repeat') {
            const params = new URLSearchParams();
            if (filterSpecies !== 'all') params.set('species', filterSpecies);
            if (filterLocation !== 'all') params.set('location_id', filterLocation);
            navigate(`/animals/repeat-breeders${params.size ? `?${params}` : ''}`);
          } else setFilterReproductive(value);
        }}>
          <SelectTrigger className="w-56" aria-label="Reproductive status">
            <span className="mr-1 text-muted-foreground">Reproduction:</span><SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="pregnant">Pregnant</SelectItem>
            <SelectItem value="unknown">Unknown</SelectItem>
            <SelectItem value="repeat">Repeat breeders</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterLocation} onValueChange={setFilterLocation}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All Locations" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Locations</SelectItem>
            {locations.map(function (loc) {
              return <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>;
            })}
          </SelectContent>
        </Select>

        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="sold">Sold</SelectItem>
            <SelectItem value="dead">Dead</SelectItem>
            <SelectItem value="transferred">Transferred</SelectItem>
            <SelectItem value="missing">Missing</SelectItem>
          </SelectContent>
        </Select>

        <Input
          placeholder="Search tag or name..."
          value={search}
          onChange={function (e) { setSearch(e.target.value); }}
          className="w-52"
        />

        <div className="flex items-center gap-2">
          <Switch
            id="temp-tags-only"
            checked={filterTempOnly}
            onCheckedChange={setFilterTempOnly}
            data-testid="temp-tags-switch"
          />
          <Label htmlFor="temp-tags-only" className="cursor-pointer text-sm">Temp tags only</Label>
        </div>
      </div>

      {/* Table */}
      {filteredAnimals.length > 0 ? (
        <>
          <Card className="border-border/60">
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tag</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Species</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead>Sex</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Acquired</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredAnimals.map(function (animal) {
                    return (
                      <TableRow
                        key={animal.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={function () { handleRowClick(animal); }}
                        data-testid={`animal-row-${animal.id}`}
                      >
                        <TableCell className="font-mono font-medium">{animal.tag_number}</TableCell>
                        <TableCell>{animal.name || <span className="text-muted-foreground">—</span>}</TableCell>
                        <TableCell><SpeciesBadge species={animal.species} /></TableCell>
                        <TableCell>{animal.category_name_sw || '—'}</TableCell>
                        <TableCell>{animal.location_name || '—'}</TableCell>
                        <TableCell className="capitalize">{animal.sex}</TableCell>
                        <TableCell><StatusBadge status={animal.status} /></TableCell>
                        <TableCell>{animal.acquisition_date ? formatDate(animal.acquisition_date) : '—'}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      ) : (
        <Card className="border-border/60">
          <CardContent className="py-12 text-center">
            <Tag className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
            <p className="text-muted-foreground mb-4">
              {animals.length === 0 && !filterTempOnly ? 'No animals registered yet' : 'No animals match your filters'}
            </p>
            {animals.length === 0 && !filterTempOnly && (isAdmin || isDataEntry) && (
              <Button onClick={function () { handleOpenAddDialog(null); }} className="gap-2">
                <Plus className="h-4 w-4" />
                Add Your First Animal
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Detail Sheet ── */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="w-[420px] sm:w-[520px] overflow-y-auto">
          {selectedAnimal && (
            <>
              <SheetHeader className="mb-6">
                <SheetTitle className="font-heading flex items-center gap-2 flex-wrap">
                  <SpeciesBadge species={selectedAnimal.species} />
                  <span className="font-mono">{selectedAnimal.tag_number}</span>
                  {selectedAnimal.name && (
                    <span className="text-muted-foreground font-normal text-base">({selectedAnimal.name})</span>
                  )}
                </SheetTitle>
              </SheetHeader>

              <div className="space-y-5 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Status</span>
                  <StatusBadge status={selectedAnimal.status} />
                </div>

                <div className="border-t border-border" />

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">Category</p>
                    <p>{selectedAnimal.category_name_sw || '—'}</p>
                    {selectedAnimal.category_name_en && (
                      <p className="text-muted-foreground text-xs">{selectedAnimal.category_name_en}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">Location</p>
                    <p>{selectedAnimal.location_name || '—'}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">Sex</p>
                    <p className="capitalize">{selectedAnimal.sex}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs mb-1">Birth Date</p>
                    <p>{selectedAnimal.birth_date ? formatDate(selectedAnimal.birth_date) : 'Unknown'}</p>
                  </div>
                </div>

                <div className="border-t border-border" />

                <div>
                  <p className="font-medium text-xs uppercase tracking-wide text-muted-foreground mb-3">Parentage</p>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-muted-foreground text-xs mb-1">Mother Tag</p>
                      <p className="font-mono">{selectedAnimal.mother_tag || '—'}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs mb-1">Father Tag</p>
                      <p className="font-mono">{selectedAnimal.father_tag || '—'}</p>
                    </div>
                  </div>
                </div>

                <div className="border-t border-border" />

                <div>
                  <p className="font-medium text-xs uppercase tracking-wide text-muted-foreground mb-3">Acquisition</p>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-muted-foreground text-xs mb-1">Type</p>
                      <p className="capitalize">{selectedAnimal.acquisition_type?.replace('_', ' ')}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs mb-1">Date</p>
                      <p>{selectedAnimal.acquisition_date ? formatDate(selectedAnimal.acquisition_date) : '—'}</p>
                    </div>
                  </div>
                </div>

                {selectedAnimal.notes && (
                  <>
                    <div className="border-t border-border" />
                    <div>
                      <p className="text-muted-foreground text-xs mb-1">Notes</p>
                      <p>{selectedAnimal.notes}</p>
                    </div>
                  </>
                )}

                <div className="border-t border-border" />

                <p className="text-xs text-muted-foreground">
                  Added {formatDate(selectedAnimal.created_at)}
                  {selectedAnimal.created_by_name && ` by ${selectedAnimal.created_by_name}`}
                </p>

                {(isAdmin || isDataEntry) && (
                  <div className="flex gap-2 pt-2">
                    {isAdmin && selectedAnimal.status === 'active' && (
                      <Button variant="outline" className="gap-2 flex-1" onClick={handleOpenTransfer}>
                        <ArrowsLeftRight className="h-4 w-4" />
                        Transfer
                      </Button>
                    )}
                    <Button
                      className="flex-1"
                      onClick={function () {
                        setSheetOpen(false);
                        handleOpenAddDialog(selectedAnimal);
                      }}
                    >
                      Edit
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* ── Add / Edit Dialog ── */}
      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editingAnimal ? 'Edit Animal' : 'Add Animal'}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="tag_number">Tag Number *</Label>
                <Input
                  id="tag_number"
                  value={formData.tag_number}
                  onChange={function (e) { setField('tag_number', e.target.value); }}
                  placeholder="e.g., T-001"
                  required
                  data-testid="tag-number-input"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="animal_name">Name (Optional)</Label>
                <Input
                  id="animal_name"
                  value={formData.name}
                  onChange={function (e) { setField('name', e.target.value); }}
                  placeholder="e.g., Bella"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Species *</Label>
                <Select
                  value={formData.species}
                  onValueChange={function (v) { setFormData(function (p) { return { ...p, species: v, category_id: '' }; }); }}
                >
                  <SelectTrigger data-testid="species-select">
                    <SelectValue placeholder="Select species" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cattle">Cattle</SelectItem>
                    <SelectItem value="sheep">Sheep</SelectItem>
                    <SelectItem value="goat">Goat</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Category *</Label>
                <Select
                  value={formData.category_id}
                  onValueChange={function (v) { setField('category_id', v); }}
                  disabled={!formData.species}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={formData.species ? 'Select category' : 'Select species first'} />
                  </SelectTrigger>
                  <SelectContent>
                    {formCategories.map(function (cat) {
                      return (
                        <SelectItem key={cat.id} value={String(cat.id)}>
                          {cat.name_sw} ({cat.name_en})
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Location *</Label>
                <Select
                  value={formData.location_id}
                  onValueChange={function (v) { setField('location_id', v); }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select location" />
                  </SelectTrigger>
                  <SelectContent>
                    {locations.map(function (loc) {
                      return <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>;
                    })}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Sex *</Label>
                <Select
                  value={formData.sex}
                  onValueChange={function (v) { setField('sex', v); }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select sex" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Acquisition Type *</Label>
                <Select
                  value={formData.acquisition_type}
                  onValueChange={function (v) { setField('acquisition_type', v); }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="How acquired" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="born">Born on farm</SelectItem>
                    <SelectItem value="bought">Bought</SelectItem>
                    <SelectItem value="gift_in">Gift In</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="acquisition_date">Acquisition Date *</Label>
                <Input
                  id="acquisition_date"
                  type="date"
                  value={formData.acquisition_date}
                  onChange={function (e) { setField('acquisition_date', e.target.value); }}
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="birth_date">Birth Date (Optional)</Label>
                <Input
                  id="birth_date"
                  type="date"
                  value={formData.birth_date}
                  onChange={function (e) { setField('birth_date', e.target.value); }}
                />
              </div>
              <div /> {/* spacer */}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="mother_tag">Mother Tag (Optional)</Label>
                <Input
                  id="mother_tag"
                  value={formData.mother_tag}
                  onChange={function (e) { setField('mother_tag', e.target.value); }}
                  placeholder="e.g., T-024"
                  className="font-mono"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="father_tag">Father Tag (Optional)</Label>
                <Input
                  id="father_tag"
                  value={formData.father_tag}
                  onChange={function (e) { setField('father_tag', e.target.value); }}
                  placeholder="e.g., T-007"
                  className="font-mono"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="animal_notes">Notes (Optional)</Label>
              <Textarea
                id="animal_notes"
                value={formData.notes}
                onChange={function (e) { setField('notes', e.target.value); }}
                placeholder="Any additional notes..."
                rows={3}
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={function () { setAddDialogOpen(false); }}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  saving ||
                  !formData.tag_number ||
                  !formData.species ||
                  !formData.category_id ||
                  !formData.location_id ||
                  !formData.sex ||
                  !formData.acquisition_type ||
                  !formData.acquisition_date
                }
                data-testid="save-animal-btn"
              >
                {saving ? 'Saving...' : editingAnimal ? 'Update Animal' : 'Add Animal'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Transfer Dialog ── */}
      <Dialog open={transferDialogOpen} onOpenChange={setTransferDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">Transfer Animal</DialogTitle>
          </DialogHeader>
          {selectedAnimal && (
            <div className="mb-4 p-3 bg-muted rounded-lg text-sm">
              <span className="font-mono font-medium">{selectedAnimal.tag_number}</span>
              {selectedAnimal.name && <span className="text-muted-foreground"> ({selectedAnimal.name})</span>}
              <span className="text-muted-foreground"> — currently at {selectedAnimal.location_name}</span>
            </div>
          )}
          <form onSubmit={handleTransfer} className="space-y-4">
            <div className="space-y-2">
              <Label>Transfer To *</Label>
              <Select
                value={transferForm.to_location_id}
                onValueChange={function (v) { setTransferForm(function (p) { return { ...p, to_location_id: v }; }); }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select destination location" />
                </SelectTrigger>
                <SelectContent>
                  {locations
                    .filter(function (l) { return selectedAnimal && l.id !== selectedAnimal.location_id; })
                    .map(function (loc) {
                      return <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>;
                    })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="transfer_date">Transfer Date *</Label>
              <Input
                id="transfer_date"
                type="date"
                value={transferForm.transfer_date}
                onChange={function (e) { setTransferForm(function (p) { return { ...p, transfer_date: e.target.value }; }); }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="transfer_notes">Notes (Optional)</Label>
              <Textarea
                id="transfer_notes"
                value={transferForm.notes}
                onChange={function (e) { setTransferForm(function (p) { return { ...p, notes: e.target.value }; }); }}
                placeholder="Reason for transfer..."
                rows={2}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={function () { setTransferDialogOpen(false); }}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={transferring || !transferForm.to_location_id || !transferForm.transfer_date}
              >
                {transferring ? 'Transferring...' : 'Transfer'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Bulk Import Dialog ── */}
      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">Bulk Import Animals</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground mb-3">
                Download the CSV template, fill in your animals, then upload.
              </p>
              <Button variant="outline" className="gap-2" onClick={handleDownloadTemplate}>
                <DownloadSimple className="h-4 w-4" />
                Download Template
              </Button>
            </div>

            <div className="space-y-2">
              <Label>Upload CSV File</Label>
              <Input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileSelect}
                disabled={importing}
                data-testid="animals-file-input"
              />
            </div>

            {importing && (
              <div className="text-center py-4">
                <p className="text-muted-foreground">Importing...</p>
              </div>
            )}

            {importResult && (
              <div className="p-4 bg-muted rounded-lg space-y-2">
                <p className="font-medium">Import Result:</p>
                <p className="text-sm text-green-600">Created: {importResult.created}</p>
                {importResult.skipped > 0 && (
                  <p className="text-sm text-yellow-600">Skipped (duplicates): {importResult.skipped}</p>
                )}
                {importResult.errors && importResult.errors.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm text-red-600 font-medium">Errors:</p>
                    <ul className="text-sm text-red-600 list-disc list-inside space-y-1">
                      {importResult.errors.slice(0, 5).map(function (err, i) {
                        return <li key={i}>{err}</li>;
                      })}
                      {importResult.errors.length > 5 && (
                        <li>...and {importResult.errors.length - 5} more</li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
}

export default Animals;
