#!/usr/bin/env python3
"""
Test script to figure out how to properly trigger deployments on Railway.
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

print("=" * 80)
print("TESTING DEPLOYMENT TRIGGERS")
print("=" * 80)
print(f"Project ID: {creds['railway_project_id']}")
print(f"Environment: {environment}")
print()

# Get environment ID
env_id = provider._get_environment_id(creds["railway_project_id"], environment)
print(f"Environment ID: {env_id}")
print()

# List all services in the project
print("Listing all services in project...")
try:
    services = provider._list_services(creds["railway_project_id"])
    print(f"✓ Found {len(services)} services")
    print()
    
    for idx, service in enumerate(services, 1):
        print(f"{idx}. {service.get('name', 'Unnamed')} (ID: {service.get('id')})")
    
    if not services:
        print("No services found. Create a service first using the deploy script.")
        sys.exit(0)
    
    # Use the first service for testing
    test_service = services[0]
    service_id = test_service['id']
    service_name = test_service.get('name', 'unknown')
    
    print()
    print(f"Testing with service: {service_name} ({service_id})")
    print()
    
except Exception as e:
    print(f"✗ Failed to list services: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check service instance details
print("Checking for service instances...")
try:
    instance = provider._get_service_instance(service_id, env_id)
    if instance:
        print(f"✓ Service instance found: {instance['id']}")
        latest_deployment = instance.get("latestDeployment")
        if latest_deployment:
            print(f"  Latest deployment ID: {latest_deployment['id']}")
            print(f"  Status: {latest_deployment.get('status', 'unknown')}")
        else:
            print("  ⚠️  No deployments yet")
        print()
        
        # Try to trigger a deployment
        print("Attempting to trigger deployment...")
        try:
            deployment_id = provider.deploy_service(
                service_id=service_id,
                environment=environment,
                project_id=creds["railway_project_id"]
            )
            print(f"✓ SUCCESS! Deployment triggered: {deployment_id}")
        except Exception as e:
            print(f"✗ Failed to trigger deployment: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("✗ No service instance found")
        print()
        print("This means:")
        print("  - Service was just created and instance isn't ready yet")
        print("  - Railway creates service instances asynchronously")
        print("  - This is why deploy_service() fails with 'Problem processing request'")
        print()
        print("Solution: Don't trigger deployment for newly created services.")
        print("Railway will auto-deploy when the service instance is ready.")
    
except Exception as e:
    print(f"✗ Failed to check service instance: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("CONCLUSION")
print("=" * 80)
print("""
For newly created services:
- Railway creates service instances ASYNCHRONOUSLY after service creation
- The instance doesn't exist immediately
- deploy_service() mutation requires an instance to exist
- Attempting to deploy before instance exists = "Problem processing request"

Best Practice:
1. For NEW services: Skip deployment trigger
   - Railway auto-deploys when instance is ready
   - GitHub webhooks trigger deployments
   
2. For EXISTING services: Trigger deployment after variable changes
   - Instance already exists
   - deploy_service() works fine

Update deploy.py to ONLY trigger deployments for existing services!
""")
