import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getDailyLogs, getLocations } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import DateRangePicker, { lastDaysRange } from '../components/DateRangePicker';
import { Skeleton } from '../components/ui/skeleton';
import { CalendarBlank, Plus, Lock, MapPin, Funnel } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { EVENT_TYPES, formatDate } from '../lib/utils';
import { format } from 'date-fns';

const DailyLogs = () => {
  const [logs, setLogs] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    location_id: '',
    start_date: lastDaysRange(30).from,
    end_date: lastDaysRange(30).to
  });
  const { isDataEntry } = useAuth();

  useEffect(() => {
    loadLocations();
  }, []);

  useEffect(() => {
    loadLogs();
  }, [filters]);

  const loadLocations = async () => {
    try {
      const response = await getLocations();
      setLocations(response.data);
    } catch (error) {
      console.error('Failed to load locations');
    }
  };

  const loadLogs = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.location_id) params.location_id = filters.location_id;
      if (filters.start_date) params.start_date = format(filters.start_date, 'yyyy-MM-dd');
      if (filters.end_date) params.end_date = format(filters.end_date, 'yyyy-MM-dd');
      
      const response = await getDailyLogs(params);
      setLogs(response.data);
    } catch (error) {
      toast.error('Failed to load daily logs');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="daily-logs-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold">Daily Logs</h1>
          <p className="text-muted-foreground mt-1">View and manage daily stock records</p>
        </div>
        {isDataEntry && (
          <Link to="/daily-logs/new">
            <Button className="gap-2" data-testid="new-daily-log-btn">
              <Plus className="h-4 w-4" />
              New Daily Log
            </Button>
          </Link>
        )}
      </div>

      {/* Filters */}
      <Card className="border-border/60">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Funnel className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Filters:</span>
            </div>
            
            <Select 
              value={filters.location_id || "all"} 
              onValueChange={(v) => setFilters({ ...filters, location_id: v === "all" ? "" : v })}
            >
              <SelectTrigger className="w-[180px]" data-testid="location-filter">
                <SelectValue placeholder="All Locations" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Locations</SelectItem>
                {locations.map(loc => (
                  <SelectItem key={loc.id} value={loc.id.toString()}>{loc.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <DateRangePicker
              clearable
              value={filters.start_date && filters.end_date ? { from: filters.start_date, to: filters.end_date } : null}
              onChange={(range) => setFilters({ ...filters, start_date: range ? range.from : null, end_date: range ? range.to : null })}
            />

            {(filters.location_id || filters.start_date || filters.end_date) && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setFilters({ location_id: '', start_date: null, end_date: null })}
              >
                Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Logs List */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : logs.length > 0 ? (
        <div className="space-y-4">
          {logs.map((log) => (
            <Card key={log.id} className="border-border/60" data-testid={`log-card-${log.id}`}>
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                      <CalendarBlank className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-heading font-semibold text-lg">
                          {formatDate(log.log_date)}
                        </p>
                        {log.is_locked && (
                          <Lock className="h-4 w-4 text-success" weight="fill" />
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <MapPin className="h-4 w-4" />
                        {log.location_name}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <div className="text-right hidden sm:block">
                      {log.has_events ? (
                        <Badge variant="secondary" className="text-base">
                          {log.events?.length || 0} events
                        </Badge>
                      ) : (
                        <Badge variant="outline">No events</Badge>
                      )}
                    </div>
                    <Link to={`/daily-logs/${log.id}`}>
                      <Button variant="outline" data-testid={`view-log-${log.id}`}>View</Button>
                    </Link>
                  </div>
                </div>

                {log.events && log.events.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-border flex flex-wrap gap-2">
                    {log.events.slice(0, 6).map((event, idx) => {
                      const eventConfig = EVENT_TYPES[event.event_type];
                      return (
                        <Badge key={idx} className={eventConfig?.color}>
                          {eventConfig?.label}: {event.count}
                        </Badge>
                      );
                    })}
                    {log.events.length > 6 && (
                      <Badge variant="outline">+{log.events.length - 6} more</Badge>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="border-border/60">
          <CardContent className="py-12 text-center">
            <CalendarBlank className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
            <p className="text-muted-foreground mb-4">No daily logs found</p>
            {isDataEntry && (
              <Link to="/daily-logs/new">
                <Button className="gap-2">
                  <Plus className="h-4 w-4" />
                  Create First Log
                </Button>
              </Link>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default DailyLogs;
