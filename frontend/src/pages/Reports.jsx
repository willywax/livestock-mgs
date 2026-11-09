import React, { useState, useEffect } from 'react';
import { getDailyReport, getRangeReport, getAnalyticsReport, getDetailedReport, getLocations } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import DateRangePicker from '../components/DateRangePicker';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { ChartBar, CalendarBlank, TrendUp, TrendDown, MapPin, MagnifyingGlass, Skull, CurrencyCircleDollar, Baby, ShoppingCart, Package, ArrowsDownUp, FirstAid, Clock, Warning } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { EVENT_TYPES, SPECIES_CONFIG, formatDate } from '../lib/utils';
import { format, subDays } from 'date-fns';

function AnalyticsCard({ speciesRate }) {
  const config = SPECIES_CONFIG[speciesRate.species];
  const mortalityHigh = speciesRate.mortality_rate > 5;
  const calvingLow = speciesRate.calving_rate < 60 && speciesRate.breeding_females > 0;
  const weaningLow = speciesRate.weaning_rate < 80 && speciesRate.births > 0;
  
  return (
    <Card className="border-border/60 overflow-hidden">
      <div className="h-2" style={{ backgroundColor: speciesRate.color }} />
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: speciesRate.color }} />
          <CardTitle className="font-heading text-base">{config?.label || speciesRate.species}</CardTitle>
          <Badge variant="outline" className="ml-auto text-xs">{speciesRate.total_stock}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2">
          <div className={`p-2 rounded-lg ${calvingLow ? 'bg-amber-50' : 'bg-green-50'}`}>
            <div className="flex items-center gap-1 mb-1">
              <Baby className={`h-3 w-3 ${calvingLow ? 'text-amber-600' : 'text-green-600'}`} weight="fill" />
              <span className={`text-xs ${calvingLow ? 'text-amber-700' : 'text-green-700'}`}>Calving</span>
            </div>
            <p className={`text-lg font-bold ${calvingLow ? 'text-amber-800' : 'text-green-800'}`}>
              {speciesRate.calving_rate}%
            </p>
          </div>
          <div className={`p-2 rounded-lg ${weaningLow ? 'bg-amber-50' : 'bg-teal-50'}`}>
            <div className="flex items-center gap-1 mb-1">
              <ArrowsDownUp className={`h-3 w-3 ${weaningLow ? 'text-amber-600' : 'text-teal-600'}`} weight="fill" />
              <span className={`text-xs ${weaningLow ? 'text-amber-700' : 'text-teal-700'}`}>Weaning</span>
            </div>
            <p className={`text-lg font-bold ${weaningLow ? 'text-amber-800' : 'text-teal-800'}`}>
              {speciesRate.weaning_rate}%
            </p>
          </div>
          <div className={`p-2 rounded-lg ${mortalityHigh ? 'bg-red-50' : 'bg-slate-50'}`}>
            <div className="flex items-center gap-1 mb-1">
              <Skull className={`h-3 w-3 ${mortalityHigh ? 'text-red-600' : 'text-slate-600'}`} weight="fill" />
              <span className={`text-xs ${mortalityHigh ? 'text-red-700' : 'text-slate-700'}`}>Mortality</span>
            </div>
            <p className={`text-lg font-bold ${mortalityHigh ? 'text-red-800' : 'text-slate-800'}`}>
              {speciesRate.mortality_rate}%
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 rounded-lg bg-blue-50 text-center">
            <span className="text-xs text-blue-700">Sold</span>
            <p className="font-bold text-blue-800">{speciesRate.sold}</p>
          </div>
          <div className="p-2 rounded-lg bg-purple-50 text-center">
            <span className="text-xs text-purple-700">Bought</span>
            <p className="font-bold text-purple-800">{speciesRate.bought}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function BreedingAnalyticsCard({ speciesRate }) {
  const config = SPECIES_CONFIG[speciesRate.species];
  const trend = speciesRate.breeding_females_trend || 0;
  const trendPositive = trend >= 0;

  return (
    <Card className="border-border/60 overflow-hidden">
      <div className="h-2" style={{ backgroundColor: speciesRate.color }} />
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: speciesRate.color }} />
          <CardTitle className="font-heading text-base">{config?.label || speciesRate.species}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg bg-emerald-50">
            <div className="flex items-center justify-between text-xs text-emerald-700">
              <span>Breeding Females (Koo)</span>
              <span className={trendPositive ? 'text-emerald-600' : 'text-red-600'}>
                {trendPositive ? <TrendUp className="h-3 w-3" /> : <TrendDown className="h-3 w-3" />}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <p className="text-2xl font-bold text-emerald-800">{speciesRate.breeding_females}</p>
              <p className={`text-sm font-semibold ${trendPositive ? 'text-emerald-700' : 'text-red-700'}`}>
                {trendPositive ? '+' : ''}{trend}
              </p>
            </div>
          </div>
          <div className="p-3 rounded-lg bg-slate-50">
            <p className="text-xs text-slate-600">Breeding Males (Dume Mbegu)</p>
            <p className="text-2xl font-bold text-slate-800">{speciesRate.breeding_males}</p>
          </div>
          <div className="p-3 rounded-lg bg-amber-50">
            <div className="flex items-baseline justify-between">
              <p className="text-xs text-amber-700">Births</p>
              <p className="text-2xl font-bold text-amber-800">{speciesRate.births}</p>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-amber-200/80">
              <div>
                <p className="text-[11px] text-amber-700/80">Male (Dume)</p>
                <p className="text-sm font-semibold text-amber-900">{speciesRate.births_male || 0}</p>
              </div>
              <div className="border-l border-amber-200/80 pl-2">
                <p className="text-[11px] text-amber-700/80">Female (Jike)</p>
                <p className="text-sm font-semibold text-amber-900">{speciesRate.births_female || 0}</p>
              </div>
            </div>
          </div>
          <div className="p-3 rounded-lg bg-blue-50">
            <p className="text-xs text-blue-700">Calving Rate</p>
            <p className="text-2xl font-bold text-blue-800">{speciesRate.calving_rate}%</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function NetChangeRow({ netChange }) {
  const config = SPECIES_CONFIG[netChange.species];
  const isPositive = netChange.net_change >= 0;
  
  return (
    <div className="p-4 rounded-lg border border-border">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
          <span className="font-medium">{config?.label || netChange.species}</span>
        </div>
        <div className={`flex items-center gap-1 ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {isPositive ? <TrendUp className="h-5 w-5" /> : <TrendDown className="h-5 w-5" />}
          <span className="font-bold text-2xl">{isPositive ? '+' : ''}{netChange.net_change}</span>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2 text-sm">
        <div className="text-center p-2 rounded bg-green-50">
          <p className="text-green-700 text-xs">Births</p>
          <p className="font-bold text-green-800">+{netChange.births}</p>
        </div>
        <div className="text-center p-2 rounded bg-blue-50">
          <p className="text-blue-700 text-xs">Bought</p>
          <p className="font-bold text-blue-800">+{netChange.bought}</p>
        </div>
        <div className="text-center p-2 rounded bg-red-50">
          <p className="text-red-700 text-xs">Deaths</p>
          <p className="font-bold text-red-800">-{netChange.deaths}</p>
        </div>
        <div className="text-center p-2 rounded bg-amber-50">
          <p className="text-amber-700 text-xs">Sold</p>
          <p className="font-bold text-amber-800">-{netChange.sold}</p>
        </div>
      </div>
    </div>
  );
}

function DeathCauseBar({ cause, count, percentage, avgDaysSick }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium">{cause}</span>
          <Badge variant="outline">{count}</Badge>
        </div>
        <div className="flex items-center gap-2">
          {avgDaysSick !== null && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {avgDaysSick}d
            </span>
          )}
          <span className="text-sm font-medium w-12 text-right">{percentage}%</span>
        </div>
      </div>
      <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-destructive rounded-full" style={{ width: percentage + '%' }} />
      </div>
    </div>
  );
}

function DeathsBySpeciesCard({ ds }) {
  const config = SPECIES_CONFIG[ds.species];
  
  const catBadges = [];
  const cats = ds.by_category || [];
  for (let i = 0; i < cats.length && i < 5; i++) {
    catBadges.push(
      <Badge key={cats[i].category_id} variant="outline" className="text-xs">
        {cats[i].category_name_sw}: {cats[i].count}
      </Badge>
    );
  }
  
  const causeRows = [];
  const causes = ds.by_cause || [];
  for (let i = 0; i < causes.length && i < 3; i++) {
    causeRows.push(
      <div key={causes[i].cause} className="flex items-center justify-between text-sm">
        <span>{causes[i].cause}</span>
        <span className="font-bold">{causes[i].count} ({causes[i].percentage}%)</span>
      </div>
    );
  }

  const diseaseRows = [];
  const diseases = ds.by_disease || [];
  for (let i = 0; i < diseases.length && i < 3; i++) {
    diseaseRows.push(
      <div key={diseases[i].disease_id} className="flex items-center justify-between text-sm">
        <span>{diseases[i].disease_name}</span>
        <span className="font-bold">{diseases[i].count} ({diseases[i].percentage}%)</span>
      </div>
    );
  }
  
  return (
    <Card className="border-border/60">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
          <CardTitle className="font-heading text-base">{config?.label || ds.species}</CardTitle>
          <Badge variant="destructive" className="ml-auto">{ds.total_deaths}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {catBadges.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">By Category</p>
            <div className="flex flex-wrap gap-2">{catBadges}</div>
          </div>
        )}
        {causeRows.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">By Cause</p>
            <div className="space-y-1">{causeRows}</div>
          </div>
        )}
        {diseaseRows.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">By Disease</p>
            <div className="space-y-1">{diseaseRows}</div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-2 pt-2 border-t">
          <div className="p-2 rounded bg-green-50 text-center">
            <FirstAid className="h-4 w-4 text-green-600 mx-auto" />
            <p className="text-xs text-green-700">With Vet</p>
            <p className="font-bold text-green-800">{ds.with_vet_attendance}</p>
          </div>
          <div className="p-2 rounded bg-slate-50 text-center">
            <Clock className="h-4 w-4 text-slate-600 mx-auto" />
            <p className="text-xs text-slate-700">Avg Days</p>
            <p className="font-bold text-slate-800">{ds.avg_days_sick || '-'}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AbortionBySpeciesCard({ ab }) {
  const config = SPECIES_CONFIG[ab.species];
  
  const stageItems = [];
  const stages = ab.by_stage || [];
  for (let i = 0; i < stages.length; i++) {
    const s = stages[i];
    const stageLabels = { early: 'Early (0-3m)', mid: 'Mid (3-6m)', late: 'Late (6-9m)' };
    stageItems.push(
      <div key={s.stage} className="text-center p-2 rounded bg-amber-50">
        <p className="text-xs text-amber-700">{stageLabels[s.stage] || s.stage}</p>
        <p className="font-bold text-amber-800">{s.count}</p>
        <p className="text-xs text-amber-600">{s.percentage}%</p>
      </div>
    );
  }
  
  return (
    <Card className="border-border/60">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
          <CardTitle className="font-heading text-base">{config?.label || ab.species}</CardTitle>
          <Badge variant="outline" className="ml-auto bg-amber-50 text-amber-700">{ab.total_abortions} abortions</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-2 mb-3">
          {stageItems}
        </div>
        <div className="pt-2 border-t">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Abortion Rate</span>
            <span className="font-bold text-amber-700">{ab.abortion_rate}%</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SalesBySpeciesCard({ sale }) {
  const config = SPECIES_CONFIG[sale.species];
  
  const catItems = [];
  const cats = sale.by_category || [];
  for (let i = 0; i < cats.length && i < 4; i++) {
    catItems.push(
      <div key={i} className="text-sm flex justify-between">
        <span>{cats[i].category_name_sw}</span>
        <span className="font-medium">{cats[i].count} @ TZS {cats[i].avg_price?.toLocaleString()}</span>
      </div>
    );
  }
  
  return (
    <Card className="border-border/60">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
          <CardTitle className="font-heading text-base">{config?.label || sale.species}</CardTitle>
          <Badge variant="outline" className="ml-auto">{sale.count} sold</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="p-2 rounded bg-green-50 text-center">
            <p className="text-xs text-green-700">Total Value</p>
            <p className="font-bold text-green-800">TZS {sale.total_value?.toLocaleString()}</p>
          </div>
          <div className="p-2 rounded bg-blue-50 text-center">
            <p className="text-xs text-blue-700">Avg Price</p>
            <p className="font-bold text-blue-800">TZS {sale.average_price?.toLocaleString()}</p>
          </div>
        </div>
        {catItems.length > 0 && (
          <div className="pt-2 border-t space-y-1">
            <p className="text-xs text-muted-foreground mb-1">By Category</p>
            {catItems}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AnalyticsCategorySection({ speciesData }) {
  const config = SPECIES_CONFIG[speciesData.species];
  const cats = (speciesData.categories || []).slice().sort(function(a, b) {
    return (b.count || 0) - (a.count || 0);
  });
  if (cats.length === 0) return null;
  const total = speciesData.total || 0;

  const catItems = [];
  for (let i = 0; i < cats.length; i++) {
    const netChange = cats[i].net_change || 0;
    const isPositive = netChange >= 0;
    const percent = total > 0 ? ((cats[i].count / total) * 100).toFixed(1) : '0.0';
    catItems.push(
      <div key={cats[i].category_id} className="p-2 rounded bg-muted/50 text-center">
        <p className="text-xs text-muted-foreground truncate">{cats[i].category_name_sw}</p>
        <p className="text-base font-bold font-heading mt-1">{cats[i].count}</p>
        <p className="text-[11px] text-muted-foreground">{percent}%</p>
        <p className={`text-xs mt-1 ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {isPositive ? '+' : ''}{netChange}
        </p>
      </div>
    );
  }

  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-3 w-3 rounded-full" style={{ backgroundColor: config?.color }} />
        <h4 className="font-semibold text-sm">{config?.label || speciesData.species}</h4>
        <Badge variant="outline" className="ml-auto">{speciesData.total} total</Badge>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {catItems}
      </div>
    </div>
  );
}

function Reports() {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [loadingDetailed, setLoadingDetailed] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [rangeData, setRangeData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [detailedData, setDetailedData] = useState(null);

  const [dailyDate, setDailyDate] = useState(new Date());
  const [startDate, setStartDate] = useState(subDays(new Date(), 30));
  const [endDate, setEndDate] = useState(new Date());
  const [locationId, setLocationId] = useState('all');

  function handleRangeChange(range) {
    if (range && range.from && range.to) {
      setStartDate(range.from);
      setEndDate(range.to);
    }
  }

  useEffect(function() {
    loadLocations();
    loadDailyReport();
  }, []);

  useEffect(function() {
    loadDailyReport();
  }, [dailyDate]);

  async function loadLocations() {
    try {
      const response = await getLocations();
      setLocations(response.data);
    } catch (error) {
      console.error('Failed to load locations');
    }
  }

  async function loadDailyReport() {
    setLoading(true);
    try {
      const response = await getDailyReport(format(dailyDate, 'yyyy-MM-dd'));
      setReportData(response.data);
    } catch (error) {
      toast.error('Failed to load daily report');
    } finally {
      setLoading(false);
    }
  }

  async function loadRangeReport() {
    try {
      const params = {
        start_date: format(startDate, 'yyyy-MM-dd'),
        end_date: format(endDate, 'yyyy-MM-dd')
      };
      if (locationId && locationId !== 'all') params.location_id = locationId;
      const response = await getRangeReport(params);
      setRangeData(response.data);
    } catch (error) {
      toast.error('Failed to load range report');
    }
  }

  async function loadAnalytics() {
    try {
      const params = {
        start_date: format(startDate, 'yyyy-MM-dd'),
        end_date: format(endDate, 'yyyy-MM-dd')
      };
      if (locationId && locationId !== 'all') params.location_id = locationId;
      const response = await getAnalyticsReport(params);
      setAnalyticsData(response.data);
    } catch (error) {
      toast.error('Failed to load analytics');
    }
  }

  async function loadDetailedReport() {
    try {
      const params = {
        start_date: format(startDate, 'yyyy-MM-dd'),
        end_date: format(endDate, 'yyyy-MM-dd')
      };
      if (locationId && locationId !== 'all') params.location_id = locationId;
      const response = await getDetailedReport(params);
      setDetailedData(response.data);
    } catch (error) {
      toast.error('Failed to load detailed report');
    }
  }

  async function handleGenerateReport() {
    setLoadingAnalytics(true);
    await Promise.all([loadRangeReport(), loadAnalytics()]);
    setLoadingAnalytics(false);
  }

  async function handleGenerateDetailedReport() {
    setLoadingDetailed(true);
    await loadDetailedReport();
    setLoadingDetailed(false);
  }

  // Build elements using for loops
  const locationOptions = [];
  for (let i = 0; i < locations.length; i++) {
    locationOptions.push(
      <SelectItem key={locations[i].id} value={locations[i].id.toString()}>
        {locations[i].name}
      </SelectItem>
    );
  }

  const speciesRates = analyticsData?.species_rates || [];
  const analyticsCards = [];
  for (let i = 0; i < speciesRates.length; i++) {
    analyticsCards.push(<AnalyticsCard key={speciesRates[i].species} speciesRate={speciesRates[i]} />);
  }

  const breedingCards = [];
  for (let i = 0; i < speciesRates.length; i++) {
    breedingCards.push(<BreedingAnalyticsCard key={speciesRates[i].species} speciesRate={speciesRates[i]} />);
  }

  const netChanges = analyticsData?.net_changes || [];
  const netChangeRows = [];
  for (let i = 0; i < netChanges.length; i++) {
    netChangeRows.push(<NetChangeRow key={netChanges[i].species} netChange={netChanges[i]} />);
  }

  const deathAnalysis = analyticsData?.death_analysis;
  const topCauses = deathAnalysis?.top_causes || [];
  const causeBars = [];
  for (let i = 0; i < topCauses.length; i++) {
    const c = topCauses[i];
    causeBars.push(<DeathCauseBar key={c.cause} cause={c.cause} count={c.count} percentage={c.percentage} avgDaysSick={c.avg_days_sick} />);
  }

  const topDiseases = deathAnalysis?.top_diseases || [];
  const diseaseBars = [];
  for (let i = 0; i < topDiseases.length; i++) {
    const d = topDiseases[i];
    diseaseBars.push(<DeathCauseBar key={d.disease_id} cause={d.disease_name} count={d.count} percentage={d.percentage} avgDaysSick={d.avg_days_sick} />);
  }

  const deathsBySpecies = deathAnalysis?.by_species || [];
  const deathCards = [];
  for (let i = 0; i < deathsBySpecies.length; i++) {
    deathCards.push(<DeathsBySpeciesCard key={deathsBySpecies[i].species} ds={deathsBySpecies[i]} />);
  }

  const deathsByLocation = deathAnalysis?.by_location || [];
  const deathLocationRows = [];
  for (let i = 0; i < deathsByLocation.length; i++) {
    const loc = deathsByLocation[i];
    deathLocationRows.push(
      <div key={loc.location_id} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
        <div>
          <p className="font-medium">{loc.location_name}</p>
          <p className="text-xs text-muted-foreground">{loc.percentage}% of deaths</p>
        </div>
        <Badge variant="outline">{loc.total_deaths}</Badge>
      </div>
    );
  }

  // Abortion analysis
  const abortionAnalysis = analyticsData?.abortion_analysis;
  const abortionsBySpecies = abortionAnalysis?.by_species || [];
  const abortionCards = [];
  for (let i = 0; i < abortionsBySpecies.length; i++) {
    abortionCards.push(<AbortionBySpeciesCard key={abortionsBySpecies[i].species} ab={abortionsBySpecies[i]} />);
  }

  // Sales analysis
  const salesAnalysis = analyticsData?.sales_analysis;
  const salesBySpecies = salesAnalysis?.by_species || [];
  const salesCards = [];
  for (let i = 0; i < salesBySpecies.length; i++) {
    salesCards.push(<SalesBySpeciesCard key={salesBySpecies[i].species} sale={salesBySpecies[i]} />);
  }

  const analyticsCategoryTotals = analyticsData?.category_totals || [];
  const categorySections = [];
  for (let i = 0; i < analyticsCategoryTotals.length; i++) {
    if (analyticsCategoryTotals[i].categories && analyticsCategoryTotals[i].categories.length > 0) {
      categorySections.push(
        <AnalyticsCategorySection key={analyticsCategoryTotals[i].species} speciesData={analyticsCategoryTotals[i]} />
      );
    }
  }


  const stockLocations = reportData ? Object.entries(reportData.stock_by_location || {}) : [];
  const stockCards = [];
  for (let i = 0; i < stockLocations.length; i++) {
    const locName = stockLocations[i][0];
    const stock = stockLocations[i][1];
    const total = (stock.cattle || 0) + (stock.sheep || 0) + (stock.goat || 0);
    stockCards.push(
      <div key={locName} className="p-4 rounded-lg border border-border bg-muted/30">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-heading font-semibold">{locName}</h3>
          <span className="text-2xl font-bold">{total}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div className="p-2 rounded bg-white">
            <p className="text-xs text-muted-foreground">Cattle</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.cattle?.color }}>{stock.cattle || 0}</p>
          </div>
          <div className="p-2 rounded bg-white">
            <p className="text-xs text-muted-foreground">Sheep</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.sheep?.color }}>{stock.sheep || 0}</p>
          </div>
          <div className="p-2 rounded bg-white">
            <p className="text-xs text-muted-foreground">Goat</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.goat?.color }}>{stock.goat || 0}</p>
          </div>
        </div>
      </div>
    );
  }

  const eventTypes = rangeData ? Object.entries(rangeData.events_by_type || {}) : [];
  const eventCards = [];
  for (let i = 0; i < eventTypes.length; i++) {
    const type = eventTypes[i][0];
    const data = eventTypes[i][1];
    const eventConfig = EVENT_TYPES[type];
    eventCards.push(
      <div key={type} className="p-4 rounded-lg border border-border text-center">
        <Badge className={(eventConfig?.color || '') + ' mb-2'}>{eventConfig?.label || type}</Badge>
        <p className="text-2xl font-bold">{data.count}</p>
        <p className="text-sm text-muted-foreground">{data.total_animals} animals</p>
      </div>
    );
  }

  const openingTotals = detailedData?.opening_totals || [];
  const closingTotals = detailedData?.closing_totals || [];
  const detailedEvents = detailedData?.events || [];

  const openingCards = [];
  for (let i = 0; i < openingTotals.length; i++) {
    const loc = openingTotals[i];
    openingCards.push(
      <div key={`opening-${loc.location_id}`} className="p-4 rounded-lg border border-border bg-muted/30">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-heading font-semibold">{loc.location_name}</h4>
          <span className="text-xl font-bold">{loc.total}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="p-2 rounded bg-white">
            <p className="text-muted-foreground">Cattle</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.cattle?.color }}>{loc.cattle}</p>
          </div>
          <div className="p-2 rounded bg-white">
            <p className="text-muted-foreground">Sheep</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.sheep?.color }}>{loc.sheep}</p>
          </div>
          <div className="p-2 rounded bg-white">
            <p className="text-muted-foreground">Goat</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.goat?.color }}>{loc.goat}</p>
          </div>
        </div>
      </div>
    );
  }

  const closingCards = [];
  for (let i = 0; i < closingTotals.length; i++) {
    const loc = closingTotals[i];
    closingCards.push(
      <div key={`closing-${loc.location_id}`} className="p-4 rounded-lg border border-border bg-muted/30">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-heading font-semibold">{loc.location_name}</h4>
          <span className="text-xl font-bold">{loc.total}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="p-2 rounded bg-white">
            <p className="text-muted-foreground">Cattle</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.cattle?.color }}>{loc.cattle}</p>
          </div>
          <div className="p-2 rounded bg-white">
            <p className="text-muted-foreground">Sheep</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.sheep?.color }}>{loc.sheep}</p>
          </div>
          <div className="p-2 rounded bg-white">
            <p className="text-muted-foreground">Goat</p>
            <p className="font-bold" style={{ color: SPECIES_CONFIG.goat?.color }}>{loc.goat}</p>
          </div>
        </div>
      </div>
    );
  }

  const detailedEventCards = [];
  for (let i = 0; i < detailedEvents.length; i++) {
    const ev = detailedEvents[i];
    const eventConfig = EVENT_TYPES[ev.event_type];
    const dateLabel = ev.log_date ? format(new Date(ev.log_date), 'MMM d, yyyy') : '';
    let movementLine = '';
    if (ev.from_location_name || ev.to_location_name) {
      const fromLoc = ev.from_location_name || 'Unknown';
      const toLoc = ev.to_location_name || 'Unknown';
      movementLine = `From ${fromLoc} to ${toLoc}`;
    } else if (ev.from_category_name_sw || ev.to_category_name_sw) {
      const fromCat = ev.from_category_name_sw || 'Unknown';
      const toCat = ev.to_category_name_sw || 'Unknown';
      movementLine = `Category: ${fromCat} -> ${toCat}`;
    }

    detailedEventCards.push(
      <div key={`event-${ev.id}`} className="p-4 rounded-lg border border-border bg-muted/30">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Badge className={eventConfig?.color || ''}>{eventConfig?.label || ev.event_type}</Badge>
              <span className="text-xs text-muted-foreground">{dateLabel}</span>
            </div>
            <p className="font-medium">{ev.location_name}</p>
            <p className="text-xs text-muted-foreground">{SPECIES_CONFIG[ev.species]?.label || ev.species}</p>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold">{ev.count}</p>
            {ev.category_name_sw && (
              <p className="text-xs text-muted-foreground">Category: {ev.category_name_sw}</p>
            )}
          </div>
        </div>
        {movementLine && (
          <p className="text-xs text-muted-foreground mt-2">{movementLine}</p>
        )}
        {ev.notes && (
          <p className="text-xs text-muted-foreground mt-1">Notes: {ev.notes}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div>
        <h1 className="font-heading text-3xl font-bold">Reports & Analytics</h1>
        <p className="text-muted-foreground mt-1">View herd performance, death analysis, abortions, and sales</p>
      </div>

      <Tabs defaultValue="analytics">
        <TabsList className="flex-wrap">
          <TabsTrigger value="analytics" data-testid="analytics-tab">Herd Analytics</TabsTrigger>
          <TabsTrigger value="breeding" data-testid="breeding-tab">Breeding Analytics</TabsTrigger>
          <TabsTrigger value="deaths" data-testid="deaths-tab">Deaths</TabsTrigger>
          <TabsTrigger value="abortions" data-testid="abortions-tab">Abortions</TabsTrigger>
          <TabsTrigger value="sales" data-testid="sales-tab">Sales</TabsTrigger>
          <TabsTrigger value="detailed" data-testid="detailed-tab">Detailed Report</TabsTrigger>
          <TabsTrigger value="daily" data-testid="daily-tab">Daily</TabsTrigger>
        </TabsList>

        <TabsContent value="analytics" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Location</label>
                  <Select value={locationId} onValueChange={setLocationId}>
                    <SelectTrigger className="w-[180px]" data-testid="analytics-location-filter">
                      <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Locations" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Locations</SelectItem>
                      {locationOptions}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Date Range</label>
                  <DateRangePicker value={{ from: startDate, to: endDate }} onChange={handleRangeChange} />
                </div>
                <Button onClick={handleGenerateReport} className="gap-2" data-testid="generate-analytics-btn">
                  <MagnifyingGlass className="h-4 w-4" />
                  Generate Report
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingAnalytics ? (
            <Skeleton className="h-64" />
          ) : analyticsData ? (
            <>
              {analyticsData.location_name && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  <span>Showing for: <strong className="text-foreground">{analyticsData.location_name}</strong></span>
                </div>
              )}
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {analyticsCards}
              </div>

              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="font-heading flex items-center gap-2">
                    <TrendUp className="h-5 w-5 text-primary" />
                    Net Change in Animals
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {netChangeRows}
                  </div>
                </CardContent>
              </Card>


              {categorySections.length > 0 && (
                <Card className="border-border/60">
                  <CardHeader>
                    <CardTitle className="font-heading flex items-center gap-2">
                      <Package className="h-5 w-5 text-primary" />
                      Animal Group Breakdown
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {categorySections}
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <ChartBar className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Click Generate Report to view analytics</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="breeding" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Location</label>
                  <Select value={locationId} onValueChange={setLocationId}>
                    <SelectTrigger className="w-[180px]" data-testid="breeding-location-filter">
                      <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Locations" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Locations</SelectItem>
                      {locationOptions}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Date Range</label>
                  <DateRangePicker value={{ from: startDate, to: endDate }} onChange={handleRangeChange} />
                </div>
                <Button onClick={handleGenerateReport} className="gap-2" data-testid="generate-breeding-btn">
                  <MagnifyingGlass className="h-4 w-4" />
                  Generate Report
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingAnalytics ? (
            <Skeleton className="h-64" />
          ) : analyticsData ? (
            <>
              {analyticsData.location_name && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  <span>Showing for: <strong className="text-foreground">{analyticsData.location_name}</strong></span>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {breedingCards}
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <ChartBar className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Click Generate Report to view breeding analytics</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="deaths" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Location</label>
                  <Select value={locationId} onValueChange={setLocationId}>
                    <SelectTrigger className="w-[180px]">
                      <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Locations" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Locations</SelectItem>
                      {locationOptions}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Date Range</label>
                  <DateRangePicker value={{ from: startDate, to: endDate }} onChange={handleRangeChange} />
                </div>
                <Button onClick={handleGenerateReport} className="gap-2" data-testid="generate-death-btn">
                  <MagnifyingGlass className="h-4 w-4" />
                  Generate Report
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingAnalytics ? (
            <Skeleton className="h-64" />
          ) : deathAnalysis ? (
            <>
              <div className="grid grid-cols-3 gap-4">
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <Skull className="h-5 w-5 text-destructive" />
                      <span className="text-sm text-muted-foreground">Total Deaths</span>
                    </div>
                    <p className="text-4xl font-bold text-destructive">{deathAnalysis.total_deaths}</p>
                  </CardContent>
                </Card>
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <FirstAid className="h-5 w-5 text-green-600" />
                      <span className="text-sm text-muted-foreground">Vet Attendance</span>
                    </div>
                    <p className="text-4xl font-bold text-green-600">{deathAnalysis.vet_attendance_rate}%</p>
                  </CardContent>
                </Card>
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <ChartBar className="h-5 w-5 text-primary" />
                      <span className="text-sm text-muted-foreground">Diseases Identified</span>
                    </div>
                    <p className="text-4xl font-bold">{topDiseases.length}</p>
                  </CardContent>
                </Card>
              </div>

              {diseaseBars.length > 0 && (
                <Card className="border-border/60">
                  <CardHeader>
                    <CardTitle className="font-heading flex items-center gap-2">
                      <Skull className="h-5 w-5 text-destructive" />
                      Deaths by Disease
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">{diseaseBars}</div>
                  </CardContent>
                </Card>
              )}

              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="font-heading flex items-center gap-2">
                    <Skull className="h-5 w-5 text-destructive" />
                    Deaths by Cause
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {causeBars.length > 0 ? (
                    <div className="space-y-4">{causeBars}</div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <p>No deaths recorded in this period</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="font-heading flex items-center gap-2">
                    <MapPin className="h-5 w-5 text-primary" />
                    Deaths by Farm
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {deathLocationRows.length > 0 ? (
                    <div className="space-y-3">{deathLocationRows}</div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <p>No farm-level death data for this period</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {deathCards.length > 0 && (
                <div>
                  <h3 className="font-heading text-lg font-semibold mb-4">Deaths by Species</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {deathCards}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Skull className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Click Generate Report to view death analysis</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="abortions" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Location</label>
                  <Select value={locationId} onValueChange={setLocationId}>
                    <SelectTrigger className="w-[180px]">
                      <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Locations" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Locations</SelectItem>
                      {locationOptions}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Date Range</label>
                  <DateRangePicker value={{ from: startDate, to: endDate }} onChange={handleRangeChange} />
                </div>
                <Button onClick={handleGenerateReport} className="gap-2">
                  <MagnifyingGlass className="h-4 w-4" />
                  Generate Report
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingAnalytics ? (
            <Skeleton className="h-64" />
          ) : abortionAnalysis ? (
            <>
              <div className="grid grid-cols-4 gap-4">
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <Warning className="h-5 w-5 text-amber-600" />
                      <span className="text-sm text-muted-foreground">Total Abortions</span>
                    </div>
                    <p className="text-4xl font-bold text-amber-600">{abortionAnalysis.total_abortions}</p>
                  </CardContent>
                </Card>
                {(abortionAnalysis.by_stage || []).map(function(s) {
                  const stageLabels = { early: 'Early (0-3m)', mid: 'Mid (3-6m)', late: 'Late (6-9m)' };
                  return (
                    <Card key={s.stage} className="border-border/60">
                      <CardContent className="p-6">
                        <span className="text-sm text-muted-foreground">{stageLabels[s.stage]}</span>
                        <p className="text-3xl font-bold text-amber-700">{s.count}</p>
                        <p className="text-sm text-amber-600">{s.percentage}%</p>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>

              {abortionCards.length > 0 ? (
                <div>
                  <h3 className="font-heading text-lg font-semibold mb-4">Abortions by Species</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {abortionCards}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <p>No abortions recorded in this period</p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Warning className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Click Generate Report to view abortion analysis</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="sales" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Location</label>
                  <Select value={locationId} onValueChange={setLocationId}>
                    <SelectTrigger className="w-[180px]">
                      <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Locations" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Locations</SelectItem>
                      {locationOptions}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Date Range</label>
                  <DateRangePicker value={{ from: startDate, to: endDate }} onChange={handleRangeChange} />
                </div>
                <Button onClick={handleGenerateReport} className="gap-2">
                  <MagnifyingGlass className="h-4 w-4" />
                  Generate Report
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingAnalytics ? (
            <Skeleton className="h-64" />
          ) : salesAnalysis ? (
            <>
              <div className="grid grid-cols-4 gap-4">
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <ShoppingCart className="h-5 w-5 text-blue-600" />
                      <span className="text-sm text-muted-foreground">Total Sold</span>
                    </div>
                    <p className="text-4xl font-bold text-blue-600">{salesAnalysis.total_count}</p>
                  </CardContent>
                </Card>
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <CurrencyCircleDollar className="h-5 w-5 text-green-600" />
                      <span className="text-sm text-muted-foreground">Total Revenue</span>
                    </div>
                    <p className="text-3xl font-bold text-green-600">TZS {salesAnalysis.total_value?.toLocaleString()}</p>
                  </CardContent>
                </Card>
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-2 mb-2">
                      <ChartBar className="h-5 w-5 text-purple-600" />
                      <span className="text-sm text-muted-foreground">Avg Price</span>
                    </div>
                    <p className="text-3xl font-bold text-purple-600">TZS {salesAnalysis.average_price?.toLocaleString()}</p>
                  </CardContent>
                </Card>
                <Card className="border-border/60">
                  <CardContent className="p-6">
                    <span className="text-sm text-muted-foreground">Price Range</span>
                    <p className="text-lg font-bold mt-1">
                      TZS {salesAnalysis.price_range?.min?.toLocaleString()} - {salesAnalysis.price_range?.max?.toLocaleString()}
                    </p>
                  </CardContent>
                </Card>
              </div>

              {salesCards.length > 0 ? (
                <div>
                  <h3 className="font-heading text-lg font-semibold mb-4">Sales by Species</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {salesCards}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <p>No sales recorded in this period</p>
                </div>
              )}

              {(salesAnalysis.top_buyers || []).length > 0 && (
                <Card className="border-border/60">
                  <CardHeader>
                    <CardTitle className="font-heading flex items-center gap-2">
                      <ShoppingCart className="h-5 w-5 text-primary" />
                      Top Buyers
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {(salesAnalysis.top_buyers || []).map(function(buyer, idx) {
                        return (
                          <div key={buyer.buyer_name} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                            <div className="flex items-center gap-3">
                              <span className="font-bold text-lg text-muted-foreground">#{idx + 1}</span>
                              <div>
                                <p className="font-medium">{buyer.buyer_name}</p>
                                <p className="text-sm text-muted-foreground">{buyer.count} animals</p>
                              </div>
                            </div>
                            <p className="font-bold text-green-600">TZS {buyer.total_value?.toLocaleString()}</p>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <ShoppingCart className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Click Generate Report to view sales analysis</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="detailed" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <div className="flex flex-wrap items-end gap-4">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Location</label>
                  <Select value={locationId} onValueChange={setLocationId}>
                    <SelectTrigger className="w-[180px]" data-testid="detailed-location-filter">
                      <MapPin className="h-4 w-4 mr-2 text-muted-foreground" />
                      <SelectValue placeholder="All Locations" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Locations</SelectItem>
                      {locationOptions}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Date Range</label>
                  <DateRangePicker value={{ from: startDate, to: endDate }} onChange={handleRangeChange} />
                </div>
                <Button onClick={handleGenerateDetailedReport} className="gap-2" data-testid="generate-detailed-btn">
                  <MagnifyingGlass className="h-4 w-4" />
                  Generate Report
                </Button>
              </div>
            </CardContent>
          </Card>

          {loadingDetailed ? (
            <Skeleton className="h-64" />
          ) : detailedData ? (
            <>
              {detailedData.location_name && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  <span>Showing for: <strong className="text-foreground">{detailedData.location_name}</strong></span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="border-border/60">
                  <CardHeader>
                    <CardTitle className="font-heading">Opening Balances</CardTitle>
                    <CardDescription>{format(startDate, 'PPP')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {openingCards.length > 0 ? (
                      <div className="space-y-3">{openingCards}</div>
                    ) : (
                      <div className="text-center py-6 text-muted-foreground">
                        <p>No opening balances for this period</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card className="border-border/60">
                  <CardHeader>
                    <CardTitle className="font-heading">Closing Balances</CardTitle>
                    <CardDescription>{format(endDate, 'PPP')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {closingCards.length > 0 ? (
                      <div className="space-y-3">{closingCards}</div>
                    ) : (
                      <div className="text-center py-6 text-muted-foreground">
                        <p>No closing balances for this period</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="font-heading">Events in Range</CardTitle>
                  <CardDescription>{format(startDate, 'PPP')} - {format(endDate, 'PPP')}</CardDescription>
                </CardHeader>
                <CardContent>
                  {detailedEventCards.length > 0 ? (
                    <div className="space-y-3">{detailedEventCards}</div>
                  ) : (
                    <div className="text-center py-6 text-muted-foreground">
                      <p>No events recorded in this period</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <ChartBar className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Click Generate Report to view detailed report</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="daily" className="space-y-6 mt-6">
          <Card className="border-border/60">
            <CardContent className="p-4">
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="gap-2" data-testid="daily-date-picker">
                    <CalendarBlank className="h-4 w-4" />
                    {format(dailyDate, 'PPP')}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar mode="single" selected={dailyDate} onSelect={function(d) { if (d) setDailyDate(d); }} />
                </PopoverContent>
              </Popover>
            </CardContent>
          </Card>

          {loading ? (
            <Skeleton className="h-64" />
          ) : (
            <Card className="border-border/60">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <MapPin className="h-5 w-5 text-primary" />
                  Stock by Location - {formatDate(dailyDate)}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {stockCards.length > 0 ? (
                  <div className="space-y-4">{stockCards}</div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <p>No stock data for this date</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default Reports;
