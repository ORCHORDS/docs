# strangler-fig

The Strangler Fig Pattern is a practical approach to legacy system migration where you gradually replace an old system with a new one, rather than doing a big bang replacement. The pattern gets its name from how a strangler fig grows around its host tree, slowly taking over its space.

## Incremental Replacement

Instead of rewriting everything at once, implement the strangler fig pattern by incrementally replacing functionality. Start with low-risk features and work toward core business logic. For example, if you have an old order processing system, begin by routing new orders to the new system while keeping existing orders in the legacy system.

```python
# Legacy system handling
def process_order_legacy(order_id):
    # Old code path
    return legacy_processor.process(order_id)

# New system handling
def process_order_new(order_id):
    # New code path
    return new_processor.process(order_id)

# Gradual migration strategy
def process_order(order_id):
    if should_use_new_system(order_id):
        return process_order_new(order_id)
    else:
        return process_order_legacy(order_id)
```

## Facade Routing

The facade pattern is essential for implementing the strangler fig. Create a routing layer that decides which system handles each request:

```java
public class OrderServiceFacade {
    private LegacyOrderService legacyService;
    private NewOrderService newService;

    public OrderResponse processOrder(OrderRequest request) {
        // Route based on business rules, time, or feature flags
        if (isFeatureEnabled("new-order-processing") &&
            isNewCustomer(request.getCustomerId())) {
            return newService.process(request);
        }
        return legacyService.process(request);
    }
}
```

## Coexistence

Both systems must run simultaneously during the transition period. This requires careful attention to data consistency and shared resources:

```python
// Data synchronization example
public class OrderSyncService {
    public void syncOrder(Order order) {
        // Update both systems
        legacySystem.update(order);
        newSystem.update(order);

        // Handle conflicts appropriately
        if (legacySystem.hasConflicts(order)) {
            resolveConflict(order);
        }
    }
}
```

## Risk Reduction

The strangler fig pattern dramatically reduces migration risks by allowing gradual transition:

- **Rollback capability**: If new system fails, quickly switch back to legacy
- **Gradual user adoption**: Users experience minimal disruption
- **Testing flexibility**: Can test new features with subset of users
- **Monitoring**: Easy to detect issues in real-time

## Migration Steps

1. **Identify core functionality** to migrate first (start with non-critical features)
2. **Create facade layer** for routing decisions
3. **Implement feature flags** for gradual rollout
4. **Monitor performance** and error rates closely
5. **Gradually increase traffic** to new system
6. **Remove legacy components** once fully migrated

## When to use

Use the strangler fig pattern when:
- Legacy system is stable but needs modernization
- Business cannot afford downtime or major disruption
- You need to migrate complex, interdependent systems
- Team lacks resources for big bang rewrite
- Requirements are unclear and need iterative development
- Data migration is complex and risky

## When NOT to use

Avoid this pattern when:
- System is already obsolete and will be replaced anyway
- Migration timeline is extremely tight (no room for gradual approach)
- Legacy system has no shared data or integration points
- Team lacks experience with incremental approaches
- Business requires immediate feature parity
- Technical debt is so severe that rewrite is cheaper than maintenance

## Real Tradeoffs

The main tradeoff is **complexity**: you maintain two systems simultaneously, increasing operational overhead. However, this complexity pays off through reduced risk and business continuity.

## Common Gotchas

1. **Data consistency issues** - Both systems must maintain synchronized data
2. **Performance degradation
