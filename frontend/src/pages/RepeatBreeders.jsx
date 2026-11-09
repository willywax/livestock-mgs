import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getLocations, listRepeatBreeders } from '../lib/api';
import { formatDate } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Skeleton } from '../components/ui/skeleton';

export default function RepeatBreeders() {
  const [params, setParams] = useSearchParams();
  const location = params.get('location_id') || 'all';
  const species = params.get('species') || 'all';
  const [locations, setLocations] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [locationError, setLocationError] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setLocationError(false);
    getLocations().then(({ data }) => { if (active) setLocations(data); })
      .catch(() => { if (active) setLocationError(true); });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    listRepeatBreeders({ location_id: location === 'all' ? undefined : location,
      species: species === 'all' ? undefined : species })
      .then(({ data }) => { if (active) setRows([...data].sort((a, b) => b.services_without_conception - a.services_without_conception)); })
      .catch(() => { if (active) setError('Could not load repeat breeders. Please try again.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [location, species, refresh]);

  const filter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value === 'all') next.delete(key); else next.set(key, value);
    setParams(next);
  };

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost"><Link to="/animals">Back to animals</Link></Button>
      <h1 className="font-heading text-3xl font-bold">Repeat breeders</h1>
      <div className="flex flex-wrap gap-3">
        <Select value={location} onValueChange={(value) => filter('location_id', value)}>
          <SelectTrigger className="w-48" aria-label="Location"><SelectValue placeholder="All locations" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All locations</SelectItem>
            {locations.map((loc) => <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={species} onValueChange={(value) => filter('species', value)}>
          <SelectTrigger className="w-40" aria-label="Species"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="all">All species</SelectItem><SelectItem value="cattle">Cattle</SelectItem>
            <SelectItem value="sheep">Sheep</SelectItem><SelectItem value="goat">Goats</SelectItem></SelectContent>
        </Select>
        <Button variant="outline" onClick={() => setRefresh((value) => value + 1)}>Refresh</Button>
      </div>
      {locationError && <p role="alert" className="text-sm text-red-600">Could not load locations. Use Refresh to retry.</p>}
      {loading ? <Skeleton className="h-40" /> : error ? <p role="alert" className="text-red-600">{error}</p> : rows.length === 0 ? (
        <p className="text-muted-foreground">No repeat breeders above threshold.</p>
      ) : (
        <Card><CardContent className="p-0"><Table>
          <TableHeader><TableRow>{['Tag', 'Species', 'Farm', 'Services without conception', 'Last PD', 'Status'].map((label) =>
            <TableHead key={label}>{label}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{rows.map((row, index) => <TableRow key={`${row.species}-${row.location_name}-${row.tag_number}-${index}`}>
            <TableCell className="font-mono font-medium">{row.tag_number}</TableCell>
            <TableCell className="capitalize">{row.species}</TableCell><TableCell>{row.location_name}</TableCell>
            <TableCell>{row.services_without_conception}</TableCell>
            <TableCell>{row.last_pd_date ? formatDate(row.last_pd_date) : '—'}</TableCell>
            <TableCell className="capitalize">{row.reproductive_status || 'unknown'}</TableCell>
          </TableRow>)}</TableBody>
        </Table></CardContent></Card>
      )}
    </div>
  );
}
