#!/usr/bin/env python3
"""
Test script to verify all the bug fixes work correctly.
Run this after setting up the virtual environment and installing dependencies.

Usage:
    python test_fixes.py
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def print_test(name):
    print(f"\n🧪 Testing: {name}")
    print("-" * 50)

def test_health():
    print_test("Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_denomination_validation():
    print_test("Denomination Validation (Fix #1)")
    print("Testing change breakdown with 1 and 2 INR denominations...")
    
    try:
        # Test change that requires 1 and 2 INR coins
        response = requests.get(f"{BASE_URL}/purchase/change-breakdown?change=18")
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Change breakdown for 18: {result}")
        
        # Should include 10, 5, 2, 1 coins
        denominations = result.get("denominations", {})
        has_small_denominations = "1" in denominations or "2" in denominations
        print(f"✅ Contains 1 or 2 INR coins: {has_small_denominations}")
        return has_small_denominations
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_zero_price_validation():
    print_test("Zero Price Validation (Fix #2)")
    
    try:
        # First create a slot
        slot_data = {"code": "TEST1", "capacity": 10}
        slot_response = requests.post(f"{BASE_URL}/slots", json=slot_data)
        
        if slot_response.status_code != 201:
            print("❌ Failed to create test slot")
            return False
        
        slot_id = slot_response.json()["id"]
        print(f"Created test slot: {slot_id}")
        
        # Try to create item with 0 price (should fail)
        item_data = {"name": "Free Item", "price": 0, "quantity": 1}
        response = requests.post(f"{BASE_URL}/slots/{slot_id}/items", json=item_data)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
        
        # Should return 422 (validation error)
        success = response.status_code == 422
        print(f"✅ Correctly rejected zero price: {success}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/slots/{slot_id}")
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_slot_deletion_with_items():
    print_test("Slot Deletion with Items (Fix #4)")
    
    try:
        # Create a slot
        slot_data = {"code": "TEST2", "capacity": 10}
        slot_response = requests.post(f"{BASE_URL}/slots", json=slot_data)
        slot_id = slot_response.json()["id"]
        print(f"Created test slot: {slot_id}")
        
        # Add an item to the slot
        item_data = {"name": "Test Item", "price": 10, "quantity": 1}
        item_response = requests.post(f"{BASE_URL}/slots/{slot_id}/items", json=item_data)
        print(f"Added item to slot")
        
        # Try to delete slot with items (should fail)
        response = requests.delete(f"{BASE_URL}/slots/{slot_id}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
        
        success = response.status_code == 400
        print(f"✅ Correctly prevented deletion of slot with items: {success}")
        
        # Cleanup - remove items first, then slot
        requests.delete(f"{BASE_URL}/slots/{slot_id}/items")
        requests.delete(f"{BASE_URL}/slots/{slot_id}")
        
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_capacity_logic():
    print_test("Capacity Logic (Fix #5 - CRITICAL)")
    
    try:
        # Create a slot with small capacity
        slot_data = {"code": "TEST3", "capacity": 3}
        slot_response = requests.post(f"{BASE_URL}/slots", json=slot_data)
        slot_id = slot_response.json()["id"]
        print(f"Created test slot with capacity 3: {slot_id}")
        
        # Add items up to capacity (should succeed)
        item_data = {"name": "Test Item", "price": 10, "quantity": 3}
        response = requests.post(f"{BASE_URL}/slots/{slot_id}/items", json=item_data)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
        
        success = response.status_code == 201
        print(f"✅ Successfully added items up to capacity: {success}")
        
        # Try to add more items (should fail)
        item_data2 = {"name": "Extra Item", "price": 10, "quantity": 1}
        response2 = requests.post(f"{BASE_URL}/slots/{slot_id}/items", json=item_data2)
        
        capacity_check = response2.status_code == 400
        print(f"✅ Correctly rejected exceeding capacity: {capacity_check}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/slots/{slot_id}/items")
        requests.delete(f"{BASE_URL}/slots/{slot_id}")
        
        return success and capacity_check
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_bulk_operations():
    print_test("Bulk Operations (Fix #5)")
    
    try:
        # Create a slot
        slot_data = {"code": "TEST4", "capacity": 5}
        slot_response = requests.post(f"{BASE_URL}/slots", json=slot_data)
        slot_id = slot_response.json()["id"]
        print(f"Created test slot: {slot_id}")
        
        # Bulk add items within capacity
        bulk_data = {
            "items": [
                {"name": "Item 1", "price": 10, "quantity": 2},
                {"name": "Item 2", "price": 15, "quantity": 2}
            ]
        }
        response = requests.post(f"{BASE_URL}/slots/{slot_id}/items/bulk", json=bulk_data)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        success = response.status_code == 200
        print(f"✅ Bulk add within capacity succeeded: {success}")
        
        # Try to bulk add items that would exceed capacity
        bulk_data2 = {
            "items": [
                {"name": "Item 3", "price": 20, "quantity": 5}  # Would exceed capacity
            ]
        }
        response2 = requests.post(f"{BASE_URL}/slots/{slot_id}/items/bulk", json=bulk_data2)
        
        capacity_check = response2.status_code == 400
        print(f"✅ Correctly rejected bulk add exceeding capacity: {capacity_check}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/slots/{slot_id}/items")
        requests.delete(f"{BASE_URL}/slots/{slot_id}")
        
        return success and capacity_check
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🔧 Vending Machine API - Bug Fix Verification")
    print("=" * 60)
    print("Make sure the API is running on http://127.0.0.1:8000")
    print("Run: uvicorn app.main:app --reload")
    print("=" * 60)
    
    # Wait a moment for user to start the API if needed
    input("Press Enter to start testing (make sure API is running)...")
    
    tests = [
        ("Health Check", test_health),
        ("Denomination Validation", test_denomination_validation),
        ("Zero Price Validation", test_zero_price_validation),
        ("Slot Deletion with Items", test_slot_deletion_with_items),
        ("Capacity Logic (CRITICAL FIX)", test_capacity_logic),
        ("Bulk Operations", test_bulk_operations),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            time.sleep(1)  # Small delay between tests
        except KeyboardInterrupt:
            print("\n❌ Testing interrupted by user")
            break
        except Exception as e:
            print(f"❌ Test {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"Results: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Bug fixes verified successfully.")
    else:
        print("⚠️  Some tests failed. Check the API implementation.")

if __name__ == "__main__":
    main()