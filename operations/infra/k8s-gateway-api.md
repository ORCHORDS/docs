# Kubernetes Gateway API

The Kubernetes Gateway API is a modern, extensible API for configuring network traffic in Kubernetes clusters. It provides a unified way to manage ingress, egress, and service routing with enhanced capabilities over traditional Ingress resources.

## Overview

Gateway API addresses limitations of the legacy Ingress API by offering better extensibility, cross-namespace support, and advanced routing features. It introduces three core resource types: GatewayClass, Gateway, and Route resources (including HTTPRoute).

## Key Components

### GatewayClass
GatewayClass defines a class of Gateways that can be instantiated. It acts as a template for creating Gateways with specific implementations.

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: GatewayClass
metadata:
  name: my-gateway-class
spec:
  controllerName: "example.com/gateway-controller"
```

### HTTPRoute
HTTPRoute defines how traffic should be routed based on HTTP criteria like paths, hosts, and headers.

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: HTTPRoute
metadata:
  name: example-route
spec:
  parentRefs:
  - name: my-gateway
  rules:
  - matches:
    - path:
        type: Prefix
        value: "/api"
    backendRefs:
    - name: api-service
      port: 80
```

## Advanced Features

### Cross-Namespace Routing
Gateway API supports routing across namespaces, allowing services to be referenced from different namespaces.

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: HTTPRoute
metadata:
  name: cross-namespace-route
spec:
  parentRefs:
  - name: my-gateway
    namespace: networking
  rules:
  - backendRefs:
    - name: external-service
      namespace: production
      port: 80
```

### TLS Passthrough
TLS passthrough enables direct TLS termination at the Gateway level without decrypting traffic.

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: Gateway
metadata:
  name: tls-gateway
spec:
  listeners:
  - name: https
    port: 443
    protocol: HTTPS
    tls:
      mode: Passthrough
```

## GAMMA Implementation

GAMMA (Gateway API Manager for Multi-Cluster Applications) provides enhanced management capabilities for Gateway API implementations across multiple clusters, offering centralized policy enforcement and monitoring.

## Migration from Ingress

### Key Differences
- Better cross-namespace support
- More granular routing rules
- Enhanced TLS configuration
- Improved extensibility through CRDs

### Migration Example
```yaml
# Old Ingress
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: legacy-ingress
spec:
