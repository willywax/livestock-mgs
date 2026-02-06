import React, { useState, useEffect } from 'react';
import { getDiseases, createDisease, deleteDisease } from '../lib/api';
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
import { Gear, Plus, Trash, FirstAid, Cow, Dog } from '@phosphor-icons/react';
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
  
  // Form state for new disease
  const [newDisease, setNewDisease] = useState({
    name: '',
    description: '',
    species: ''
  });

  useEffect(function() {
    loadDiseases();
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
