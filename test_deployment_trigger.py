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

# Get FULL service details
print("Fetching complete service details...")
query = """
query GetServiceDetails($serviceId: String!) {
    service(id: $serviceId) {
        id
        name
        icon
        source {
            repo
            image
        }
        serviceInstances(first: 5) {
            edges {
                node {
                    id
                    environmentId
                    source {
                        repo
                        image
                    }
                    latestDeployment {
                        id
                        status
                        createdAt
                    }
                    domains {
                        serviceDomains {
                            domain
                        }
                    }
                }
            }
        }
    }
}
"""

try:
    result = provider._graphql_query(query, {"serviceId": service_id})
    service_data = result.get("service", {})
    
    print(f"Service Name: {service_data.get('name')}")
    
    # Check source
    source = service_data.get("source")
    if source:
        print(f"Service-level Source:")
        print(f"  Repo: {source.get('repo', 'None')}")
        print(f"  Image: {source.get('image', 'None')}")
    else:
        print("Service-level Source: None")
    
    print()
    
    # Check instances
    instances = service_data.get("serviceInstances", {}).get("edges", [])
    print(f"Service Instances: {len(instances)}")
    
    target_instance = None
    for edge in instances:
        node = edge.get("node", {})
        inst_env_id = node.get("environmentId")
        inst_id = node.get("id")
        
        print(f"\n  Instance {inst_id}:")
        print(f"    Environment ID: {inst_env_id}")
        
        # Check instance-level source
        inst_source = node.get("source")
        if inst_source:
            print(f"    Instance Source:")
            print(f"      Repo: {inst_source.get('repo', 'None')}")
            print(f"      Image: {inst_source.get('image', 'None')}")
        else:
            print(f"    Instance Source: None ⚠️")
        
        # Check deployments
        latest_dep = node.get("latestDeployment")
        if latest_dep:
            print(f"    Latest Deployment: {latest_dep['id']}")
            print(f"      Status: {latest_dep.get('status')}")
        else:
            print(f"    Latest Deployment: None (no deployments yet)")
        
        if inst_env_id == env_id:
            target_instance = node
    
    if not target_instance:
        print(f"\n✗ No service instance found for environment '{environment}'")
        sys.exit(1)
    
    print()
    print("=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)
    
    # Check what might be wrong
    inst_source = target_instance.get("source")
    has_repo = inst_source and inst_source.get("repo")
    has_image = inst_source and inst_source.get("image")
    
    if not has_repo and not has_image:
        print("⚠️  ISSUE FOUND: Service instance has NO source configured!")
        print()
        print("The service instance exists but doesn't have a repo or image attached.")
        print("This is why deployments fail with 'Problem processing request'.")
        print()
        print("Solution: Manually click 'Deploy' in Railway UI once, or ensure")
        print("the service was created with a valid source_repo parameter.")
        print()
        print("Since your services were created via API with source_repo,")
        print("Railway might need time to initialize the connection.")
        print()
        print("Try waiting 10-30 seconds and running this script again.")
    elif not target_instance.get("latestDeployment"):
        print("✓ Service instance has source configured")
        print("  But no deployments have been triggered yet.")
        print()
        print("This suggests Railway is waiting for you to manually trigger")
        print("the first deployment via the UI, or it's still initializing.")
        print()
        print("RECOMMENDATION: Just let Railway auto-deploy when ready.")
        print("The service will deploy automatically when Railway finishes")
        print("connecting to the GitHub repository.")
    
except Exception as e:
    print(f"✗ Failed to query service: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
print("Railway Dashboard:")
print(f"https://railway.com/project/{creds['railway_project_id']}/service/{service_id}")
print("=" * 80)
