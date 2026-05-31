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
    </div>
  );
}

export default Settings;
