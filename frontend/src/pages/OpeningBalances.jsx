import React, { useState, useEffect, useRef } from 'react';
import { getLocations, getCategories, getOpeningBalances, createOpeningBalance, updateOpeningBalance, importOpeningBalances, downloadOpeningBalancesTemplate } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Skeleton } from '../components/ui/skeleton';
import { Scales, Plus, Pencil, CalendarBlank, DownloadSimple, UploadSimple, FileText } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { SPECIES_CONFIG } from '../lib/utils';
import { format } from 'date-fns';

function OpeningBalances() {
  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState({});
  const [balances, setBalances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [selectedSpecies, setSelectedSpecies] = useState('cattle');
  const [selectedLocation, setSelectedLocation] = useState('');
  const fileInputRef = useRef(null);

  const [formData, setFormData] = useState({
    id: null,
    location_id: '',
    species: 'cattle',
    category_id: '',
    count: 0,
    period_start: new Date()
  });

  useEffect(function() {
    loadData();
  }, []);

  useEffect(function() {
    if (selectedLocation) {
      loadBalances();
    }
  }, [selectedLocation, selectedSpecies]);

  async function loadData() {
    try {
      const locRes = await getLocations();
      const cattleRes = await getCategories('cattle');
      const sheepRes = await getCategories('sheep');
      const goatRes = await getCategories('goat');
      
      setLocations(locRes.data);
      setCategories({
        cattle: cattleRes.data,
        sheep: sheepRes.data,
        goat: goatRes.data
      });
      
      if (locRes.data.length > 0) {
        setSelectedLocation(locRes.data[0].id.toString());
      }
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  async function loadBalances() {
    try {
      const response = await getOpeningBalances({
        location_id: selectedLocation,
        species: selectedSpecies
      });
      setBalances(response.data);
    } catch (error) {
      console.error('Failed to load balances');
    }
  }

  function handleOpenDialog(balance) {
    if (balance) {
      setFormData({
        id: balance.id,
        location_id: balance.location_id.toString(),
        species: balance.species,
        category_id: balance.category_id.toString(),
        count: balance.count,
        period_start: new Date(balance.period_start)
      });
    } else {
      setFormData({
        id: null,
        location_id: selectedLocation,
        species: selectedSpecies,
        category_id: '',
        count: 0,
        period_start: new Date()
      });
    }
    setDialogOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);

    try {
      const payload = {
        location_id: parseInt(formData.location_id),
        species: formData.species,
        category_id: parseInt(formData.category_id),
        count: parseInt(formData.count),
        period_start: format(formData.period_start, 'yyyy-MM-dd')
      };

      if (formData.id) {
        await updateOpeningBalance(formData.id, { count: payload.count });
        toast.success('Opening balance updated');
      } else {
        await createOpeningBalance(payload);
        toast.success('Opening balance created');
      }
      
      setDialogOpen(false);
      loadBalances();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save opening balance');
    } finally {
      setSaving(false);
    }
  }

  function handleDownloadTemplate() {
    const token = localStorage.getItem('token');
    const url = downloadOpeningBalancesTemplate();
    // Need to add auth header, so use fetch
    fetch(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(function(res) { return res.blob(); })
    .then(function(blob) {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'opening_balances_template.csv';
      a.click();
      window.URL.revokeObjectURL(url);
    });
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
      const response = await importOpeningBalances(file);
      setImportResult(response.data);
      toast.success(response.data.message);
      loadBalances();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to import balances');
      setImportResult({ errors: [error.response?.data?.detail || 'Import failed'] });
    } finally {
      setImporting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }

  const speciesCategories = categories[formData.species] || [];
  const currentCategories = categories[selectedSpecies] || [];

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="opening-balances-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold">Opening Balances</h1>
          <p className="text-muted-foreground mt-1">Set initial stock counts for each location</p>
        </div>
        <div className="flex gap-2">
          <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="gap-2" data-testid="import-balances-btn">
                <UploadSimple className="h-4 w-4" />
                Import CSV
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle className="font-heading">Import Opening Balances</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground mb-3">
                    Download the template with all categories and locations, fill in your counts, then upload.
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
                    data-testid="balances-file-input"
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
                    <p className="text-sm text-blue-600">Updated: {importResult.updated}</p>
                    {importResult.errors && importResult.errors.length > 0 && (
                      <div className="mt-2 max-h-40 overflow-y-auto">
                        <p className="text-sm text-red-600 font-medium">Errors:</p>
                        <ul className="text-sm text-red-600 list-disc list-inside">
                          {importResult.errors.slice(0, 10).map(function(err, i) {
                            return <li key={i}>{err}</li>;
                          })}
                          {importResult.errors.length > 10 && (
                            <li>...and {importResult.errors.length - 10} more</li>
                          )}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </DialogContent>
          </Dialog>

          <Button className="gap-2" onClick={function() { handleOpenDialog(null); }} data-testid="add-balance-btn">
            <Plus className="h-4 w-4" />
            Add Balance
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="border-border/60">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="space-y-1">
              <Label className="text-xs">Location</Label>
              <Select value={selectedLocation} onValueChange={setSelectedLocation}>
                <SelectTrigger className="w-[200px]" data-testid="location-filter">
                  <SelectValue placeholder="Select location" />
                </SelectTrigger>
                <SelectContent>
                  {locations.map(function(loc) {
                    return <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Species Tabs */}
      <Tabs value={selectedSpecies} onValueChange={setSelectedSpecies}>
        <TabsList>
          {Object.entries(SPECIES_CONFIG).map(function([key, config]) {
            return <TabsTrigger key={key} value={key} data-testid={`tab-${key}`}>{config.label.split(' ')[0]}</TabsTrigger>;
          })}
        </TabsList>

        {Object.keys(SPECIES_CONFIG).map(function(speciesKey) {
          return (
            <TabsContent key={speciesKey} value={speciesKey} className="mt-6">
              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="font-heading flex items-center gap-2">
                    <div className="h-4 w-4 rounded-full" style={{ backgroundColor: SPECIES_CONFIG[speciesKey].color }} />
                    {SPECIES_CONFIG[speciesKey].label} Categories
                  </CardTitle>
                  <CardDescription>
                    Set opening balances for each category at {locations.find(function(l) { return l.id.toString() === selectedLocation; })?.name || 'selected location'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {(categories[speciesKey] || []).map(function(cat) {
                      const balance = balances.find(function(b) { return b.category_id === cat.id; });
                      
                      return (
                        <div key={cat.id} className="p-4 rounded-lg border border-border bg-muted/30 flex items-center justify-between" data-testid={`balance-${cat.id}`}>
                          <div>
                            <p className="font-medium">{cat.name_sw}</p>
                            <p className="text-sm text-muted-foreground">{cat.name_en}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-2xl font-bold font-heading">{balance?.count || 0}</span>
                            <Button variant="ghost" size="icon" onClick={function() {
                              handleOpenDialog(balance || { 
                                location_id: parseInt(selectedLocation),
                                species: speciesKey,
                                category_id: cat.id,
                                count: 0,
                                period_start: new Date().toISOString().split('T')[0]
                              });
                            }} data-testid={`edit-balance-${cat.id}`}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          );
        })}
      </Tabs>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-heading">
              {formData.id ? 'Edit Opening Balance' : 'Add Opening Balance'}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>Location</Label>
              <Select value={formData.location_id} onValueChange={function(v) { setFormData({ ...formData, location_id: v }); }} disabled={!!formData.id}>
                <SelectTrigger data-testid="dialog-location">
                  <SelectValue placeholder="Select location" />
                </SelectTrigger>
                <SelectContent>
                  {locations.map(function(loc) {
                    return <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Species</Label>
              <Select value={formData.species} onValueChange={function(v) { setFormData({ ...formData, species: v, category_id: '' }); }} disabled={!!formData.id}>
                <SelectTrigger data-testid="dialog-species">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(SPECIES_CONFIG).map(function([key, config]) {
                    return <SelectItem key={key} value={key}>{config.label}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Category</Label>
              <Select value={formData.category_id} onValueChange={function(v) { setFormData({ ...formData, category_id: v }); }} disabled={!!formData.id}>
                <SelectTrigger data-testid="dialog-category">
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {speciesCategories.map(function(cat) {
                    return <SelectItem key={cat.id} value={cat.id.toString()}>{cat.name_sw} ({cat.name_en})</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Count</Label>
              <Input
                type="number"
                min="0"
                value={formData.count}
                onChange={function(e) { setFormData({ ...formData, count: e.target.value }); }}
                data-testid="dialog-count"
              />
            </div>

            {!formData.id && (
              <div className="space-y-2">
                <Label>Period Start Date</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start gap-2">
                      <CalendarBlank className="h-4 w-4" />
                      {format(formData.period_start, 'PPP')}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={formData.period_start}
                      onSelect={function(date) { if (date) setFormData({ ...formData, period_start: date }); }}
                    />
                  </PopoverContent>
                </Popover>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4">
              <Button type="button" variant="outline" onClick={function() { setDialogOpen(false); }}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving} data-testid="save-balance-btn">
                {saving ? 'Saving...' : 'Save'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default OpeningBalances;
