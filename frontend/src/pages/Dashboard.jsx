import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getDashboard, getLocations, getLastEvents, getLastVaccinations } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Cow, TrendUp, TrendDown, Plus, Heartbeat, Skull, Baby, MapPin, FirstAidKit, WarningCircle, Syringe } from '@phosphor-icons/react';
import { SPECIES_CONFIG, formatDate } from '../lib/utils';
import { useAuth } from '../context/AuthContext';

function SpeciesCard({ species, total, color }) {
  const config = SPECIES_CONFIG[species];
  return (
    <Card className="border-border/60 overflow-hidden" data-testid={`species-${species}-card`}>
      <div className="h-2" style={{ backgroundColor: color }} />
      <CardContent className="p-6">
        <div className="flex items-center gap-4">
          <div className="h-14 w-14 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${color}15` }}>
            <Cow className="h-8 w-8" weight="fill" style={{ color: color }} />
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">{config?.label || species}</p>
            <p className="text-3xl font-bold font-heading">{total}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CategoryItem({ cat }) {
  return (
    <div className="p-3 rounded-lg bg-muted/50 text-center">
      <p className="text-xs text-muted-foreground truncate">{cat.category_name_sw}</p>
      <p className="text-lg font-bold font-heading mt-1">{cat.count}</p>
    </div>
  );
}

function SpeciesCategorySection({ speciesData }) {
  const config = SPECIES_CONFIG[speciesData.species];
  const cats = speciesData.categories || [];
  
  if (cats.length === 0) return null;
  
  const categoryItems = [];
  for (let i = 0; i < cats.length; i++) {
    categoryItems.push(<CategoryItem key={cats[i].category_id} cat={cats[i]} />);
  }
  
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
        <h4 className="font-semibold text-sm">{config?.label || speciesData.species}</h4>
        <Badge variant="outline" className="ml-auto">{speciesData.total} total</Badge>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
        {categoryItems}
      </div>
    </div>
  );
}

function HerdPerformanceCard({ performance }) {
  const config = SPECIES_CONFIG[performance.species];
  const mortalityHigh = performance.mortality_rate > 5;
  const calvingLow = performance.calving_rate < 60 && performance.breeding_females > 0;
  
  return (
    <Card className="border-border/60 overflow-hidden" data-testid={`performance-${performance.species}`}>
      <div className="h-2" style={{ backgroundColor: performance.color }} />
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="font-heading text-base flex items-center gap-2">
            <div className="h-3 w-3 rounded-full" style={{ backgroundColor: performance.color }} />
            {config?.label || performance.species}
          </CardTitle>
          <Badge variant="outline" className="text-xs">{performance.total_stock}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div className={`p-2 rounded-lg ${calvingLow ? 'bg-amber-50' : 'bg-green-50'}`}>
            <div className="flex items-center gap-1 mb-1">
              <Baby className={`h-3 w-3 ${calvingLow ? 'text-amber-600' : 'text-green-600'}`} weight="fill" />
              <span className={`text-xs ${calvingLow ? 'text-amber-700' : 'text-green-700'}`}>
                Calving
              </span>
            </div>
            <p className={`text-lg font-bold ${calvingLow ? 'text-amber-800' : 'text-green-800'}`}>
              {performance.calving_rate}%
            </p>
            <p className={`text-[11px] ${calvingLow ? 'text-amber-700' : 'text-green-700'}`}>
              {performance.births_30d}/{performance.breeding_females}
            </p>
          </div>
          
          <div className={`p-2 rounded-lg ${mortalityHigh ? 'bg-red-50' : 'bg-slate-50'}`}>
            <div className="flex items-center gap-1 mb-1">
              <Skull className={`h-3 w-3 ${mortalityHigh ? 'text-red-600' : 'text-slate-600'}`} weight="fill" />
              <span className={`text-xs ${mortalityHigh ? 'text-red-700' : 'text-slate-700'}`}>Mortality</span>
            </div>
            <p className={`text-lg font-bold ${mortalityHigh ? 'text-red-800' : 'text-slate-800'}`}>
              {performance.mortality_rate}%
            </p>
          </div>
        </div>
        
        <div className="text-xs text-muted-foreground flex justify-between pt-2 border-t">
          <span>Births: {performance.births_30d}</span>
          <span>Deaths: {performance.deaths_30d}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function NetChangeCard({ netChange }) {
  const config = SPECIES_CONFIG[netChange.species];
  const isPositive = netChange.net_change >= 0;
  
  return (
    <div className="p-4 rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
          <span className="font-medium text-sm">{config?.label || netChange.species}</span>
        </div>
        <div className={`flex items-center gap-1 ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {isPositive ? <TrendUp className="h-4 w-4" /> : <TrendDown className="h-4 w-4" />}
          <span className="font-bold text-lg">{isPositive ? '+' : ''}{netChange.net_change}</span>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2 text-xs">
        <div className="text-center p-1 rounded bg-green-50">
          <p className="text-green-700">Births</p>
          <p className="font-bold text-green-800">+{netChange.births}</p>
        </div>
        <div className="text-center p-1 rounded bg-blue-50">
          <p className="text-blue-700">Bought</p>
          <p className="font-bold text-blue-800">+{netChange.bought}</p>
        </div>
        <div className="text-center p-1 rounded bg-red-50">
          <p className="text-red-700">Deaths</p>
          <p className="font-bold text-red-800">-{netChange.deaths}</p>
        </div>
        <div className="text-center p-1 rounded bg-amber-50">
          <p className="text-amber-700">Sold</p>
          <p className="font-bold text-amber-800">-{netChange.sold}</p>
        </div>
      </div>
    </div>
  );
}

function LocationItem({ location }) {
  return (
    <Link to={`/locations/${location.location_id}`} className="block">
      <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50 hover:bg-muted transition-colors">
        <div>
          <p className="font-medium">{location.location_name}</p>
          <div className="flex gap-3 mt-1">
            <span className="text-xs" style={{ color: SPECIES_CONFIG.cattle?.color }}>Cattle: {location.cattle}</span>
            <span className="text-xs" style={{ color: SPECIES_CONFIG.sheep?.color }}>Sheep: {location.sheep}</span>
            <span className="text-xs" style={{ color: SPECIES_CONFIG.goat?.color }}>Goat: {location.goat}</span>
          </div>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold font-heading">{location.total}</p>
          <p className="text-xs text-muted-foreground">Total</p>
        </div>
      </div>
    </Link>
  );
}

function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [locations, setLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState('all');
  const [selectedPeriod, setSelectedPeriod] = useState('30');
  const [healthSummaries, setHealthSummaries] = useState([]);
  const [vaccinationSummaries, setVaccinationSummaries] = useState([]);
  const { isDataEntry } = useAuth();

  useEffect(function() {
    loadLocations();
  }, []);

  useEffect(function() {
    loadDashboard();
  }, [selectedLocation, selectedPeriod]);

  async function loadLocations() {
    try {
      const response = await getLocations();
      setLocations(response.data);
    } catch (error) {
      console.error('Failed to load locations');
    }
    try {
      const [healthRes, vacRes] = await Promise.all([getLastEvents(), getLastVaccinations()]);
      setHealthSummaries(healthRes.data);
      setVaccinationSummaries(vacRes.data);
    } catch {
      // Health data is non-critical
    }
  }

  async function loadDashboard() {
    setLoading(true);
    try {
      const params = {};
      if (selectedLocation && selectedLocation !== 'all') {
        params.location_id = selectedLocation;
      }
      const periodDays = parseInt(selectedPeriod, 10);
      if (!Number.isNaN(periodDays)) {
        params.period_days = periodDays;
      }
      const response = await getDashboard(params);
      setData(response.data);
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    } finally {
      setLoading(false);
    }
  }

  const isInitialLoading = loading && !data;
  const isRefreshing = loading && data;

  if (isInitialLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    );
  }

  const speciesTotals = data?.species_totals || [];
  const speciesCategoryTotals = data?.species_category_totals || [];
  const locationTotals = data?.location_totals || [];
  const herdPerformance = data?.herd_performance || [];
  const netChanges = data?.net_changes || [];
  const periodDays = parseInt(selectedPeriod, 10) || 30;
  
  // Build arrays to avoid nested maps
  const speciesCards = [];
  for (let i = 0; i < speciesTotals.length; i++) {
    const s = speciesTotals[i];
    speciesCards.push(<SpeciesCard key={s.species} species={s.species} total={s.total} color={s.color} />);
  }
  
  const perfCards = [];
  for (let i = 0; i < herdPerformance.length; i++) {
    perfCards.push(<HerdPerformanceCard key={herdPerformance[i].species} performance={herdPerformance[i]} />);
  }
  
  const netCards = [];
  for (let i = 0; i < netChanges.length; i++) {
    netCards.push(<NetChangeCard key={netChanges[i].species} netChange={netChanges[i]} />);
  }
  
  const catSections = [];
  for (let i = 0; i < speciesCategoryTotals.length; i++) {
    const sct = speciesCategoryTotals[i];
    if (sct.categories && sct.categories.length > 0) {
      catSections.push(<SpeciesCategorySection key={sct.species} speciesData={sct} />);
    }
  }
  
  const locationItems = [];
  for (let i = 0; i < locationTotals.length; i++) {
    if (locationTotals[i].total > 0) {
      locationItems.push(<LocationItem key={locationTotals[i].location_id} location={locationTotals[i]} />);
    }
  }
  
  const locationOptions = [];
  for (let i = 0; i < locations.length; i++) {
    locationOptions.push(
      <SelectItem key={locations[i].id} value={locations[i].id.toString()}>
        {locations[i].name}
      </SelectItem>
    );
  }

  return (
    <div className="space-y-8" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl md:text-4xl font-bold text-foreground">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            {formatDate(new Date())} - Herd Overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
            <SelectTrigger className="w-[180px]" data-testid="period-filter">
              <SelectValue placeholder="Last 30 Days" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 Days</SelectItem>
              <SelectItem value="30">Last 30 Days</SelectItem>
              <SelectItem value="90">Last 90 Days</SelectItem>
              <SelectItem value="180">Last 180 Days</SelectItem>
              <SelectItem value="365">Last 365 Days</SelectItem>
            </SelectContent>
          </Select>
          <Select value={selectedLocation} onValueChange={setSelectedLocation}>
            <SelectTrigger className="w-[200px]" data-testid="location-filter">
              <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
              <SelectValue placeholder="All Locations" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Locations</SelectItem>
              {locationOptions}
            </SelectContent>
          </Select>
          {isDataEntry && (
            <Link to="/daily-logs/new">
              <Button className="gap-2" data-testid="new-daily-log-btn">
                <Plus className="h-4 w-4" />
                New Daily Log
              </Button>
            </Link>
          )}
        </div>
      </div>

      {data?.selected_location_name && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <MapPin className="h-4 w-4" />
          <span>Showing data for: <strong className="text-foreground">{data.selected_location_name}</strong></span>
        </div>
      )}

      {isRefreshing ? (
        <div className="space-y-6" aria-live="polite">
          <Skeleton className="h-6 w-64" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
          </div>
          <Skeleton className="h-48" />
          <Skeleton className="h-28" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Skeleton className="h-36" />
            <Skeleton className="h-36" />
            <Skeleton className="h-36" />
            <Skeleton className="h-36" />
          </div>
        </div>
      ) : (
        <>
          <div>
            <h2 className="font-heading text-xl font-semibold mb-4 flex items-center gap-2">
              <Heartbeat className="h-5 w-5 text-primary" />
              Herd Performance (Last {periodDays} Days)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {perfCards}
            </div>
          </div>

          {netCards.length > 0 && (
            <Card className="border-border/60" data-testid="net-changes-card">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <TrendUp className="h-5 w-5 text-primary" />
                  Net Change in Animals (Last {periodDays} Days)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {netCards}
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="border-border/60" data-testid="total-animals-card">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Animals</p>
                  <p className="text-4xl font-bold font-heading mt-1">{data?.total_animals || 0}</p>
                </div>
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <Cow className="h-8 w-8 text-primary" weight="fill" />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {speciesCards}
          </div>

          {catSections.length > 0 && (
            <Card className="border-border/60" data-testid="category-breakdown-card">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <Cow className="h-5 w-5 text-primary" />
                  Summary by Category
                </CardTitle>
              </CardHeader>
              <CardContent>
                {catSections}
              </CardContent>
            </Card>
          )}

          {selectedLocation === 'all' && locationItems.length > 0 && (
            <Card className="border-border/60" data-testid="location-totals-card">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <MapPin className="h-5 w-5 text-primary" />
                  Stock by Location
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {locationItems}
                </div>
              </CardContent>
            </Card>
          )}

          {healthSummaries.length > 0 && (
            <Card className="border-border/60">
              <CardHeader>
                <CardTitle className="font-heading flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <FirstAidKit className="h-5 w-5 text-primary" />
                    Farm Health
                  </span>
                  <Link to="/farm-health" className="text-xs font-normal text-muted-foreground hover:text-primary transition-colors">
                    View all →
                  </Link>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {healthSummaries.filter(function(s) { return s.is_overdue; }).length > 0 && (
                  <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">
                    <WarningCircle className="h-4 w-4 text-red-600 flex-shrink-0" weight="fill" />
                    <p className="text-xs text-red-700 font-medium">
                      {healthSummaries.filter(function(s) { return s.is_overdue; }).length} overdue health intervention(s)
                    </p>
                  </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                  {[...healthSummaries].sort(function(a, b) {
                    function rank(s) {
                      if (s.is_overdue) return 0;
                      if (!s.next_due_date) return 3;
                      const days = Math.ceil((new Date(s.next_due_date) - new Date()) / (1000 * 60 * 60 * 24));
                      return days <= 7 ? 1 : 2;
                    }
                    return rank(a) - rank(b);
                  }).slice(0, 8).map(function(s, i) {
                    return (
                      <div key={i} className={`p-2 rounded-lg border text-xs ${s.is_overdue ? 'border-red-200 bg-red-50/40' : 'border-border bg-muted/30'}`}>
                        <p className="font-medium text-foreground truncate capitalize">{s.event_type}</p>
                        <p className="text-muted-foreground truncate">{s.location_name}{s.species ? ` · ${s.species}` : ''}</p>
                        {s.is_overdue ? (
                          <p className="text-red-600 font-semibold mt-0.5">
                            {s.days_overdue ? `${s.days_overdue}d overdue` : 'Never done'}
                          </p>
                        ) : s.next_due_date ? (
                          <p className="text-green-600 mt-0.5">Due {formatDate(s.next_due_date)}</p>
                        ) : (
                          <p className="text-muted-foreground mt-0.5">{s.last_date ? formatDate(s.last_date) : '—'}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {vaccinationSummaries.length > 0 && (
            <Card className="border-border/60">
              <CardHeader>
                <CardTitle className="font-heading flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Syringe className="h-5 w-5 text-primary" />
                    Vaccination Status
                  </span>
                  <Link to="/farm-health?event_type=VACCINATION" className="text-xs font-normal text-muted-foreground hover:text-primary transition-colors">
                    View all →
                  </Link>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-muted-foreground border-b">
                        <th className="text-left font-medium pb-2 pr-3">Farm</th>
                        <th className="text-left font-medium pb-2 pr-3">Species</th>
                        <th className="text-left font-medium pb-2 pr-3">Vaccine</th>
                        <th className="text-left font-medium pb-2 pr-3">Last done</th>
                        <th className="text-left font-medium pb-2 pr-3">Next due</th>
                        <th className="text-left font-medium pb-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...vaccinationSummaries].sort(function(a, b) {
                        function rank(s) {
                          if (s.is_overdue) return 0;
                          if (!s.next_due_date) return 3;
                          const days = Math.ceil((new Date(s.next_due_date) - new Date()) / (1000 * 60 * 60 * 24));
                          return days <= 30 ? 1 : 2;
                        }
                        return rank(a) - rank(b);
                      }).map(function(s, i) {
                        let dotColor = 'bg-gray-300';
                        let statusText = 'No schedule';
                        if (s.is_overdue) { dotColor = 'bg-red-500'; statusText = s.days_since ? `${s.days_since}d overdue` : 'Overdue'; }
                        else if (s.next_due_date) {
                          const days = Math.ceil((new Date(s.next_due_date) - new Date()) / (1000 * 60 * 60 * 24));
                          if (days <= 30) { dotColor = 'bg-amber-400'; statusText = `Due in ${days}d`; }
                          else { dotColor = 'bg-green-500'; statusText = formatDate(s.next_due_date); }
                        }
                        return (
                          <tr key={i} className="border-b border-border/50 last:border-0">
                            <td className="py-2 pr-3 font-medium text-foreground">{s.location_name}</td>
                            <td className="py-2 pr-3 capitalize text-muted-foreground">{s.species}</td>
                            <td className="py-2 pr-3 text-foreground">{s.vaccine_type_name}</td>
                            <td className="py-2 pr-3 text-muted-foreground">{s.last_event_date ? formatDate(s.last_event_date) : '—'}</td>
                            <td className="py-2 pr-3 text-muted-foreground">{s.next_due_date ? formatDate(s.next_due_date) : '—'}</td>
                            <td className="py-2">
                              <span className="flex items-center gap-1.5">
                                <span className={`h-2 w-2 rounded-full flex-shrink-0 ${dotColor}`} />
                                <span className={s.is_overdue ? 'text-red-600 font-semibold' : 'text-muted-foreground'}>{statusText}</span>
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {data?.total_animals === 0 && (
            <Card className="border-border/60">
              <CardContent className="py-12 text-center">
                <Cow className="h-16 w-16 mx-auto mb-4 text-muted-foreground/30" />
                <p className="text-lg font-medium text-muted-foreground mb-2">No livestock data yet</p>
                <p className="text-sm text-muted-foreground mb-4">Start by adding locations and opening balances</p>
                <div className="flex gap-2 justify-center">
                  <Link to="/locations">
                    <Button variant="outline">Add Locations</Button>
                  </Link>
                  <Link to="/opening-balances">
                    <Button>Set Opening Balances</Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

export default Dashboard;
