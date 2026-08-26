# event-sourcing-strategy

## What is Event Sourcing?

Event Sourcing is a pattern where instead of storing the current state of an entity, you store a sequence of immutable events that represent changes to that entity over time. Each event is a fact about what happened, and the current state is derived by replaying all events.

```javascript
// Example: User registration event
const userRegisteredEvent = {
  id: "event-123",
  type: "USER_REGISTERED",
  timestamp: "2023-01-01T00:00:00Z",
  payload: {
    userId: "user-456",
    email: "john@example.com",
    name: "John Doe"
  }
};

// Example: User updated event
const userUpdatedEvent = {
  id: "event-456",
  type: "USER_UPDATED",
  timestamp: "2023-01-02T00:00:00Z",
  payload: {
    userId: "user-456",
    name: "John Smith"
  }
};
```

## Append-Only Event Log

The core of event sourcing is the append-only log. Events are never modified or deleted - they're always appended to the end of a sequence. This creates an immutable history that can be replayed at any time.

```javascript
class EventStore {
  constructor() {
    this.events = [];
  }

  append(event) {
    // Always append, never modify
    this.events.push({
      ...event,
      timestamp: new Date().toISOString()
    });
  }

  getEventsForAggregate(aggregateId) {
    return this.events.filter(e => e.aggregateId === aggregateId);
  }
}
```

## Snapshot Optimization

As the event log grows, replaying all events becomes expensive. Snapshots provide a performance optimization by storing the state at specific points in time.

```javascript
class OptimizedEventStore extends EventStore {
  constructor() {
    super();
    this.snapshots = new Map(); // aggregateId -> snapshot
  }

  append(event) {
    super.append(event);

    // Create snapshot every 100 events for performance
    if (event.sequence % 100 === 0) {
      const snapshot = this.createSnapshot(event.aggregateId);
      this.snapshots.set(event.aggregateId, snapshot);
    }
  }

  getAggregateState(aggregateId) {
    const snapshot = this.snapshots.get(aggregateId);
    if (snapshot) {
      // Start with snapshot and replay only recent events
      return this.replayFromSnapshot(aggregateId, snapshot);
    }

    // Full replay for aggregates without snapshots
    return this.replayAll(aggregateId);
  }
}
```

## Replay Capabilities

One of the biggest advantages is the ability to replay events to reconstruct state or debug issues.

```javascript
class EventReplayer {
  static replay(events, initialState = {}) {
    let state = initialState;

    for (const event of events) {
      switch (event.type) {
        case "USER_REGISTERED":
          state = { ...state, ...event.payload };
          break;
        case "USER_UPDATED":
          state = { ...state, ...event.payload };
          break;
        default:
          console.warn(`Unknown event type: ${event.type}`);
      }
    }

    return state;
  }
}

// Usage
const userEvents = [
  userRegisteredEvent,
  userUpdatedEvent
];
const currentState = EventReplayer.replay(userEvents);
```

## Projections

Projections transform events into different data structures for querying and reporting.

```javascript
class UserProjection {
  constructor() {
    this.users = new Map();
  }

  apply(event) {
    switch (event.type) {
