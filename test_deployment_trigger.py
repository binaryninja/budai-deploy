#!/usr/bin/env python3
"""
Test script to trigger deployment for a newly created Railway service.
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
print("TESTING DEPLOYMENT TRIGGER")
print("=" * 80)
print()

# List all services
print("Listing services...")
services = provider._list_services(creds["railway_project_id"])
print(f"Found {len(services)} service(s)")
print()

if not services:
    print("No services found!")
    sys.exit(1)

for idx, svc in enumerate(services, 1):
    print(f"{idx}. {svc.get('name')} (ID: {svc['id']})")

# Use first service for testing
service = services[0]
service_id = service['id']
service_name = service.get('name', 'unknown')

print()
print(f"Testing with: {service_name}")
print(f"Service ID: {service_id}")
print()

# Get environment ID
env_id = provider._get_environment_id(creds["railway_project_id"], environment)
print(f"Environment ID: {env_id}")
print()

# Check for service instance
print("Checking for service instance...")
instance = provider._get_service_instance(service_id, env_id)

if not instance:
    print("✗ No service instance found yet")
    print()
    print("Attempting to trigger initial deployment using serviceConnect...")
    print()
    
    # Try method 1: serviceConnect with branch (might trigger deployment)
    try:
        # First, get the service source details
        query = """
        query GetService($serviceId: String!) {
            service(id: $serviceId) {
                id
                name
                source {
                    repo
                }
            }
        }
        """
        result = provider._graphql_query(query, {"serviceId": service_id})
        service_data = result.get("service", {})
        source = service_data.get("source")
        
        if source and source.get("repo"):
            repo = source["repo"]
            print(f"Service repo: {repo}")
            print("Attempting serviceConnect to trigger deployment...")
            
            connect_query = """
            mutation ServiceConnect($serviceId: String!, $branch: String, $repo: String) {
                serviceConnect(
                    id: $serviceId
                    input: { branch: $branch, repo: $repo }
                ) {
                    id
                }
            }
            """
            provider._graphql_query(
                connect_query,
                {
                    "serviceId": service_id,
                    "branch": "master",
                    "repo": repo
                }
            )
            print("✓ serviceConnect completed - this may trigger a deployment")
        else:
            print("⚠️  No repo source found - service might use Docker image")
            
    except Exception as e:
        print(f"serviceConnect failed: {e}")
    
    print()
    print("Waiting a moment for service instance to initialize...")
    import time
    time.sleep(3)
    
    instance = provider._get_service_instance(service_id, env_id)
    if not instance:
        print("Still no instance. Trying deploymentTrigger mutation...")
        
        # Try method 2: Use deploymentTrigger if it exists
        trigger_query = """
        mutation TriggerDeploy($environmentId: String!, $projectId: String!, $serviceId: String!) {
            deploymentTrigger(
                environmentId: $environmentId
                projectId: $projectId
                serviceId: $serviceId
            ) {
                id
            }
        }
        """
        try:
            result = provider._graphql_query(
                trigger_query,
                {
                    "environmentId": env_id,
                    "projectId": creds["railway_project_id"],
                    "serviceId": service_id
                }
            )
            print(f"✓ deploymentTrigger succeeded: {result}")
        except Exception as e:
            print(f"deploymentTrigger failed: {e}")

if instance:
    print("✓ Service instance exists!")
    print(f"  Instance ID: {instance['id']}")
    
    deployment = instance.get("latestDeployment")
    if deployment:
        print(f"  Latest deployment: {deployment['id']}")
        print(f"  Status: {deployment.get('status')}")
    else:
        print("  No deployments yet - attempting to trigger...")
        
        try:
            deployment_id = provider.deploy_service(
                service_id=service_id,
                environment=environment
            )
            print(f"✓ Deployment triggered: {deployment_id}")
        except Exception as e:
            print(f"✗ deploy_service failed: {e}")

print()
print("=" * 80)
print("Check Railway dashboard:")
print(f"https://railway.com/project/{creds['railway_project_id']}/service/{service_id}")
print("=" * 80)
