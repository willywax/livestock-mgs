import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getLocation, getStockLevels, getDailyLogs } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Skeleton } from '../components/ui/skeleton';
import { 
  MapPin, 
  ArrowLeft, 
  Cow, 
  CalendarBlank,
  Plus,
  Lock,
  CheckCircle
} from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { SPECIES_CONFIG, EVENT_TYPES, formatDate } from '../lib/utils';

const LocationDetail = () => {
  const { id } = useParams();
  const [location, setLocation] = useState(null);
  const [stockLevels, setStockLevels] = useState([]);
  const [dailyLogs, setDailyLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const { isDataEntry } = useAuth();

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      const [locRes, stockRes, logsRes] = await Promise.all([
        getLocation(id),
        getStockLevels({ location_id: id }),
        getDailyLogs({ location_id: id })
      ]);
      setLocation(locRes.data);
      setStockLevels(stockRes.data);
      setDailyLogs(logsRes.data);
    } catch (error) {
      toast.error('Failed to load location data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!location) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Location not found</p>
        <Link to="/locations">
          <Button variant="link">Back to Locations</Button>
        </Link>
      </div>
    );
  }

  // Group stock by species
  const stockBySpecies = stockLevels.reduce((acc, item) => {
    if (!acc[item.species]) {
      acc[item.species] = [];
    }
    acc[item.species].push(item);
    return acc;
  }, {});

  const totalStock = stockLevels.reduce((sum, item) => sum + item.current_count, 0);

  return (
    <div className="space-y-6" data-testid="location-detail-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link to="/locations">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <MapPin className="h-6 w-6 text-primary" weight="fill" />
              <h1 className="font-heading text-3xl font-bold">{location.name}</h1>
            </div>
            {location.description && (
              <p className="text-muted-foreground mt-1">{location.description}</p>
            )}
          </div>
        </div>
        {isDataEntry && (
          <Link to={`/daily-logs/new?location=${id}`}>
            <Button className="gap-2" data-testid="new-log-btn">
              <Plus className="h-4 w-4" />
              New Daily Log
            </Button>
          </Link>
        )}
      </div>

      {/* Summary Card */}
      <Card className="border-border/60" data-testid="location-summary-card">
        <CardContent className="p-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <p className="text-sm text-muted-foreground">Total Stock</p>
              <p className="text-3xl font-bold font-heading">{totalStock}</p>
            </div>
            {Object.entries(SPECIES_CONFIG).map(([key, config]) => {
              const speciesStock = stockBySpecies[key] || [];
              const total = speciesStock.reduce((sum, s) => sum + s.current_count, 0);
              return (
                <div key={key}>
                  <p className="text-sm text-muted-foreground">{config.label.split(' ')[0]}</p>
                  <p className="text-3xl font-bold font-heading" style={{ color: config.color }}>
                    {total}
                  </p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="stock" className="space-y-6">
        <TabsList>
          <TabsTrigger value="stock" data-testid="stock-tab">Stock Levels</TabsTrigger>
          <TabsTrigger value="logs" data-testid="logs-tab">Daily Logs</TabsTrigger>
        </TabsList>

        {/* Stock Levels Tab */}
        <TabsContent value="stock" className="space-y-6">
          {Object.entries(SPECIES_CONFIG).map(([speciesKey, config]) => {
            const speciesStock = stockBySpecies[speciesKey] || [];
            const total = speciesStock.reduce((sum, s) => sum + s.current_count, 0);
            
            if (speciesStock.length === 0) return null;
            
            return (
              <Card key={speciesKey} className="border-border/60" data-testid={`stock-${speciesKey}`}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="font-heading flex items-center gap-2">
                      <div 
                        className="h-4 w-4 rounded-full"
                        style={{ backgroundColor: config.color }}
                      />
                      {config.label}
                    </CardTitle>
                    <Badge variant="secondary" className="text-lg font-bold">
                      {total}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                    {speciesStock.map((item) => (
                      <div 
                        key={item.id}
                        className="p-4 rounded-lg bg-muted/50 text-center"
                      >
                        <p className="text-sm text-muted-foreground">{item.category_name_sw}</p>
                        <p className="text-2xl font-bold font-heading mt-1">{item.current_count}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
          
          {stockLevels.length === 0 && (
            <Card className="border-border/60">
              <CardContent className="py-12 text-center">
                <Cow className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                <p className="text-muted-foreground">No stock recorded yet</p>
                <Link to="/opening-balances">
                  <Button variant="link">Set Opening Balances</Button>
                </Link>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Daily Logs Tab */}
        <TabsContent value="logs" className="space-y-4">
          {dailyLogs.length > 0 ? (
            dailyLogs.map((log) => (
              <Card key={log.id} className="border-border/60" data-testid={`log-${log.id}`}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <CalendarBlank className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="font-medium">{formatDate(log.log_date)}</p>
                        <div className="flex items-center gap-2 mt-1">
                          {log.has_events ? (
                            <Badge variant="secondary">
                              {log.events?.length || 0} events
                            </Badge>
                          ) : (
                            <Badge variant="outline">No events</Badge>
                          )}
                          {log.is_locked && (
                            <Badge className="bg-green-100 text-green-800 gap-1">
                              <Lock className="h-3 w-3" />
                              Locked
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    <Link to={`/daily-logs/${log.id}`}>
                      <Button variant="outline" size="sm">View</Button>
                    </Link>
                  </div>
                  
                  {log.events && log.events.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-border flex flex-wrap gap-2">
                      {log.events.slice(0, 5).map((event, idx) => {
                        const eventConfig = EVENT_TYPES[event.event_type];
                        return (
                          <Badge key={idx} className={eventConfig?.color}>
                            {eventConfig?.label}: {event.count}
                          </Badge>
                        );
                      })}
                      {log.events.length > 5 && (
                        <Badge variant="outline">+{log.events.length - 5} more</Badge>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          ) : (
            <Card className="border-border/60">
              <CardContent className="py-12 text-center">
                <CalendarBlank className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                <p className="text-muted-foreground">No daily logs yet</p>
                {isDataEntry && (
                  <Link to={`/daily-logs/new?location=${id}`}>
                    <Button variant="link">Create First Log</Button>
                  </Link>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default LocationDetail;
