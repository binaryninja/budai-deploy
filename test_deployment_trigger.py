#!/usr/bin/env python3
"""
Test script to diagnose and trigger deployment for a newly created Railway service.
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from installer.railway import RailwayProvider

# Load credentials
creds_file = '../credentials.json'
print(f"Loading credentials from: {creds_file}")
with open(creds_file) as f:
    creds = json.load(f)

provider = RailwayProvider(
    api_token=creds["railway_token"],
    project_id=creds["railway_project_id"]
)

environment = "development"
target_service_name = "budai-orchestrator"

print("=" * 80)
print("DETAILED SERVICE DIAGNOSTICS")
print("=" * 80)
print()

# List all services and find target
print("Finding service...")
services = provider._list_services(creds["railway_project_id"])
service = None
for svc in services:
    if svc.get('name') == target_service_name:
        service = svc
        break

if not service:
    print(f"✗ Service '{target_service_name}' not found!")
    sys.exit(1)

service_id = service['id']
print(f"✓ Found: {target_service_name}")
print(f"  Service ID: {service_id}")
print()

# Get environment ID
env_id = provider._get_environment_id(creds["railway_project_id"], environment)
print(f"Environment ID: {env_id}")
print()

# Get service details in steps (some queries fail for new services)
print("Fetching service details (basic)...")
query = """
query GetServiceBasic($serviceId: String!) {
    service(id: $serviceId) {
        id
        name
        source {
            repo
            image
        }
    }
}
"""

try:
    result = provider._graphql_query(query, {"serviceId": service_id})
    service_data = result.get("service", {})
    
    if not service_data:
        print("✗ Service not found or query failed")
        print("The service might have been deleted or is in an invalid state.")
        print()
        print("RECOMMENDATION: Delete this service and recreate it.")
        sys.exit(1)
    
    print(f"✓ Service Name: {service_data.get('name')}")
    
    # Check source
    source = service_data.get("source")
    if source:
        print(f"Service-level Source:")
        print(f"  Repo: {source.get('repo', 'None')}")
        print(f"  Image: {source.get('image', 'None')}")
    else:
        print("Service-level Source: None")
    
    print()
    
except Exception as e:
    print(f"✗ Failed to query basic service details: {e}")
    print()
    print("This service appears to be in a corrupted state.")
    print("RECOMMENDATION: Delete and recreate the service.")
    sys.exit(1)

# Now try to get service instances separately
print("Fetching service instances...")
try:
    instance = provider._get_service_instance(service_id, env_id)
    
    if not instance:
        print("✗ No service instance found for this environment")
        print()
        print("This is normal for newly created services.")
        print("Railway creates service instances asynchronously.")
        print()
        print("RECOMMENDATION: Wait 10-30 seconds for Railway to initialize,")
        print("then the service will auto-deploy when ready.")
    else:
        print(f"✓ Service Instance found: {instance['id']}")
        
        deployment = instance.get("latestDeployment")
        if deployment:
            print(f"  Latest Deployment: {deployment['id']}")
            print(f"  Status: {deployment.get('status')}")
        else:
            print(f"  Latest Deployment: None")
            print()
            print("  The service instance exists but has no deployments yet.")
            print("  This means Railway has initialized the instance but hasn't")
            print("  triggered the first deployment.")
            print()
            print("  NEXT STEP: The new serviceConnect() call in deploy.py")
            print("  should trigger the first deployment automatically.")
    
except Exception as e:
    print(f"✗ Failed to query service instances: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("Railway Dashboard:")
print(f"https://railway.com/project/{creds['railway_project_id']}/service/{service_id}")
print("=" * 80)
