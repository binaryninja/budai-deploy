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

# Test service details from the error log
service_id = "7814bb95-b2db-426c-88b7-e23b7c7dc3fa"
environment = "development"

print("=" * 80)
print("TESTING DEPLOYMENT TRIGGERS")
print("=" * 80)
print(f"Service ID: {service_id}")
print(f"Environment: {environment}")
print()

# Get environment ID
env_id = provider._get_environment_id(creds["railway_project_id"], environment)
print(f"Environment ID: {env_id}")
print()

# Check service details
print("Querying service details...")
try:
    query = """
    query GetService($serviceId: String!) {
        service(id: $serviceId) {
            id
            name
            source {
                repo
                image
            }
            serviceInstances(first: 5) {
                edges {
                    node {
                        id
                        environmentId
                        latestDeployment {
                            id
                            status
                            createdAt
                        }
                    }
                }
            }
        }
    }
    """
    result = provider._graphql_query(query, {"serviceId": service_id})
    service = result.get("service", {})
    source = service.get("source")
    
    print(f"✓ Service name: {service.get('name')}")
    if source:
        print(f"  Source repo: {source.get('repo', 'None')}")
        print(f"  Source image: {source.get('image', 'None')}")
    
    instances = service.get("serviceInstances", {}).get("edges", [])
    print(f"  Service instances: {len(instances)}")
    
    if instances:
        for edge in instances:
            node = edge.get("node", {})
            print(f"\n  Instance ID: {node['id']}")
            print(f"    Environment ID: {node['environmentId']}")
            deployment = node.get("latestDeployment")
            if deployment:
                print(f"    Latest deployment: {deployment['id']}")
                print(f"    Status: {deployment.get('status')}")
            else:
                print(f"    Latest deployment: None")
    else:
        print("  ⚠️  No service instances exist yet!")
        print("     Railway creates instances asynchronously after service creation.")
        print("     This is why deploy_service fails with 'Problem processing request'")
    
except Exception as e:
    print(f"✗ Failed to query service: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("SOLUTION")
print("=" * 80)
print("""
The issue: serviceInstanceDeploy mutation requires a service instance to exist.
For newly created services, the instance doesn't exist immediately.

Options:
1. Remove the automatic deployment trigger for new services
   - Let Railway auto-deploy when it's ready
   - Advantages: No errors, Railway handles it
   - Disadvantages: No immediate feedback

2. Wait for service instance to appear, then trigger deployment
   - Poll until instance exists (with timeout)
   - Then call deploy_service()
   - Disadvantages: Adds complexity and wait time

3. Use a webhook or GitHub push to trigger first deployment
   - Configure GitHub repo to trigger Railway deploys
   - Advantages: Standard Railway workflow
   - Disadvantages: Requires GitHub repo to have commits

RECOMMENDATION: Option 1 - Don't trigger deployment for new services.
Railway will automatically deploy when the service instance is ready.
Only trigger deployments for existing services when variables change.
""")
