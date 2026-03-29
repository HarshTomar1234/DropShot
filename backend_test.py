#!/usr/bin/env python3
"""
DROPSHOT Tennis Video Analytics - Backend API Testing
Tests all backend endpoints for the tennis video analytics app.
"""

import requests
import sys
import time
import tempfile
import cv2
import numpy as np
from datetime import datetime
import json
import os

class DropshotAPITester:
    def __init__(self, base_url="https://serve-analyzer.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.session = requests.Session()
        
    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        
    def run_test(self, name, method, endpoint, expected_status, data=None, files=None, timeout=30):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}" if endpoint else self.base_url
        
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=timeout)
            elif method == 'POST':
                if files:
                    response = self.session.post(url, files=files, timeout=timeout)
                else:
                    response = self.session.post(url, json=data, timeout=timeout)
            elif method == 'DELETE':
                response = self.session.delete(url, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if not success:
                details += f", Expected: {expected_status}"
                if response.text:
                    try:
                        error_data = response.json()
                        details += f", Error: {error_data.get('detail', response.text[:100])}"
                    except:
                        details += f", Response: {response.text[:100]}"
            
            self.log_test(name, success, details)
            return success, response.json() if success and response.text else {}

        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return False, {}

    def create_test_video(self, duration_sec=3, filename="test_tennis.mp4"):
        """Create a simple test video with moving objects for upload testing"""
        try:
            # Create a temporary video file
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_file.close()
            
            # Video properties
            fps = 30
            width, height = 640, 480
            total_frames = int(duration_sec * fps)
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_file.name, fourcc, fps, (width, height))
            
            for frame_num in range(total_frames):
                # Create a frame with moving tennis ball simulation
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                
                # Background (tennis court green)
                frame[:] = (34, 139, 34)  # Forest green
                
                # Moving ball (yellow-green tennis ball color)
                ball_x = int((frame_num / total_frames) * (width - 40) + 20)
                ball_y = int(height // 2 + 50 * np.sin(frame_num * 0.2))
                cv2.circle(frame, (ball_x, ball_y), 15, (0, 255, 206), -1)  # Tennis ball
                
                # Player rectangle (simulated player)
                player_x = int(width * 0.8)
                player_y = int(height * 0.7)
                cv2.rectangle(frame, (player_x-20, player_y-40), (player_x+20, player_y+40), (255, 255, 255), -1)
                
                # Court lines
                cv2.line(frame, (0, height//2), (width, height//2), (255, 255, 255), 2)
                cv2.line(frame, (width//2, 0), (width//2, height), (255, 255, 255), 2)
                
                out.write(frame)
            
            out.release()
            return temp_file.name
            
        except Exception as e:
            print(f"Failed to create test video: {e}")
            return None

    def test_basic_endpoints(self):
        """Test basic API endpoints"""
        print("\n🔍 Testing Basic Endpoints...")
        
        # Test root endpoint
        self.run_test("GET /api/ returns app info", "GET", "", 200)
        
        # Test health endpoint
        success, health_data = self.run_test("GET /api/health returns health status", "GET", "health", 200)
        if success and health_data:
            print(f"   Health Status: {health_data.get('status', 'unknown')}")
            print(f"   DB: {health_data.get('db', 'unknown')}")
            print(f"   Storage: {health_data.get('storage', 'unknown')}")
            print(f"   Active Jobs: {health_data.get('active_jobs', 0)}")

    def test_upload_functionality(self):
        """Test video upload functionality"""
        print("\n🔍 Testing Upload Functionality...")
        
        # Test valid video upload
        test_video_path = self.create_test_video(duration_sec=5)
        if test_video_path:
            try:
                with open(test_video_path, 'rb') as f:
                    files = {'file': ('test_tennis.mp4', f, 'video/mp4')}
                    success, upload_data = self.run_test(
                        "POST /api/upload accepts valid video", 
                        "POST", 
                        "upload", 
                        200, 
                        files=files,
                        timeout=60
                    )
                    
                    if success and upload_data:
                        self.test_analysis_id = upload_data.get('id')
                        print(f"   Upload ID: {self.test_analysis_id}")
                        print(f"   Status: {upload_data.get('status')}")
                        print(f"   Duration: {upload_data.get('duration_sec')}s")
                        
            except Exception as e:
                self.log_test("POST /api/upload accepts valid video", False, f"File error: {e}")
            finally:
                # Clean up test file
                try:
                    os.unlink(test_video_path)
                except:
                    pass
        
        # Test invalid file upload (non-video)
        try:
            # Create a text file disguised as video
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
                f.write(b"This is not a video file")
                f.flush()
                
                with open(f.name, 'rb') as test_file:
                    files = {'file': ('fake_video.mp4', test_file, 'text/plain')}
                    self.run_test(
                        "POST /api/upload rejects non-video files", 
                        "POST", 
                        "upload", 
                        400, 
                        files=files
                    )
                
                os.unlink(f.name)
        except Exception as e:
            self.log_test("POST /api/upload rejects non-video files", False, f"Test setup error: {e}")

    def test_analyses_endpoints(self):
        """Test analysis listing and retrieval endpoints"""
        print("\n🔍 Testing Analysis Endpoints...")
        
        # Test analyses list
        success, analyses_data = self.run_test("GET /api/analyses returns paginated list", "GET", "analyses", 200)
        if success and analyses_data:
            items = analyses_data.get('items', [])
            total = analyses_data.get('total', 0)
            pages = analyses_data.get('pages', 0)
            print(f"   Total analyses: {total}")
            print(f"   Items in page: {len(items)}")
            print(f"   Total pages: {pages}")
            
            # Store an analysis ID for further testing
            if items:
                self.existing_analysis_id = items[0].get('id')
                print(f"   Using analysis ID for testing: {self.existing_analysis_id}")
        
        # Test pagination
        self.run_test("GET /api/analyses?page=1&limit=5 pagination works", "GET", "analyses?page=1&limit=5", 200)
        
        # Test specific analysis retrieval
        if hasattr(self, 'existing_analysis_id') and self.existing_analysis_id:
            self.run_test(
                "GET /api/analyses/{id} returns analysis details", 
                "GET", 
                f"analyses/{self.existing_analysis_id}", 
                200
            )
        
        # Test invalid analysis ID
        self.run_test(
            "GET /api/analyses/{id} returns 404 for invalid ID", 
            "GET", 
            "analyses/invalid-id-12345", 
            404
        )

    def test_video_streaming(self):
        """Test video streaming endpoints"""
        print("\n🔍 Testing Video Streaming...")
        
        if hasattr(self, 'existing_analysis_id') and self.existing_analysis_id:
            # Test original video streaming
            self.run_test(
                "GET /api/analyses/{id}/original-video streams original video", 
                "GET", 
                f"analyses/{self.existing_analysis_id}/original-video", 
                200
            )
            
            # Test output video streaming (may not be ready for all analyses)
            success, _ = self.run_test(
                "GET /api/analyses/{id}/output-video streams output video", 
                "GET", 
                f"analyses/{self.existing_analysis_id}/output-video", 
                200
            )
            
            if not success:
                print("   Note: Output video may not be ready yet (analysis still processing)")

    def test_analysis_management(self):
        """Test analysis management endpoints"""
        print("\n🔍 Testing Analysis Management...")
        
        # Test retry functionality (only works on failed analyses)
        if hasattr(self, 'existing_analysis_id') and self.existing_analysis_id:
            # This will likely return 400 since the analysis isn't failed
            success, _ = self.run_test(
                "POST /api/analyses/{id}/retry handles retry requests", 
                "POST", 
                f"analyses/{self.existing_analysis_id}/retry", 
                400  # Expected to fail since analysis isn't failed
            )
            
            if not success:
                print("   Note: Retry expected to fail for non-failed analysis")

    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        print("\n🔍 Testing Rate Limiting...")
        
        # Make rapid requests to trigger rate limiting
        rate_limit_hit = False
        for i in range(12):  # Rate limit is 10 requests per 60 seconds
            try:
                response = self.session.get(f"{self.base_url}/health", timeout=5)
                if response.status_code == 429:
                    rate_limit_hit = True
                    break
                time.sleep(0.1)  # Small delay between requests
            except:
                break
        
        self.log_test("Rate limiting returns 429 after excessive requests", rate_limit_hit, 
                     "Rate limit triggered" if rate_limit_hit else "Rate limit not triggered in test")

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting DROPSHOT Backend API Tests")
        print(f"Testing against: {self.base_url}")
        print("=" * 60)
        
        start_time = time.time()
        
        # Initialize test variables
        self.existing_analysis_id = None
        self.test_analysis_id = None
        
        # Run test suites
        self.test_basic_endpoints()
        self.test_upload_functionality()
        self.test_analyses_endpoints()
        self.test_video_streaming()
        self.test_analysis_management()
        self.test_rate_limiting()
        
        # Summary
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        print(f"⏱️  Duration: {duration:.2f} seconds")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed")
            return 1

    def get_test_summary(self):
        """Get a summary of test results"""
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0,
            "test_details": self.test_results
        }

def main():
    """Main test execution"""
    tester = DropshotAPITester()
    exit_code = tester.run_all_tests()
    
    # Save detailed results
    summary = tester.get_test_summary()
    with open('/tmp/backend_test_results.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())