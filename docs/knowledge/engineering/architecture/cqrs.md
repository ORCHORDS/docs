# CQRS

CQRS (Command Query Responsibility Segregation) is an architectural pattern that separates read and write operations into distinct models. Instead of having one model that handles both commands (writes) and queries (reads), you split them into separate entities.

## Core Concepts

The fundamental idea is that commands modify data while queries retrieve it. This separation allows for optimized models tailored to each operation type.

```javascript
// Traditional approach - single model
class User {
  constructor(name, email) {
    this.name = name;
    this.email = email;
  }

  updateEmail(newEmail) {
    this.email = newEmail;
    // Save to database
  }

  getEmail() {
    return this.email;
  }
}

// CQRS approach - separate models
class UserCommandModel {
  updateEmail(userId, newEmail) {
    // Handle command logic
    return { userId, newEmail, timestamp: Date.now() };
  }
}

class UserQueryModel {
  getUserById(userId) {
    // Optimized for read performance
    return database.find({ id: userId });
  }
}
```

## Event Store

CQRS relies heavily on event sourcing. Instead of storing current state, you store a sequence of events that describe changes to the system.

```javascript
// Event store implementation
class EventStore {
  constructor() {
    this.events = [];
  }

  append(event) {
    this.events.push({
      ...event,
      timestamp: Date.now()
    });
  }

  getEventsForAggregate(aggregateId) {
    return this.events.filter(e => e.aggregateId === aggregateId);
  }
}

// Example events
const events = [
  { type: 'UserCreated', aggregateId: 'user-123', data: { name: 'John' } },
  { type: 'EmailUpdated', aggregateId: 'user-123', data: { email: 'john@example.com' } }
];
```

## Projections

Projections transform events into read-optimized views. They listen to the event store and maintain materialized views.

```javascript
class UserProjection {
  constructor(eventStore, repository) {
    this.eventStore = eventStore;
    this.repository = repository;
    this.listenToEvents();
  }

  listenToEvents() {
    this.eventStore.on('event', (event) => {
      if (event.type === 'UserCreated') {
        this.createUserView(event);
      } else if (event.type === 'EmailUpdated') {
        this.updateUserView(event);
      }
    });
  }

  createUserView(event) {
    const userView = {
      id: event.aggregateId,
      name: event.data.name,
      email: null,
      createdAt: event.timestamp
    };
    this.repository.save(userView);
  }

  updateUserView(event) {
    const userView = this.repository.findById(event.aggregateId);
    if (userView) {
      userView.email = event.data.email;
      userView.updatedAt = event.timestamp;
      this.repository.save(userView);
    }
  }
}
```

## Materialized Views

Materialized views are pre-computed read models that provide optimized access patterns for specific queries.

```javascript
// Materialized view for user search
class UserSearchView {
  constructor() {
    this.index = new Map();
  }

  updateFromEvent(event) {
    if (event.type === 'UserCreated') {
      this.index.set(event.aggregateId, {
        id: event.aggregateId,
        name: event.data.name,
        email: event.data.email,
        searchableText: `${event.data.name} ${event.data.email}`
      });
    }
  }

  search(query) {
    return Array.from(this.index.values())
      .filter(user => user.searchableText.toLowerCase().includes(query.toLowerCase()));
  }
}
```

## Real Implementation Example

```javascript
