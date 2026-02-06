#!/usr/bin/env python3
"""
Backend API Testing for ShambaManager Livestock Management System
Tests all endpoints with the provided admin credentials
"""

import requests
import sys
from datetime import datetime, date
import json

class ShambaManagerAPITester:
    def __init__(self, base_url="https://herd-analytics.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.admin_user = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Test data
        self.admin_phone = "255700000000"
        self.admin_password = "admin123"

    def log_result(self, test_name, success, status_code=None, error=None, data=None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "status_code": status_code,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        if data:
            result["data"] = data
        self.test_results.append(result)

    def run_test(self, name, method, endpoint, expected_status, data=None, auth_required=True):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {method} {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    self.log_result(name, True, response.status_code, None, response_data)
                    return success, response_data
                except:
                    self.log_result(name, True, response.status_code, None, None)
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get('detail', str(error_data))
                except:
                    pass
                print(f"   Error: {error_msg}")
                self.log_result(name, False, response.status_code, error_msg, None)
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.log_result(name, False, None, str(e), None)
            return False, {}

    def test_health_check(self):
        """Test basic API health"""
        return self.run_test("API Health Check", "GET", "", 200, auth_required=False)

    def test_auth_login(self):
        """Test login with admin credentials"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"phone": self.admin_phone, "password": self.admin_password},
            auth_required=False
        )
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.admin_user = response.get('user')
            print(f"   Logged in as: {self.admin_user.get('name', 'Unknown')} ({self.admin_user.get('role', 'Unknown')})")
            return True
        return False

    def test_auth_me(self):
        """Test getting current user info"""
        success, response = self.run_test("Get Current User", "GET", "auth/me", 200)
        return success

    def test_locations_crud(self):
        """Test locations CRUD operations"""
        results = []
        
        # List locations
        success, locations = self.run_test("List Locations", "GET", "locations", 200)
        results.append(success)
        initial_location_count = len(locations) if success else 0
        
        # Create location
        test_location_data = {
            "name": f"Test Location {datetime.now().strftime('%H%M%S')}",
            "description": "Test location for API testing"
        }
        success, new_location = self.run_test(
            "Create Location", "POST", "locations", 200, test_location_data
        )
        results.append(success)
        location_id = new_location.get('id') if success else None
        
        if location_id:
            # Get specific location
            success, _ = self.run_test(
                "Get Location", "GET", f"locations/{location_id}", 200
            )
            results.append(success)
            
            # Update location
            update_data = {"description": "Updated test location description"}
            success, _ = self.run_test(
                "Update Location", "PUT", f"locations/{location_id}", 200, update_data
            )
            results.append(success)
        
        return all(results)

    def test_categories(self):
        """Test categories listing"""
        success, categories = self.run_test("List Categories", "GET", "categories", 200)
        if success:
            print(f"   Found {len(categories)} categories")
            species_counts = {}
            for cat in categories:
                species = cat.get('species', 'unknown')
                species_counts[species] = species_counts.get(species, 0) + 1
            print(f"   Species distribution: {species_counts}")
        return success

    def test_opening_balances(self):
        """Test opening balances operations"""
        results = []
        
        # List opening balances
        success, balances = self.run_test("List Opening Balances", "GET", "opening-balances", 200)
        results.append(success)
        
        # Test creating opening balance (requires location and category)
        # First get locations and categories
        _, locations = self.run_test("Get Locations for Balance", "GET", "locations", 200)
        _, categories = self.run_test("Get Categories for Balance", "GET", "categories", 200)
        
        if locations and categories:
            location_id = locations[0]['id']
            category = categories[0]  # Get first category
            
            balance_data = {
                "location_id": location_id,
                "species": category['species'],
                "category_id": category['id'],
                "count": 10,
                "period_start": date.today().isoformat()
            }
            
            success, _ = self.run_test(
                "Create Opening Balance", "POST", "opening-balances", 200, balance_data
            )
            results.append(success)
        
        return all(results)

    def test_stock_levels(self):
        """Test stock levels listing"""
        success, stock_levels = self.run_test("List Stock Levels", "GET", "stock-levels", 200)
        if success:
            print(f"   Found {len(stock_levels)} stock level entries")
        return success

    def test_daily_logs(self):
        """Test daily logs operations"""
        results = []
        
        # List daily logs
        success, logs = self.run_test("List Daily Logs", "GET", "daily-logs", 200)
        results.append(success)
        
        # Test creating daily log with events
        _, locations = self.run_test("Get Locations for Log", "GET", "locations", 200)
        _, categories = self.run_test("Get Categories for Log", "GET", "categories", 200)
        
        if locations and categories:
            location_id = locations[0]['id']
            category = categories[0]
            
            log_data = {
                "location_id": location_id,
                "log_date": date.today().isoformat(),
                "notes": "Test daily log from API testing",
                "events": [
                    {
                        "event_type": "birth",
                        "species": category['species'],
                        "category_id": category['id'],
                        "count": 2,
                        "notes": "Test birth event",
                        "is_stock_event": True
                    }
                ]
            }
            
            success, new_log = self.run_test(
                "Create Daily Log with Events", "POST", "daily-logs", 200, log_data
            )
            results.append(success)
            
            log_id = new_log.get('id') if success else None
            if log_id:
                # Get specific log
                success, _ = self.run_test(
                    "Get Daily Log", "GET", f"daily-logs/{log_id}", 200
                )
                results.append(success)
        
        return all(results)

    def test_dashboard(self):
        """Test dashboard data"""
        success, dashboard = self.run_test("Get Dashboard", "GET", "dashboard", 200)
        if success:
            print(f"   Total Animals: {dashboard.get('total_animals', 0)}")
            print(f"   Total Locations: {dashboard.get('total_locations', 0)}")
            print(f"   Pending Logs Today: {dashboard.get('pending_logs_today', 0)}")
            print(f"   Species Totals: {len(dashboard.get('species_totals', []))}")
        return success

    def test_users_admin(self):
        """Test users management (admin only)"""
        results = []
        
        # List users
        success, users = self.run_test("List Users (Admin)", "GET", "users", 200)
        results.append(success)
        if success:
            print(f"   Found {len(users)} users")
        
        return all(results)

    def test_reports(self):
        """Test reports endpoints"""
        results = []
        
        # Daily report
        today = date.today().isoformat()
        success, _ = self.run_test("Daily Report", "GET", f"reports/daily?report_date={today}", 200)
        results.append(success)
        
        # Range report
        success, _ = self.run_test(
            "Range Report", "GET", 
            f"reports/range?start_date={today}&end_date={today}", 200
        )
        results.append(success)
        
        return all(results)

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting ShambaManager API Tests")
        print("=" * 50)
        
        # Health check
        if not self.test_health_check():
            print("❌ Health check failed - stopping tests")
            return False
        
        # Authentication
        if not self.test_auth_login():
            print("❌ Login failed - stopping tests")
            return False
            
        self.test_auth_me()
        
        # Core functionality tests
        self.test_categories()
        self.test_locations_crud()
        self.test_opening_balances()
        self.test_stock_levels()
        self.test_daily_logs()
        self.test_dashboard()
        self.test_users_admin()
        self.test_reports()
        
        # Print results
        print("\n" + "=" * 50)
        print("📊 Test Results Summary")
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        # Show failed tests
        failed_tests = [t for t in self.test_results if not t['success']]
        if failed_tests:
            print(f"\n❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   - {test['test']}: {test.get('error', 'Unknown error')}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = ShambaManagerAPITester()
    success = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/backend_test_results.json', 'w') as f:
        json.dump(tester.test_results, f, indent=2)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())