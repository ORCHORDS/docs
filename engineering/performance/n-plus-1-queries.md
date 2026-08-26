# N+1 Queries

## What are N+1 Queries?

N+1 queries occur when your application makes one initial query to fetch a collection of records, then makes N additional queries (one for each record) to fetch related data. This pattern creates severe performance bottlenecks and can slow down your application by orders of magnitude.

```javascript
// Bad: N+1 query pattern
const users = await User.findAll();
for (const user of users) {
  const posts = await Post.findAll({ where: { userId: user.id } });
  // This executes a separate query for each user!
}
```

## Detection Methods

### Browser DevTools Profiling
Use browser developer tools to monitor network requests. Look for repeated queries with similar patterns:
- Open Chrome DevTools → Network tab
- Filter by XHR/Fetch requests
- Look for identical queries with different parameters
- Monitor request duration and frequency

### Database Query Logging
Enable query logging in your ORM to identify problematic patterns:

```javascript
// Sequelize example
const sequelize = new Sequelize('database', 'username', 'password', {
  logging: console.log, // Logs all queries
});

// Django example
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'mydb',
        'LOGGING': True,
    }
}
```

### Application Monitoring Tools
Use tools like New Relic, Datadog, or custom logging to track query patterns and identify performance bottlenecks.

## Solutions

### ORM Eager Loading
Preload related data in a single query using eager loading:

```javascript
// Sequelize - Using include
const users = await User.findAll({
  include: [{
    model: Post,
    as: 'posts'
  }]
});

// Django - Using select_related or prefetch_related
users = User.objects.select_related('profile').prefetch_related('posts')

// SQLAlchemy - Using joinedload
users = session.query(User).options(joinedload(User.posts)).all()
```

### DataLoader Batching
Implement batching to reduce database calls:

```javascript
const DataLoader = require('dataloader');

const userLoader = new DataLoader(async (userIds) => {
  const users = await User.findAll({ where: { id: userIds } });
  return userIds.map(id => users.find(user => user.id === id));
});

// Usage
const user = await userLoader.load(userId);
```

### Join vs Separate Queries
Choose appropriate query strategies based on data access patterns:

```javascript
// Good: Single join query instead of N+1
const usersWithPosts = await User.findAll({
  include: [{
    model: Post,
    required: true // INNER JOIN
  }]
});

// Better: Left join for optional relationships
const usersWithOptionalPosts = await User.findAll({
  include: [{
    model: Post,
    required: false // LEFT JOIN
  }]
});
``
