# azure-app-service-patterns

**Issue:** Azure App Service production patterns for scaling, deployment slots, and health monitoring
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deployments cause downtime, auto-scale not triggering correctly, or health probes failing silently.

## Pattern / Solution
```hcl
resource "azurerm_service_plan" "main" {
  name                = "prod-plan"
  resource_group_name = azurerm_resource_group.main.name
  location            = "East US"
  os_type             = "Linux"
  sku_name            = "P2v3"   # Premium v3 for VNET integration
}

resource "azurerm_linux_web_app" "api" {
  name                = "my-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_service_plan.main.location
  service_plan_id     = azurerm_service_plan.main.id

  site_config {
    always_on          = true
    health_check_path  = "/health"
    health_check_eviction_time_in_min = 5

    application_stack {
      node_version = "20-lts"
    }
  }

  app_settings = {
    WEBSITE_RUN_FROM_PACKAGE = "1"
    NODE_ENV                 = "production"
  }

  identity { type = "SystemAssigned" }
}

# Deployment slot for blue/green
resource "azurerm_linux_web_app_slot" "staging" {
  name           = "staging"
  app_service_id = azurerm_linux_web_app.api.id
  site_config { health_check_path = "/health" }
}
```

Swap slots after validation:
```bash
az webapp deployment slot swap \
  --resource-group prod-rg \
  --name my-api \
  --slot staging \
  --target-slot production
```

Auto-scale rule:
```bash
az monitor autoscale create \
  --resource-group prod-rg \
  --resource my-api \
  --resource-type Microsoft.Web/sites \
  --min-count 2 --max-count 20 --count 2

az monitor autoscale rule create \
  --autoscale-name my-api \
  --condition "CpuPercentage > 70 avg 5m" \
  --scale out 2
```

## Gotchas
- `WEBSITE_RUN_FROM_PACKAGE=1` mounts zip as read-only — cannot write to `/home` at runtime
- Slot swapping swaps app settings marked as "slot setting" independently of non-slot settings
- Always On must be enabled to prevent idle shutdown on Basic+ plans (not available on Free/Shared)
- Health check eviction removes unhealthy instances from load balancer but does not restart them

## Related
- `load-balancer-health-checks.md`
- `auto-scaling-policies.md`
- `azure-cosmos-db-patterns.md`
