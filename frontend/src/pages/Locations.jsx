import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { getLocations, createLocation, updateLocation, importLocations, downloadLocationsTemplate } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Skeleton } from '../components/ui/skeleton';
import { MapPin, Plus, Pencil, Eye, DownloadSimple, UploadSimple, FileText } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { formatDate } from '../lib/utils';

function Locations() {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [editingLocation, setEditingLocation] = useState(null);
  const [formData, setFormData] = useState({ name: '', description: '' });
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const fileInputRef = useRef(null);
  const { isAdmin } = useAuth();

  useEffect(function() {
    loadLocations();
  }, []);

  async function loadLocations() {
    try {
      const response = await getLocations();
      setLocations(response.data);
    } catch (error) {
      toast.error('Failed to load locations');
    } finally {
      setLoading(false);
    }
  }

  function handleOpenDialog(location) {
    if (location) {
      setEditingLocation(location);
      setFormData({ name: location.name, description: location.description || '' });
    } else {
      setEditingLocation(null);
      setFormData({ name: '', description: '' });
    }
    setDialogOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);

    try {
      if (editingLocation) {
        await updateLocation(editingLocation.id, formData);
        toast.success('Location updated successfully');
      } else {
        await createLocation(formData);
        toast.success('Location created successfully');
      }
      setDialogOpen(false);
      loadLocations();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save location');
    } finally {
      setSaving(false);
    }
  }

  function handleDownloadTemplate() {
    window.open(downloadLocationsTemplate(), '_blank');
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
      const response = await importLocations(file);
      setImportResult(response.data);
      toast.success(response.data.message);
      loadLocations();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to import locations');
      setImportResult({ errors: [error.response?.data?.detail || 'Import failed'] });
    } finally {
      setImporting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="locations-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold">Locations</h1>
          <p className="text-muted-foreground mt-1">Manage your farm locations</p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" className="gap-2" data-testid="import-locations-btn">
                  <UploadSimple className="h-4 w-4" />
                  Import CSV
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="font-heading">Import Locations</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="p-4 bg-muted rounded-lg">
                    <p className="text-sm text-muted-foreground mb-3">
                      Download the template, fill in your locations, then upload the file.
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
                      data-testid="locations-file-input"
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
                      <p className="text-sm text-yellow-600">Skipped: {importResult.skipped}</p>
                      {importResult.errors && importResult.errors.length > 0 && (
                        <div className="mt-2">
                          <p className="text-sm text-red-600 font-medium">Errors:</p>
                          <ul className="text-sm text-red-600 list-disc list-inside">
                            {importResult.errors.slice(0, 5).map(function(err, i) {
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

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="gap-2" onClick={function() { handleOpenDialog(null); }} data-testid="add-location-btn">
                  <Plus className="h-4 w-4" />
                  Add Location
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="font-heading">
                    {editingLocation ? 'Edit Location' : 'Add New Location'}
                  </DialogTitle>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Location Name</Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={function(e) { setFormData({ ...formData, name: e.target.value }); }}
                      placeholder="e.g., Shamba Kuu"
                      required
                      data-testid="location-name-input"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="description">Description (Optional)</Label>
                    <Textarea
                      id="description"
                      value={formData.description}
                      onChange={function(e) { setFormData({ ...formData, description: e.target.value }); }}
                      placeholder="Brief description of this location"
                      data-testid="location-desc-input"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={function() { setDialogOpen(false); }}>
                      Cancel
                    </Button>
                    <Button type="submit" disabled={saving} data-testid="save-location-btn">
                      {saving ? 'Saving...' : editingLocation ? 'Update' : 'Create'}
                    </Button>
                  </div>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        )}
      </div>

      {locations.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {locations.map(function(location) {
            return (
              <Card key={location.id} className="border-border/60 hover:shadow-lg transition-shadow" data-testid={`location-card-${location.id}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <MapPin className="h-5 w-5 text-primary" weight="fill" />
                      </div>
                      <div>
                        <CardTitle className="font-heading text-lg">{location.name}</CardTitle>
                        <p className="text-xs text-muted-foreground">
                          Added {formatDate(location.created_at)}
                        </p>
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {location.description && (
                    <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                      {location.description}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <Link to={`/locations/${location.id}`} className="flex-1">
                      <Button variant="outline" className="w-full gap-2" data-testid={`view-location-${location.id}`}>
                        <Eye className="h-4 w-4" />
                        View Details
                      </Button>
                    </Link>
                    {isAdmin && (
                      <Button variant="ghost" size="icon" onClick={function() { handleOpenDialog(location); }} data-testid={`edit-location-${location.id}`}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card className="border-border/60">
          <CardContent className="py-12 text-center">
            <MapPin className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
            <p className="text-muted-foreground mb-4">No locations yet</p>
            {isAdmin && (
              <div className="flex gap-2 justify-center">
                <Button variant="outline" className="gap-2" onClick={handleDownloadTemplate}>
                  <FileText className="h-4 w-4" />
                  Download Template
                </Button>
                <Button onClick={function() { handleOpenDialog(null); }} className="gap-2">
                  <Plus className="h-4 w-4" />
                  Add Your First Location
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default Locations;
