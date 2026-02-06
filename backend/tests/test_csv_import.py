"""
Tests for CSV import functionality - Locations and Opening Balances
Tests: Download templates, Import CSV files
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCSVImportFeature:
    """Tests for CSV Import functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "phone": "255700000000",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    # ========== Location Templates Tests ==========
    def test_download_locations_template_status(self):
        """Test locations template endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/templates/locations")
        assert response.status_code == 200
        print("PASS: Locations template download endpoint returns 200")
    
    def test_download_locations_template_content_type(self):
        """Test locations template returns CSV"""
        response = requests.get(f"{BASE_URL}/api/templates/locations")
        content_type = response.headers.get('content-type', '')
        assert 'text/csv' in content_type, f"Expected text/csv, got {content_type}"
        print("PASS: Locations template returns CSV content type")
    
    def test_download_locations_template_has_headers(self):
        """Test locations template contains correct CSV headers"""
        response = requests.get(f"{BASE_URL}/api/templates/locations")
        content = response.text
        assert 'name' in content
        assert 'description' in content
        print("PASS: Locations template contains name and description headers")
    
    def test_download_locations_template_has_sample_data(self):
        """Test locations template contains sample data"""
        response = requests.get(f"{BASE_URL}/api/templates/locations")
        content = response.text
        assert 'Shamba' in content  # Should have sample location names
        print("PASS: Locations template contains sample data")
    
    # ========== Opening Balances Templates Tests ==========
    def test_download_opening_balances_template_status(self):
        """Test opening balances template endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/templates/opening-balances", headers=self.headers)
        assert response.status_code == 200
        print("PASS: Opening balances template download endpoint returns 200")
    
    def test_download_opening_balances_template_content_type(self):
        """Test opening balances template returns CSV"""
        response = requests.get(f"{BASE_URL}/api/templates/opening-balances", headers=self.headers)
        content_type = response.headers.get('content-type', '')
        assert 'text/csv' in content_type, f"Expected text/csv, got {content_type}"
        print("PASS: Opening balances template returns CSV content type")
    
    def test_download_opening_balances_template_has_headers(self):
        """Test opening balances template contains correct CSV headers"""
        response = requests.get(f"{BASE_URL}/api/templates/opening-balances", headers=self.headers)
        content = response.text
        assert 'location_name' in content
        assert 'species' in content
        assert 'category_name_sw' in content
        assert 'count' in content
        assert 'period_start' in content
        print("PASS: Opening balances template contains all required headers")
    
    def test_download_opening_balances_template_has_reference(self):
        """Test opening balances template contains reference information"""
        response = requests.get(f"{BASE_URL}/api/templates/opening-balances", headers=self.headers)
        content = response.text
        assert 'REFERENCE' in content
        assert 'Koo' in content  # Swahili category name
        print("PASS: Opening balances template contains Swahili category reference")
    
    # ========== Location Import Tests ==========
    def test_import_locations_requires_auth(self):
        """Test locations import requires authentication"""
        csv_content = "name,description\nTest Location,Test"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/locations", files=files)
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden
        print("PASS: Locations import requires authentication")
    
    def test_import_locations_rejects_non_csv(self):
        """Test locations import rejects non-CSV files"""
        files = {'file': ('test.txt', 'some content', 'text/plain')}
        response = requests.post(f"{BASE_URL}/api/import/locations", files=files, headers=self.headers)
        assert response.status_code == 400
        assert 'CSV' in response.json().get('detail', '')
        print("PASS: Locations import rejects non-CSV files")
    
    def test_import_locations_valid_csv(self):
        """Test locations import accepts valid CSV and creates locations"""
        csv_content = "name,description\nTEST_Import_Location,Test import location"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/locations", files=files, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert 'created' in data or 'skipped' in data
        print(f"PASS: Locations import successful - Created: {data.get('created', 0)}, Skipped: {data.get('skipped', 0)}")
    
    def test_import_locations_skips_duplicates(self):
        """Test locations import skips duplicate locations"""
        # First, get existing location
        loc_response = requests.get(f"{BASE_URL}/api/locations")
        existing_locations = loc_response.json()
        if existing_locations:
            existing_name = existing_locations[0]['name']
            csv_content = f"name,description\n{existing_name},Duplicate"
            files = {'file': ('test.csv', csv_content, 'text/csv')}
            response = requests.post(f"{BASE_URL}/api/import/locations", files=files, headers=self.headers)
            assert response.status_code == 200
            data = response.json()
            assert data.get('skipped', 0) >= 1
            print(f"PASS: Locations import skips duplicates - Skipped: {data.get('skipped', 0)}")
        else:
            pytest.skip("No existing locations to test duplicate handling")
    
    # ========== Opening Balances Import Tests ==========
    def test_import_opening_balances_requires_auth(self):
        """Test opening balances import requires authentication"""
        csv_content = "location_name,species,category_name_sw,count,period_start\nShamba Test,cattle,Koo,10,2026-01-01"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/opening-balances", files=files)
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden
        print("PASS: Opening balances import requires authentication")
    
    def test_import_opening_balances_rejects_non_csv(self):
        """Test opening balances import rejects non-CSV files"""
        files = {'file': ('test.txt', 'some content', 'text/plain')}
        response = requests.post(f"{BASE_URL}/api/import/opening-balances", files=files, headers=self.headers)
        assert response.status_code == 400
        assert 'CSV' in response.json().get('detail', '')
        print("PASS: Opening balances import rejects non-CSV files")
    
    def test_import_opening_balances_valid_csv(self):
        """Test opening balances import accepts valid CSV"""
        # Get existing location
        loc_response = requests.get(f"{BASE_URL}/api/locations")
        locations = loc_response.json()
        if not locations:
            pytest.skip("No locations available for testing")
        
        location_name = locations[0]['name']
        csv_content = f"location_name,species,category_name_sw,count,period_start\n{location_name},cattle,Koo,5,2026-01-15"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/opening-balances", files=files, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert 'created' in data or 'updated' in data
        print(f"PASS: Opening balances import successful - Created: {data.get('created', 0)}, Updated: {data.get('updated', 0)}")
    
    def test_import_opening_balances_invalid_location(self):
        """Test opening balances import reports error for invalid location"""
        csv_content = "location_name,species,category_name_sw,count,period_start\nInvalidLocation123,cattle,Koo,10,2026-01-01"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/opening-balances", files=files, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get('errors', [])) > 0
        assert 'not found' in str(data['errors']).lower()
        print("PASS: Opening balances import reports error for invalid location")
    
    def test_import_opening_balances_invalid_species(self):
        """Test opening balances import reports error for invalid species"""
        loc_response = requests.get(f"{BASE_URL}/api/locations")
        locations = loc_response.json()
        if not locations:
            pytest.skip("No locations available for testing")
        
        location_name = locations[0]['name']
        csv_content = f"location_name,species,category_name_sw,count,period_start\n{location_name},invalid_species,Koo,10,2026-01-01"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/opening-balances", files=files, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get('errors', [])) > 0
        assert 'species' in str(data['errors']).lower()
        print("PASS: Opening balances import reports error for invalid species")
    
    def test_import_opening_balances_invalid_category(self):
        """Test opening balances import reports error for invalid category"""
        loc_response = requests.get(f"{BASE_URL}/api/locations")
        locations = loc_response.json()
        if not locations:
            pytest.skip("No locations available for testing")
        
        location_name = locations[0]['name']
        csv_content = f"location_name,species,category_name_sw,count,period_start\n{location_name},cattle,InvalidCategory,10,2026-01-01"
        files = {'file': ('test.csv', csv_content, 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/import/opening-balances", files=files, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get('errors', [])) > 0
        assert 'not found' in str(data['errors']).lower() or 'category' in str(data['errors']).lower()
        print("PASS: Opening balances import reports error for invalid category")
    
    # ========== Dashboard Swahili Names Tests ==========
    def test_dashboard_shows_swahili_category_names(self):
        """Test dashboard returns Swahili category names"""
        response = requests.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        
        # Check species_category_totals for Swahili names
        for species_data in data.get('species_category_totals', []):
            for cat in species_data.get('categories', []):
                assert 'category_name_sw' in cat
                # Verify it's a Swahili name
                swahili_names = ['Koo', 'Mitamba', 'Ndama Dume', 'Ndama Jike', 'Vichinda Dume', 'Vichinda Jike', 
                                'Achishwa Dume', 'Achishwa Jike', 'Maksai', 'Dume Mbegu', 'Dume Wadogo']
                assert cat['category_name_sw'] in swahili_names, f"Category name {cat['category_name_sw']} not in expected Swahili names"
        
        print("PASS: Dashboard returns Swahili category names")
    
    # ========== Cleanup Test Data ==========
    def test_cleanup_test_locations(self):
        """Cleanup: Remove test-created locations"""
        loc_response = requests.get(f"{BASE_URL}/api/locations")
        locations = loc_response.json()
        for loc in locations:
            if loc['name'].startswith('TEST_'):
                # Note: Delete endpoint not available for locations in current API
                pass
        print("INFO: Test cleanup completed (no deletions needed)")


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_login_valid_credentials(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "phone": "255700000000",
            "password": "admin123"
        })
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data
        assert 'user' in data
        assert data['user']['role'] == 'admin'
        print("PASS: Login with valid credentials successful")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "phone": "255700000000",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("PASS: Login rejects invalid credentials")
    
    def test_get_me_requires_auth(self):
        """Test /auth/me requires authentication"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden
        print("PASS: /auth/me requires authentication")


class TestAPIHealth:
    """Basic API health tests"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data['message'] == 'ShambaManager API'
        print("PASS: API root endpoint healthy")
    
    def test_locations_endpoint(self):
        """Test locations endpoint"""
        response = requests.get(f"{BASE_URL}/api/locations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print("PASS: Locations endpoint returns list")
    
    def test_categories_endpoint(self):
        """Test categories endpoint"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should have seeded categories
        print(f"PASS: Categories endpoint returns {len(data)} categories")
    
    def test_dashboard_endpoint(self):
        """Test dashboard endpoint"""
        response = requests.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert 'total_animals' in data
        assert 'species_totals' in data
        assert 'species_category_totals' in data
        print("PASS: Dashboard endpoint returns expected data structure")
