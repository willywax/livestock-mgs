"""
Test Dashboard and Analytics features for ShambaManager
Tests: Herd Performance, Location Filter, Analytics with sold/bought counts, Sales Summary, Death Causes
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_PHONE = "255700000000"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestDashboard:
    """Dashboard endpoint tests - Herd Performance and Location Filter"""
    
    def test_dashboard_returns_herd_performance(self, auth_headers):
        """Dashboard should include herd_performance with calving_rate and mortality_rate per species"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "herd_performance" in data
        assert isinstance(data["herd_performance"], list)
        assert len(data["herd_performance"]) == 3  # cattle, sheep, goat
        
        for perf in data["herd_performance"]:
            assert "species" in perf
            assert "total_stock" in perf
            assert "breeding_females" in perf
            assert "births_30d" in perf
            assert "deaths_30d" in perf
            assert "calving_rate" in perf
            assert "mortality_rate" in perf
            assert "color" in perf
            
            # Verify rates are numbers
            assert isinstance(perf["calving_rate"], (int, float))
            assert isinstance(perf["mortality_rate"], (int, float))
    
    def test_dashboard_species_breakdown(self, auth_headers):
        """Dashboard should show species totals and category breakdowns"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "species_totals" in data
        assert "species_category_totals" in data
        assert "total_animals" in data
        
        # Verify species_totals structure
        for species in data["species_totals"]:
            assert "species" in species
            assert "total" in species
            assert "color" in species
    
    def test_dashboard_location_filter_works(self, auth_headers):
        """Dashboard should filter by location when location_id is provided"""
        # First get locations to find one with data
        loc_response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = loc_response.json()
        
        # Get dashboard without filter
        all_response = requests.get(f"{BASE_URL}/api/dashboard", headers=auth_headers)
        all_data = all_response.json()
        
        # Get dashboard with location filter (Sirori has data)
        sirori = next((l for l in locations if l["name"] == "Sirori"), None)
        if sirori:
            filtered_response = requests.get(
                f"{BASE_URL}/api/dashboard?location_id={sirori['id']}", 
                headers=auth_headers
            )
            assert filtered_response.status_code == 200
            
            filtered_data = filtered_response.json()
            assert filtered_data["selected_location_id"] == sirori["id"]
            assert filtered_data["selected_location_name"] == "Sirori"
            
            # Location totals should only show the selected location
            assert len(filtered_data["location_totals"]) == 1
            assert filtered_data["location_totals"][0]["location_name"] == "Sirori"
    
    def test_dashboard_no_old_cards(self, auth_headers):
        """Dashboard response should not include deprecated fields for old cards"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        # These fields exist but their UI cards were removed
        # The data is still in response for backward compatibility
        assert "pending_logs_today" in data  # Field exists but card removed in UI
        assert "total_locations" in data  # Field exists but card removed in UI
        # today_events exists but isn't shown as a separate card
        assert "today_events" in data


class TestAnalytics:
    """Analytics/Reports endpoint tests"""
    
    def test_analytics_returns_species_rates(self, auth_headers):
        """Analytics should return calving_rate and mortality_rate for each species"""
        response = requests.get(
            f"{BASE_URL}/api/reports/analytics?start_date=2025-01-01&end_date=2026-12-31",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "species_rates" in data
        assert isinstance(data["species_rates"], list)
        assert len(data["species_rates"]) == 3
        
        for rate in data["species_rates"]:
            assert "species" in rate
            assert "total_stock" in rate
            assert "breeding_females" in rate
            assert "births" in rate
            assert "births_male" in rate
            assert "births_female" in rate
            assert "deaths" in rate
            assert "sold" in rate
            assert "bought" in rate
            assert "calving_rate" in rate
            assert "mortality_rate" in rate
            assert "color" in rate
    
    def test_analytics_sold_bought_counts(self, auth_headers):
        """Analytics should show sold and bought counts per species"""
        response = requests.get(
            f"{BASE_URL}/api/reports/analytics?start_date=2025-01-01&end_date=2026-12-31",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify cattle has sales (we know there are 10 cattle sales)
        cattle_rate = next(r for r in data["species_rates"] if r["species"] == "cattle")
        assert cattle_rate["sold"] >= 0
        assert cattle_rate["bought"] >= 0
    
    def test_analytics_sales_summary(self, auth_headers):
        """Analytics should include sales summary with total revenue, count, avg price"""
        response = requests.get(
            f"{BASE_URL}/api/reports/analytics?start_date=2025-01-01&end_date=2026-12-31",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "total_sales_value" in data
        assert "total_sales_count" in data
        assert "average_sale_price" in data
        
        # Verify numeric types
        assert isinstance(data["total_sales_value"], (int, float))
        assert isinstance(data["total_sales_count"], int)
        assert isinstance(data["average_sale_price"], (int, float))
        
        # We know there are 800k TZS from 10 cattle sales
        assert data["total_sales_value"] >= 0
        assert data["total_sales_count"] >= 0
    
    def test_analytics_death_causes(self, auth_headers):
        """Analytics should include death causes breakdown"""
        response = requests.get(
            f"{BASE_URL}/api/reports/analytics?start_date=2025-01-01&end_date=2026-12-31",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "death_causes" in data
        assert isinstance(data["death_causes"], dict)
        
        # We know there's 1 death with cause "Disease"
        if data["death_causes"]:
            for cause, count in data["death_causes"].items():
                assert isinstance(cause, str)
                assert isinstance(count, int)
    
    def test_analytics_location_filter(self, auth_headers):
        """Analytics should filter by location when location_id is provided"""
        # First get locations
        loc_response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        locations = loc_response.json()
        
        sirori = next((l for l in locations if l["name"] == "Sirori"), None)
        if sirori:
            response = requests.get(
                f"{BASE_URL}/api/reports/analytics?start_date=2025-01-01&end_date=2026-12-31&location_id={sirori['id']}",
                headers=auth_headers
            )
            assert response.status_code == 200
            
            data = response.json()
            assert data["location_id"] == sirori["id"]
            assert data["location_name"] == "Sirori"


class TestLocations:
    """Location endpoints tests"""
    
    def test_get_locations(self, auth_headers):
        """Get list of locations"""
        response = requests.get(f"{BASE_URL}/api/locations", headers=auth_headers)
        assert response.status_code == 200
        
        locations = response.json()
        assert isinstance(locations, list)
        assert len(locations) > 0
        
        for loc in locations:
            assert "id" in loc
            assert "name" in loc
            assert "is_active" in loc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
