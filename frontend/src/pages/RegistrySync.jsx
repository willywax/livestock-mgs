import React, { useState, useEffect, useCallback } from 'react';
import {
  getUntaggedCalves,
  assignRegistryTag,
  getRegistrySyncReport,
  retryRegistrySyncRow,
} from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/table';
import RegistryTagPicker from '../components/RegistryTagPicker';
import { WarningCircle, ArrowClockwise, Tag as TagIcon } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { formatDate, formatDateTime, SPECIES_CONFIG } from '../lib/utils';

const STATE_BADGE = {
  CONFLICT: 'bg-amber-100 text-amber-800',
  FAILED: 'bg-red-100 text-red-800',
  PENDING: 'bg-blue-100 text-blue-800',
  SENT: 'bg-green-100 text-green-800',
};

const MISMATCH_LABEL = {
  local_no_registry: 'ShambaManager only',
  registry_no_local: 'Registry only',
  status_mismatch: 'Status mismatch',
};

function UntaggedCalvesPanel() {
  const [calves, setCalves] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assigningId, setAssigningId] = useState(null);

  const loadCalves = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getUntaggedCalves();
      setCalves(res.data);
    } catch (error) {
      toast.error('Failed to load untagged calves');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadCalves(); }, [loadCalves]);

  async function handleAssign(calf, tag) {
    if (!tag) return;
    setAssigningId(calf.id);
    try {
      const res = await assignRegistryTag(calf.id, tag.tag_id);
      toast.success(`Tag ${tag.tag_id} assigned to ${calf.tag_number}`);
      if (res.data?.registry_sync_warning) {
        toast.warning(res.data.registry_sync_warning);
      }
      setCalves((prev) => prev.filter((c) => c.id !== calf.id));
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to assign registry tag');
    } finally {
      setAssigningId(null);
    }
  }

  if (loading) {
    return <Skeleton className="h-64" />;
  }

  if (calves.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No calves are waiting on a registry tag right now.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tag Number</TableHead>
            <TableHead>Species</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Location</TableHead>
            <TableHead>Born</TableHead>
            <TableHead>Days Old</TableHead>
            <TableHead className="min-w-[280px]">Assign Registry Tag</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {calves.map((calf) => (
            <TableRow key={calf.id} data-testid={`untagged-calf-${calf.id}`}>
              <TableCell className="font-mono">{calf.tag_number}</TableCell>
              <TableCell>{SPECIES_CONFIG[calf.species]?.label || calf.species}</TableCell>
              <TableCell>{calf.category_name_sw || '—'}</TableCell>
              <TableCell>{calf.location_name || '—'}</TableCell>
              <TableCell>{formatDate(calf.birth_date)}</TableCell>
              <TableCell>{calf.days_since_birth ?? '—'}</TableCell>
              <TableCell>
                <RegistryTagPicker
                  species={calf.species}
                  location={calf.location_name}
                  value={null}
                  disabled={assigningId === calf.id}
                  placeholder={assigningId === calf.id ? 'Assigning…' : 'Select this calf in the Registry'}
                  onChange={(tag) => handleAssign(calf, tag)}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function SyncIssuesPanel() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retryingId, setRetryingId] = useState(null);

  const loadReport = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRegistrySyncReport();
      setReport(res.data);
    } catch (error) {
      toast.error('Failed to load Registry sync report');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadReport(); }, [loadReport]);

  async function handleRetry(row) {
    setRetryingId(row.id);
    try {
      await retryRegistrySyncRow(row.id);
      toast.success(`Tag ${row.tag_id} re-queued for retry`);
      setReport((prev) => ({
        ...prev,
        outbox_issues: prev.outbox_issues.filter((r) => r.id !== row.id),
      }));
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to retry');
    } finally {
      setRetryingId(null);
    }
  }

  if (loading) {
    return <Skeleton className="h-64" />;
  }

  if (!report) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Since {formatDate(report.since)} · Generated {formatDateTime(report.generated_at)}
        </p>
        <Button variant="outline" size="sm" className="gap-2" onClick={loadReport}>
          <ArrowClockwise className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {report.reconcile_unavailable && (
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5">
          <WarningCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-destructive">Registry reconciliation is unreachable</p>
            <p className="text-sm text-muted-foreground mt-1">
              {report.reconcile_error || 'Could not cross-check against the Herd Tag Registry.'}
              {' '}Outbox issues below are still accurate — they come from ShambaManager's own records.
            </p>
          </div>
        </div>
      )}

      <div>
        <h3 className="font-heading font-semibold mb-3">Outbox Issues</h3>
        {report.outbox_issues.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">No stuck sync rows — everything's landed.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tag ID</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Intended Status</TableHead>
                  <TableHead>Previous Status</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Attempts</TableHead>
                  <TableHead>Last Error</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.outbox_issues.map((row) => (
                  <TableRow key={row.id} data-testid={`outbox-issue-${row.id}`}>
                    <TableCell className="font-mono">{row.tag_id}</TableCell>
                    <TableCell>{row.action}</TableCell>
                    <TableCell>{row.intended_status || '—'}</TableCell>
                    <TableCell>{row.previous_status || '—'}</TableCell>
                    <TableCell>
                      <Badge className={STATE_BADGE[row.state]}>{row.state}</Badge>
                    </TableCell>
                    <TableCell>{row.attempts}</TableCell>
                    <TableCell className="max-w-[240px] truncate text-muted-foreground" title={row.last_error || ''}>
                      {row.last_error || '—'}
                    </TableCell>
                    <TableCell>{formatDateTime(row.created_at)}</TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-2"
                        disabled={retryingId === row.id}
                        onClick={() => handleRetry(row)}
                        data-testid={`retry-${row.id}`}
                      >
                        <ArrowClockwise className="h-3.5 w-3.5" />
                        {retryingId === row.id ? 'Retrying…' : 'Retry'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div>
        <h3 className="font-heading font-semibold mb-3">Reconciliation Mismatches</h3>
        {report.reconcile_unavailable ? (
          <p className="text-sm text-muted-foreground py-4">Unavailable — see warning above.</p>
        ) : report.reconcile_mismatches.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">ShambaManager and the Registry agree on everything checked.</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tag ID</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Local Status</TableHead>
                  <TableHead>Registry Status</TableHead>
                  <TableHead>Detail</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.reconcile_mismatches.map((m, idx) => (
                  <TableRow key={`${m.tag_id}-${idx}`}>
                    <TableCell className="font-mono">{m.tag_id}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{MISMATCH_LABEL[m.kind] || m.kind}</Badge>
                    </TableCell>
                    <TableCell>{m.local_status || '—'}</TableCell>
                    <TableCell>{m.registry_status || '—'}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{m.detail}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}

function RegistrySync() {
  return (
    <div className="space-y-6" data-testid="registry-sync-page">
      <div>
        <h1 className="font-heading text-3xl font-bold flex items-center gap-2">
          <TagIcon className="h-7 w-7 text-primary" />
          Registry Sync
        </h1>
        <p className="text-muted-foreground mt-1">
          Tag newly-born calves and keep ShambaManager in step with the Herd Tag Registry
        </p>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="font-heading">Registry Status</CardTitle>
          <CardDescription>
            Untagged calves waiting to be registered, and any sync issues that need attention
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="untagged">
            <TabsList>
              <TabsTrigger value="untagged" data-testid="tab-untagged-calves">Untagged Calves</TabsTrigger>
              <TabsTrigger value="issues" data-testid="tab-sync-issues">Sync Issues</TabsTrigger>
            </TabsList>
            <TabsContent value="untagged">
              <UntaggedCalvesPanel />
            </TabsContent>
            <TabsContent value="issues">
              <SyncIssuesPanel />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}

export default RegistrySync;
