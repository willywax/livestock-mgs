import React, { useState, useEffect } from 'react';
import { getDiseases, createDisease, deleteDisease, getVaccineTypes, createVaccineType, updateVaccineType, deleteVaccineType } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle, 
  DialogTrigger 
} from '../components/ui/dialog';
import { Gear, Plus, Trash, FirstAid, Cow, Dog, Syringe, PencilSimple } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { SPECIES_CONFIG } from '../lib/utils';
import { importAnimalIdentifiers } from '../lib/api';
import { importPDTests } from '../lib/api';
import { listDeathCauses, createDeathCause, updateDeathCause, deleteDeathCause, getMortalityThresholds, updateMortalityThresholds } from '../lib/api';

function IdentifierImportCard() {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const importFile = async () => {
    if (!file) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const response = await importAnimalIdentifiers(file);
      setResult(response.data);
      toast.success('Identifier import complete');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to import identifiers');
    } finally { setBusy(false); }
  };
  return (
    <Card>
      <CardHeader><CardTitle>Import baseline identifiers</CardTitle><CardDescription>Upload the Nyigoti baseline CSV to add identifiers to existing animals.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <Label htmlFor="identifier-csv">Baseline CSV</Label>
        <Input id="identifier-csv" type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => {
          const picked = e.target.files[0];
          setResult(null);
          setError('');
          if (picked && !picked.name.toLowerCase().endsWith('.csv')) {
            setFile(null); setError('Choose a CSV file'); e.target.value = ''; return;
          }
          setFile(picked || null);
        }} />
        <Button onClick={importFile} disabled={busy || !file}>{busy ? 'Importing…' : 'Import'}</Button>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {result && <div role="status" className="rounded-lg border p-4 space-y-3">
          <p>Matched {result.matched} animals · Added {result.identifiers_added} identifiers · {result.already_existed} already existed · Reproductive fields updated for {result.repro_fields_updated} animals</p>
          {result.unmatched_eids.length > 0 && <details>
            <summary className="cursor-pointer">{result.unmatched_eids.length} animals not found in register</summary>
            <ul className="mt-2 max-h-60 overflow-auto list-disc pl-5 font-mono text-sm">{result.unmatched_eids.map((eid, index) => <li key={index}>{eid || '(missing EID short)'}</li>)}</ul>
          </details>}
        </div>}
      </CardContent>
    </Card>
  );
}

function Settings() {
  const { user } = useAuth();
  const [diseases, setDiseases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [selectedDisease, setSelectedDisease] = useState(null);
  
  const [newDisease, setNewDisease] = useState({ name: '', description: '', species: '' });

  const [vaccineTypes, setVaccineTypes] = useState([]);
  const [vaccineDialogOpen, setVaccineDialogOpen] = useState(false);
  const [editingVaccine, setEditingVaccine] = useState(null);
  const [savingVaccine, setSavingVaccine] = useState(false);
  const [vaccineDeleteTarget, setVaccineDeleteTarget] = useState(null);
  const [vaccineForm, setVaccineForm] = useState({
    name: '', description: '', default_interval_days: '',
    all_species: true, cattle: false, sheep: false, goat: false,
  });

  useEffect(function() {
    loadDiseases();
    loadVaccineTypes();
  }, []);

  async function loadDiseases() {
    try {
      const response = await getDiseases();
      setDiseases(response.data);
    } catch (error) {
      toast.error('Failed to load diseases');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateDisease() {
    if (!newDisease.name.trim()) {
      toast.error('Disease name is required');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: newDisease.name.trim(),
        description: newDisease.description.trim() || null,
        species: newDisease.species || null
      };
      
      await createDisease(payload);
      toast.success('Disease added successfully');
      setDialogOpen(false);
      setNewDisease({ name: '', description: '', species: '' });
      loadDiseases();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add disease');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteDisease() {
    if (!selectedDisease) return;
    
    setSaving(true);
    try {
      await deleteDisease(selectedDisease.id);
      toast.success('Disease removed successfully');
      setDeleteConfirmOpen(false);
      setSelectedDisease(null);
      loadDiseases();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to remove disease');
    } finally {
      setSaving(false);
    }
  }

  function openDeleteConfirm(disease) {
    setSelectedDisease(disease);
    setDeleteConfirmOpen(true);
  }

  async function loadVaccineTypes() {
    try {
      const res = await getVaccineTypes();
      setVaccineTypes(res.data);
    } catch {}
  }

  function openAddVaccine() {
    setEditingVaccine(null);
    setVaccineForm({ name: '', description: '', default_interval_days: '', all_species: true, cattle: false, sheep: false, goat: false });
    setVaccineDialogOpen(true);
  }

  function openEditVaccine(vt) {
    setEditingVaccine(vt);
    const specAll = !vt.species_applicability || vt.species_applicability.length === 0;
    setVaccineForm({
      name: vt.name,
      description: vt.description || '',
      default_interval_days: vt.default_interval_days ? String(vt.default_interval_days) : '',
      all_species: specAll,
      cattle: !specAll && vt.species_applicability.includes('CATTLE'),
      sheep: !specAll && vt.species_applicability.includes('SHEEP'),
      goat: !specAll && vt.species_applicability.includes('GOAT'),
    });
    setVaccineDialogOpen(true);
  }

  async function handleSaveVaccine() {
    if (!vaccineForm.name.trim()) { toast.error('Vaccine name is required'); return; }
    let species_applicability = null;
    if (!vaccineForm.all_species) {
      const selected = [];
      if (vaccineForm.cattle) selected.push('CATTLE');
      if (vaccineForm.sheep) selected.push('SHEEP');
      if (vaccineForm.goat) selected.push('GOAT');
      if (selected.length === 0) { toast.error('Select at least one species or choose All'); return; }
      species_applicability = selected;
    }
    const payload = {
      name: vaccineForm.name.trim(),
      description: vaccineForm.description.trim() || null,
      default_interval_days: vaccineForm.default_interval_days ? parseInt(vaccineForm.default_interval_days) : null,
      species_applicability,
    };
    setSavingVaccine(true);
    try {
      if (editingVaccine) {
        await updateVaccineType(editingVaccine.id, payload);
        toast.success('Vaccine type updated');
      } else {
        await createVaccineType(payload);
        toast.success('Vaccine type added');
      }
      setVaccineDialogOpen(false);
      loadVaccineTypes();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save vaccine type');
    } finally {
      setSavingVaccine(false);
    }
  }

  async function handleDeleteVaccine() {
    if (!vaccineDeleteTarget) return;
    setSavingVaccine(true);
    try {
      await deleteVaccineType(vaccineDeleteTarget.id);
      toast.success('Vaccine type removed');
      setVaccineDeleteTarget(null);
      loadVaccineTypes();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Cannot remove — vaccine type is currently in use');
      setVaccineDeleteTarget(null);
    } finally {
      setSavingVaccine(false);
    }
  }

  const isAdmin = user?.role === 'admin';

  if (loading) {
    return <div className="flex items-center justify-center py-12">Loading...</div>;
  }

  return (
    <div className="space-y-6" data-testid="settings-page">
      <div>
        <h1 className="font-heading text-3xl font-bold flex items-center gap-3">
          <Gear className="h-8 w-8 text-primary" weight="fill" />
          Settings
        </h1>
        <p className="text-muted-foreground mt-1">Configure system settings and manage diseases</p>
      </div>

      {isAdmin && <IdentifierImportCard />}
      {isAdmin && <PDTestImportCard />}

      <Card className="border-border/60">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="font-heading flex items-center gap-2">
                <FirstAid className="h-5 w-5 text-primary" weight="fill" />
                Disease Management
              </CardTitle>
              <CardDescription>
                Manage the list of diseases for death cause tracking
              </CardDescription>
            </div>
            {isAdmin && (
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button className="gap-2" data-testid="add-disease-btn">
                    <Plus className="h-4 w-4" />
                    Add Disease
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add New Disease</DialogTitle>
                    <DialogDescription>
                      Add a new disease to the system for death cause tracking
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label htmlFor="disease-name">Disease Name *</Label>
                      <Input
                        id="disease-name"
                        value={newDisease.name}
                        onChange={function(e) { setNewDisease({ ...newDisease, name: e.target.value }); }}
                        placeholder="e.g., East Coast Fever"
                        data-testid="disease-name-input"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="disease-description">Description (Optional)</Label>
                      <Textarea
                        id="disease-description"
                        value={newDisease.description}
                        onChange={function(e) { setNewDisease({ ...newDisease, description: e.target.value }); }}
                        placeholder="Brief description of the disease..."
                        rows={3}
                        data-testid="disease-description-input"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="disease-species">Applicable Species (Optional)</Label>
                      <Select 
                        value={newDisease.species} 
                        onValueChange={function(v) { setNewDisease({ ...newDisease, species: v }); }}
                      >
                        <SelectTrigger data-testid="disease-species-select">
                          <SelectValue placeholder="All Species" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Species</SelectItem>
                          <SelectItem value="cattle">Cattle</SelectItem>
                          <SelectItem value="sheep">Sheep</SelectItem>
                          <SelectItem value="goat">Goat</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Leave as &quot;All Species&quot; if disease can affect any animal
                      </p>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={function() { setDialogOpen(false); }}>
                      Cancel
                    </Button>
                    <Button onClick={handleCreateDisease} disabled={saving} data-testid="save-disease-btn">
                      {saving ? 'Saving...' : 'Add Disease'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {diseases.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <FirstAid className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No diseases configured yet</p>
              {isAdmin && <p className="text-sm">Click &quot;Add Disease&quot; to get started</p>}
            </div>
          ) : (
            <div className="space-y-3">
              {diseases.map(function(disease) {
                const speciesConfig = disease.species ? SPECIES_CONFIG[disease.species] : null;
                return (
                  <div 
                    key={disease.id} 
                    className="flex items-center justify-between p-4 rounded-lg border border-border bg-muted/30 hover:bg-muted/50 transition-colors"
                    data-testid={`disease-item-${disease.id}`}
                  >
                    <div className="flex items-center gap-4">
                      <div className="h-10 w-10 rounded-full bg-red-100 flex items-center justify-center">
                        <FirstAid className="h-5 w-5 text-red-600" weight="fill" />
                      </div>
                      <div>
                        <h3 className="font-medium">{disease.name}</h3>
                        {disease.description && (
                          <p className="text-sm text-muted-foreground">{disease.description}</p>
                        )}
                        <div className="flex items-center gap-2 mt-1">
                          {speciesConfig ? (
                            <Badge variant="outline" style={{ borderColor: speciesConfig.color, color: speciesConfig.color }}>
                              {speciesConfig.label} only
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-muted-foreground">
                              All Species
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    {isAdmin && (
                      <Button 
                        variant="ghost" 
                        size="icon"
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={function() { openDeleteConfirm(disease); }}
                        data-testid={`delete-disease-${disease.id}`}
                      >
                        <Trash className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {isAdmin && (
        <Card className="border-border/60">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="font-heading flex items-center gap-2">
                  <Syringe className="h-5 w-5 text-primary" />
                  Vaccine Types
                </CardTitle>
                <CardDescription>Manage vaccine types and default schedules</CardDescription>
              </div>
              <Button className="gap-2" onClick={openAddVaccine}>
                <Plus className="h-4 w-4" />
                Add Vaccine Type
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {vaccineTypes.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Syringe className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No vaccine types configured yet</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-muted-foreground border-b text-xs">
                      <th className="text-left font-medium pb-2 pr-4">Name</th>
                      <th className="text-left font-medium pb-2 pr-4">Species</th>
                      <th className="text-left font-medium pb-2 pr-4">Default interval</th>
                      <th className="text-left font-medium pb-2 pr-4">Status</th>
                      <th className="text-right font-medium pb-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vaccineTypes.map(function(vt) {
                      const specLabel = (!vt.species_applicability || vt.species_applicability.length === 0)
                        ? 'All species'
                        : vt.species_applicability.map(function(s) { return s.charAt(0) + s.slice(1).toLowerCase(); }).join(', ');
                      return (
                        <tr key={vt.id} className="border-b border-border/50 last:border-0">
                          <td className="py-2.5 pr-4 font-medium text-foreground">{vt.name}</td>
                          <td className="py-2.5 pr-4 text-muted-foreground text-xs">{specLabel}</td>
                          <td className="py-2.5 pr-4 text-muted-foreground text-xs">
                            {vt.default_interval_days ? `Every ${vt.default_interval_days} days` : '—'}
                          </td>
                          <td className="py-2.5 pr-4">
                            <Badge variant={vt.is_active ? 'default' : 'secondary'} className="text-xs">
                              {vt.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </td>
                          <td className="py-2.5 text-right">
                            <div className="flex gap-1 justify-end">
                              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={function() { openEditVaccine(vt); }}>
                                <PencilSimple className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-destructive hover:text-destructive"
                                onClick={function() { setVaccineDeleteTarget(vt); }}
                              >
                                <Trash className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Add/Edit Vaccine Type Dialog */}
      <Dialog open={vaccineDialogOpen} onOpenChange={setVaccineDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingVaccine ? 'Edit Vaccine Type' : 'Add Vaccine Type'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Name *</Label>
              <Input
                value={vaccineForm.name}
                onChange={function(e) { setVaccineForm(function(p) { return { ...p, name: e.target.value }; }); }}
                placeholder="e.g. FMD, Blackleg..."
              />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Textarea
                rows={2}
                value={vaccineForm.description}
                onChange={function(e) { setVaccineForm(function(p) { return { ...p, description: e.target.value }; }); }}
                placeholder="Optional description..."
              />
            </div>
            <div className="space-y-2">
              <Label>Default interval (days)</Label>
              <Input
                type="number"
                min="1"
                value={vaccineForm.default_interval_days}
                onChange={function(e) { setVaccineForm(function(p) { return { ...p, default_interval_days: e.target.value }; }); }}
                placeholder="e.g. 180 — leave blank for no fixed schedule"
              />
            </div>
            <div className="space-y-2">
              <Label>Species applicability</Label>
              <div className="mt-1 space-y-1.5">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={vaccineForm.all_species}
                    onChange={function(e) {
                      setVaccineForm(function(p) {
                        return { ...p, all_species: e.target.checked, cattle: false, sheep: false, goat: false };
                      });
                    }}
                  />
                  All species
                </label>
                {!vaccineForm.all_species && ['cattle', 'sheep', 'goat'].map(function(sp) {
                  return (
                    <label key={sp} className="flex items-center gap-2 text-sm cursor-pointer capitalize ml-4">
                      <input
                        type="checkbox"
                        checked={vaccineForm[sp]}
                        onChange={function(e) {
                          setVaccineForm(function(p) { return { ...p, [sp]: e.target.checked }; });
                        }}
                      />
                      {sp}
                    </label>
                  );
                })}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={function() { setVaccineDialogOpen(false); }}>Cancel</Button>
            <Button onClick={handleSaveVaccine} disabled={savingVaccine}>
              {savingVaccine ? 'Saving...' : editingVaccine ? 'Update' : 'Add Vaccine Type'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Vaccine Type Confirm */}
      <Dialog open={!!vaccineDeleteTarget} onOpenChange={function(o) { if (!o) setVaccineDeleteTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove Vaccine Type</DialogTitle>
            <DialogDescription>
              Remove &quot;{vaccineDeleteTarget?.name}&quot;? This will fail if the vaccine type is linked to existing health events.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={function() { setVaccineDeleteTarget(null); }}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteVaccine} disabled={savingVaccine}>
              {savingVaccine ? 'Removing...' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove Disease</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove &quot;{selectedDisease?.name}&quot;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={function() { setDeleteConfirmOpen(false); }}>
              Cancel
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleDeleteDisease} 
              disabled={saving}
              data-testid="confirm-delete-disease"
            >
              {saving ? 'Removing...' : 'Remove'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {isAdmin && <DeathCauseSettings />}
      {isAdmin && <MortalityThresholdSettings />}
    </div>
  );
}

export default Settings;


function PDTestImportCard() {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const importing = React.useRef(false);
  const fileInput = React.useRef(null);
  const template = 'tag_number,test_date,result,months_pregnant,vet,notes\n';
  const importFile = async () => {
    if (!file || importing.current) return;
    importing.current = true;
    setBusy(true); setError(''); setResult(null);
    try {
      const { data } = await importPDTests(file);
      setResult(data);
      setFile(null);
      if (fileInput.current) fileInput.current.value = '';
      toast.success('PD test import complete');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to import PD tests. Please try again.');
    } finally { importing.current = false; setBusy(false); }
  };
  return <Card>
    <CardHeader><CardTitle>Bulk PD Test Import</CardTitle>
      <CardDescription>Import pregnancy diagnosis results for active animals by tag number.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      <a className="text-sm text-primary underline" download="pd-tests-template.csv"
        href={`data:text/csv;charset=utf-8,${encodeURIComponent(template)}`}>Download template</a>
      <p className="overflow-x-auto font-mono text-xs">tag_number,test_date,result,months_pregnant,vet,notes</p>
      <p className="text-sm text-muted-foreground">Use YYYY-MM-DD dates. Results: pregnant / yes / p, open / no / negative / n, or recheck / r / check. Months pregnant, vet, and notes may be blank. Each row creates a new event; repeated imports create additional events.</p>
      <Label htmlFor="pd-tests-csv">PD results CSV</Label>
      <Input ref={fileInput} id="pd-tests-csv" type="file" accept=".csv,text/csv" disabled={busy}
        onChange={(event) => {
          const picked = event.target.files?.[0];
          setError(''); setResult(null);
          if (picked && !picked.name.toLowerCase().endsWith('.csv')) {
            setFile(null); setError('Choose a CSV file'); event.target.value = ''; return;
          }
          setFile(picked || null);
        }} />
      <Button onClick={importFile} disabled={busy || !file}>{busy ? 'Importing…' : 'Import'}</Button>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {result && <div role="status" className="space-y-3 rounded-lg border p-4">
        <p>{result.matched} animals updated · {result.events_created} events created</p>
        <p className="text-sm text-muted-foreground">{result.total_rows} rows processed</p>
        {result.not_found.length > 0 && <details>
          <summary className="cursor-pointer">{result.not_found.length} not found</summary>
          <ul className="mt-2 max-h-60 list-disc overflow-auto pl-5 font-mono text-sm">{result.not_found.map((tag, index) => <li key={index}>{tag}</li>)}</ul>
        </details>}
        {result.skipped.length > 0 && <details>
          <summary className="cursor-pointer">{result.skipped.length} rows skipped (missing required fields)</summary>
          <ul className="mt-2 max-h-60 list-disc overflow-auto pl-5 text-sm">{result.skipped.map((row, index) => <li key={index}>{row}</li>)}</ul>
        </details>}
      </div>}
    </CardContent>
  </Card>;
}

function mortalitySettingsError(error) {
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : 'Could not save mortality settings. Please try again.';
}

function DeathCauseSettings() {
  const [causes, setCauses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [editor, setEditor] = useState(null);
  const saving = React.useRef(false);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    Promise.all([listDeathCauses(), listDeathCauses({ is_active: false })])
      .then(([enabled, disabled]) => { if (active) setCauses([...enabled.data, ...disabled.data]); })
      .catch(() => { if (active) setError('Could not load causes. Please retry.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  async function mutate(action) {
    if (saving.current) return;
    saving.current = true; setBusy(true); setError('');
    try {
      await action();
      setEditor(null); setRefresh((value) => value + 1);
      toast.success('Death causes updated');
    } catch (err) { setError(mortalitySettingsError(err)); }
    finally { saving.current = false; setBusy(false); }
  }
  const inactive = causes.filter((item) => !item.is_active);
  const renderCause = (item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 border-b py-3 last:border-0">
    <div className="min-w-0"><p className="break-words font-medium">{item.name}</p>{item.description && <p className="text-sm text-muted-foreground">{item.description}</p>}</div>
    <div className="flex gap-2">
      <Button variant="ghost" size="icon" aria-label={`Edit ${item.name}`} disabled={busy || !!editor} onClick={() => { setError(''); setEditor({ id: item.id, name: item.name, description: item.description || '' }); }}><PencilSimple className="h-4 w-4" /></Button>
      {item.is_active ? <Button variant="outline" size="sm" disabled={busy || !!editor} onClick={() => mutate(() => deleteDeathCause(item.id))}>Deactivate</Button> :
        <Button variant="outline" size="sm" disabled={busy || !!editor} onClick={() => mutate(() => updateDeathCause(item.id, { is_active: true }))}>Reactivate</Button>}
    </div>
  </li>;
  return <Card><CardHeader><CardTitle>Cause of Death</CardTitle><CardDescription>Manage structured causes available when recording deaths. Deactivation preserves historical records.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      {error && <div role="alert" className="text-sm text-red-700">{error} <Button variant="ghost" size="sm" disabled={busy || loading} onClick={() => setRefresh((value) => value + 1)}>Retry loading</Button></div>}
      {loading ? <p role="status">Loading causes…</p> : <>
        <ul>{causes.filter((item) => item.is_active).map(renderCause)}</ul>
        {!causes.some((item) => item.is_active) && <p className="text-sm text-muted-foreground">No active causes.</p>}
        {!editor && <Button variant="outline" disabled={busy} onClick={() => { setError(''); setEditor({ id: null, name: '', description: '' }); }}>+ Add cause</Button>}
        {editor && <form className="space-y-3 rounded-lg border p-4" onSubmit={(event) => {
          event.preventDefault();
          const name = editor.name.trim();
          if (!name) { setError('Enter a cause name.'); return; }
          const data = { name, description: editor.description.trim() || null };
          mutate(() => editor.id == null ? createDeathCause(data) : updateDeathCause(editor.id, data));
        }}>
          <Label htmlFor="death-cause-name">{editor.id == null ? 'New cause' : 'Edit cause'}</Label>
          <Input id="death-cause-name" required maxLength={100} disabled={busy} value={editor.name} onChange={(event) => setEditor({ ...editor, name: event.target.value })} />
          <Label htmlFor="death-cause-description">Description (optional)</Label>
          <Input id="death-cause-description" disabled={busy} value={editor.description} onChange={(event) => setEditor({ ...editor, description: event.target.value })} />
          <div className="flex gap-2"><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save cause'}</Button><Button type="button" variant="ghost" disabled={busy} onClick={() => { setEditor(null); setError(''); }}>Cancel</Button></div>
        </form>}
        {inactive.length > 0 && <details><summary className="cursor-pointer text-sm">Show inactive ({inactive.length})</summary><ul>{inactive.map(renderCause)}</ul></details>}
      </>}
    </CardContent>
  </Card>;
}

function MortalityThresholdSettings() {
  const [values, setValues] = useState({ cattle: '', sheep: '', goat: '' });
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const saving = React.useRef(false);
  const toValues = (rows) => Object.fromEntries(['cattle', 'sheep', 'goat'].map((key) => [key, String(rows.find((row) => row.species === key)?.threshold ?? '')]));
  useEffect(() => {
    let active = true;
    setLoading(true); setLoaded(false); setError('');
    getMortalityThresholds().then(({ data }) => {
      if (active) {
        setValues(Object.fromEntries(['cattle', 'sheep', 'goat'].map((key) => [key, String(data.find((row) => row.species === key)?.threshold ?? '')])));
        setLoaded(true);
      }
    }).catch(() => { if (active) setError('Could not load thresholds. Please retry.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  async function save(event) {
    event.preventDefault();
    if (saving.current || !loaded) return;
    const data = Object.entries(values).filter(([, value]) => value !== '').map(([species, threshold]) => ({ species, threshold }));
    if (!data.length) { setError('Enter at least one threshold.'); return; }
    saving.current = true; setBusy(true); setError('');
    try {
      const response = await updateMortalityThresholds(data);
      setValues(toValues(response.data)); toast.success('Mortality thresholds saved');
    } catch (err) { setError(mortalitySettingsError(err)); }
    finally { saving.current = false; setBusy(false); }
  }
  return <Card><CardHeader><CardTitle>Mortality Alert Thresholds</CardTitle><CardDescription>Alerts appear when a mortality rate exceeds its species threshold.</CardDescription></CardHeader>
    <CardContent><form onSubmit={save} className="space-y-4">
      {error && <div role="alert" className="text-sm text-red-700">{error}{!loaded && <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>Retry</Button>}</div>}
      {loading && <p role="status">Loading thresholds…</p>}
      <fieldset disabled={loading || busy || !loaded} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">{[['cattle', 'Cattle'], ['sheep', 'Sheep'], ['goat', 'Goats']].map(([key, label]) =>
          <div key={key}><Label htmlFor={`mortality-${key}`}>{label}</Label><div className="mt-1 flex items-center gap-2"><Input id={`mortality-${key}`} type="number" min="0" max="999.99" step="0.01" placeholder="Not set" value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} /><span>%</span></div></div>)}</div>
        <p className="text-sm text-muted-foreground">Leave a field blank to keep its current setting. Species without a threshold do not trigger alerts.</p>
        <Button type="submit">{busy ? 'Saving…' : 'Save thresholds'}</Button>
      </fieldset>
    </form></CardContent>
  </Card>;
}
