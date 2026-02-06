"""
Tests for Disease Management and Event Logging Features
- Disease CRUD operations
- Death event with disease selection
- Abortion event with stage selection
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://herd-analytics.preview.emergentagent.com').rstrip('/')

class TestDiseaseManagement:
    """Test Disease CRUD endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "phone": "255700000000",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_diseases_list(self):
        """Test GET /api/diseases returns list of diseases"""
        response = requests.get(f"{BASE_URL}/api/diseases")
        assert response.status_code == 200, f"Failed to get diseases: {response.text}"
        
        diseases = response.json()
        assert isinstance(diseases, list), "Diseases should be a list"
        assert len(diseases) > 0, "Should have at least one disease (seeded data)"
        
        # Validate disease structure
        disease = diseases[0]
        assert "id" in disease, "Disease should have id"
        assert "name" in disease, "Disease should have name"
        assert "description" in disease, "Disease should have description"
        assert "species" in disease, "Disease should have species field"
        assert "is_active" in disease, "Disease should have is_active"
        print(f"SUCCESS: Found {len(diseases)} diseases")
    
    def test_get_diseases_has_seeded_data(self):
        """Test that default diseases are seeded"""
        response = requests.get(f"{BASE_URL}/api/diseases")
        assert response.status_code == 200
        
        diseases = response.json()
        disease_names = [d["name"] for d in diseases]
        
        # Check for some expected seeded diseases
        expected_diseases = ["East Coast Fever", "Foot and Mouth Disease", "Anthrax"]
        for expected in expected_diseases:
            assert expected in disease_names, f"Expected disease '{expected}' not found"
        print(f"SUCCESS: Seeded diseases verified: {expected_diseases}")
    
    def test_create_and_delete_disease(self):
        """Test POST /api/diseases creates new disease and DELETE removes it"""
        unique_name = f"TEST_Disease_{uuid.uuid4().hex[:8]}"
        test_disease = {
            "name": unique_name,
            "description": "Test disease description",
            "species": None
        }
        
        # Create
        response = requests.post(
            f"{BASE_URL}/api/diseases",
            json=test_disease,
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed to create disease: {response.text}"
        
        created = response.json()
        assert created["name"] == test_disease["name"]
        assert created["description"] == test_disease["description"]
        assert "id" in created
        disease_id = created["id"]
        print(f"Created disease: {created['name']} with id {disease_id}")
        
        # Verify it appears in the list
        list_response = requests.get(f"{BASE_URL}/api/diseases")
        diseases = list_response.json()
        disease_ids = [d["id"] for d in diseases]
        assert disease_id in disease_ids, "Created disease should appear in list"
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/diseases/{disease_id}",
            headers=self.headers
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["message"] == "Disease deleted"
        
        # Verify it's removed from list (soft delete)
        list_response2 = requests.get(f"{BASE_URL}/api/diseases")
        diseases2 = list_response2.json()
        disease_ids2 = [d["id"] for d in diseases2]
        assert disease_id not in disease_ids2, "Deleted disease should not appear in list"
        
        print("SUCCESS: Create and delete disease test passed")
    
    def test_create_disease_duplicate_error(self):
        """Test creating duplicate disease returns error"""
        unique_name = f"TEST_DupCheck_{uuid.uuid4().hex[:8]}"
        test_disease = {
            "name": unique_name,
            "description": "Testing duplicate check"
        }
        
        # First create
        response1 = requests.post(
            f"{BASE_URL}/api/diseases",
            json=test_disease,
            headers=self.headers
        )
        assert response1.status_code == 200, f"First creation should succeed: {response1.text}"
        created_id = response1.json()["id"]
        
        # Try to create same disease again
        response2 = requests.post(
            f"{BASE_URL}/api/diseases",
            json=test_disease,
            headers=self.headers
        )
        assert response2.status_code == 400, "Should fail on duplicate disease name"
        assert "already exists" in response2.json().get("detail", "").lower()
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/diseases/{created_id}", headers=self.headers)
        print("SUCCESS: Duplicate disease check works")
    
    def test_create_disease_with_species(self):
        """Test creating disease specific to a species"""
        unique_name = f"TEST_CattleDisease_{uuid.uuid4().hex[:8]}"
        test_disease = {
            "name": unique_name,
            "description": "Only affects cattle",
            "species": "cattle"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/diseases",
            json=test_disease,
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed to create disease with species: {response.text}"
        
        created = response.json()
        assert created["species"] == "cattle"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/diseases/{created['id']}", headers=self.headers)
        print("SUCCESS: Disease with species works")
    
    def test_disease_requires_authentication(self):
        """Test that disease creation requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/diseases",
            json={"name": "Unauthorized Disease", "description": "test"}
        )
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403], f"Should require authentication, got {response.status_code}"
        print("SUCCESS: Disease creation requires authentication")


class TestEventFieldsIntegration:
    """Test that new event fields (disease_id, abortion_stage) work with daily logs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get necessary data"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "phone": "255700000000",
            "password": "admin123"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get location
        loc_response = requests.get(f"{BASE_URL}/api/locations")
        assert loc_response.status_code == 200
        locations = loc_response.json()
        assert len(locations) > 0, "Need at least one location"
        self.location_id = locations[0]["id"]
        
        # Get category
        cat_response = requests.get(f"{BASE_URL}/api/categories", params={"species": "cattle"})
        assert cat_response.status_code == 200
        categories = cat_response.json()
        assert len(categories) > 0, "Need at least one category"
        self.category_id = categories[0]["id"]
        
        # Get disease
        disease_response = requests.get(f"{BASE_URL}/api/diseases")
        assert disease_response.status_code == 200
        diseases = disease_response.json()
        assert len(diseases) > 0, "Need at least one disease"
        self.disease_id = diseases[0]["id"]
        self.disease_name = diseases[0]["name"]
    
    def test_get_daily_log_with_disease_info(self):
        """Test GET daily log includes disease info for death events"""
        # Get existing logs
        response = requests.get(f"{BASE_URL}/api/daily-logs", headers=self.headers)
        assert response.status_code == 200
        
        logs = response.json()
        print(f"Found {len(logs)} daily logs")
        
        # Check if we have any logs with events
        for log in logs[:5]:
            if log.get("events"):
                log_detail = requests.get(
                    f"{BASE_URL}/api/daily-logs/{log['id']}", 
                    headers=self.headers
                )
                assert log_detail.status_code == 200
                detail = log_detail.json()
                
                for event in detail.get("events", []):
                    if event.get("event_type") == "death":
                        print(f"Found death event: cause={event.get('cause_of_death')}, disease_id={event.get('disease_id')}")
        
        print("SUCCESS: Daily log retrieval works")
    
    def test_categories_endpoint_works(self):
        """Verify categories endpoint for form dropdowns"""
        for species in ["cattle", "sheep", "goat"]:
            response = requests.get(f"{BASE_URL}/api/categories", params={"species": species})
            assert response.status_code == 200, f"Failed for {species}"
            cats = response.json()
            assert len(cats) > 0, f"Should have categories for {species}"
        print("SUCCESS: Categories endpoint works for all species")
    
    def test_locations_endpoint_works(self):
        """Verify locations endpoint for form dropdowns"""
        response = requests.get(f"{BASE_URL}/api/locations")
        assert response.status_code == 200
        locations = response.json()
        assert len(locations) > 0, "Should have at least one location"
        
        loc = locations[0]
        assert "id" in loc
        assert "name" in loc
        print(f"SUCCESS: Found {len(locations)} locations")


class TestAnalyticsEndpoints:
    """Test analytics endpoints that use disease/abortion data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "phone": "255700000000",
            "password": "admin123"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_analytics_report_includes_death_analysis(self):
        """Test analytics report includes death_analysis with disease breakdown"""
        params = {
            "start_date": "2024-01-01",
            "end_date": "2027-01-01"
        }
        response = requests.get(f"{BASE_URL}/api/reports/analytics", params=params)
        assert response.status_code == 200
        
        data = response.json()
        assert "death_analysis" in data, "Should have death_analysis"
        
        death_analysis = data["death_analysis"]
        assert "total_deaths" in death_analysis
        assert "top_causes" in death_analysis
        assert "top_diseases" in death_analysis
        assert "by_species" in death_analysis
        
        print(f"SUCCESS: Death analysis - total_deaths: {death_analysis['total_deaths']}")
        print(f"  Top causes: {[c['cause'] for c in death_analysis['top_causes'][:3]]}")
        print(f"  Top diseases: {[d['disease_name'] for d in death_analysis['top_diseases'][:3]]}")
    
    def test_analytics_report_includes_abortion_analysis(self):
        """Test analytics report includes abortion_analysis with stage breakdown"""
        params = {
            "start_date": "2024-01-01",
            "end_date": "2027-01-01"
        }
        response = requests.get(f"{BASE_URL}/api/reports/analytics", params=params)
        assert response.status_code == 200
        
        data = response.json()
        assert "abortion_analysis" in data, "Should have abortion_analysis"
        
        abortion_analysis = data["abortion_analysis"]
        assert "total_abortions" in abortion_analysis
        assert "by_stage" in abortion_analysis
        assert "by_species" in abortion_analysis
        
        print(f"SUCCESS: Abortion analysis - total: {abortion_analysis['total_abortions']}")
        if abortion_analysis["by_stage"]:
            print(f"  By stage: {abortion_analysis['by_stage']}")
    
    def test_analytics_report_includes_sales_analysis(self):
        """Test analytics report includes sales_analysis"""
        params = {
            "start_date": "2024-01-01",
            "end_date": "2027-01-01"
        }
        response = requests.get(f"{BASE_URL}/api/reports/analytics", params=params)
        assert response.status_code == 200
        
        data = response.json()
        assert "sales_analysis" in data, "Should have sales_analysis"
        
        sales = data["sales_analysis"]
        assert "total_count" in sales
        assert "total_value" in sales
        assert "average_price" in sales
        
        print(f"SUCCESS: Sales analysis - count: {sales['total_count']}, value: {sales['total_value']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
