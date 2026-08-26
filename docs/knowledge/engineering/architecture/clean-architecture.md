# Clean Architecture

Clean Architecture, popularized by Robert Martin (Uncle Bob), is a software design philosophy that separates the essentials from the non-essentials, creating maintainable, testable systems with clear boundaries between components.

## Dependency Rule

The core principle of Clean Architecture is the dependency rule: **inner layers cannot depend on outer layers**. Inner layers contain business logic and entities, while outer layers handle frameworks, databases, and user interfaces.

```java
// ❌ Wrong - outer layer depends on inner layer
public class UserController {
    private UserRepository repository; // This is fine

    public void saveUser(User user) {
        // Business logic here
        repository.save(user); // Depends on outer layer
    }
}

// ✅ Correct - dependencies flow inward
public class UserService {
    private UserRepository repository;

    public void saveUser(User user) {
        // Business logic in inner layer
        repository.save(user);
    }
}
```

## Entities

Entities are the most fundamental building blocks, representing core business objects with no external dependencies. They should contain only business logic and data structures.

```java
public class User {
    private String id;
    private String name;
    private String email;

    // Business logic that belongs to the entity
    public boolean isValidEmail() {
        return email != null && email.contains("@");
    }

    // No framework dependencies here
    public User(String name, String email) {
        this.name = name;
        this.email = email;
    }
}
```

## Use Cases

Use cases represent application-specific business rules. They orchestrate the flow between entities and interface adapters, containing the core application logic.

```java
public class CreateUserUseCase {
    private UserRepository repository;

    public User execute(CreateUserRequest request) {
        // Validate input
        if (request.getName() == null || request.getName().isEmpty()) {
            throw new IllegalArgumentException("Name is required");
        }

        // Business rules
        User user = new User(request.getName(), request.getEmail());
        if (!user.isValidEmail()) {
            throw new InvalidEmailException("Invalid email format");
        }

        // Execute the use case
        return repository.save(user);
    }
}
```

## Interface Adapters

Interface adapters convert data between the outer layers (frameworks) and inner layers (business logic). They include controllers, presenters, and gateways.

```java
// Controller - handles HTTP requests
@RestController
public class UserController {
    private CreateUserUseCase createUserUseCase;

    @PostMapping("/users")
    public ResponseEntity<User> createUser(@RequestBody CreateUserRequest request) {
        try {
            User user = createUserUseCase.execute(request);
            return ResponseEntity.ok(user);
        } catch (Exception e) {
            return ResponseEntity.badRequest().build();
        }
    }
}

// Gateway - database abstraction
public interface UserRepository {
    User save(User user);
    User findById(String id);
}
```

## Frameworks

Frameworks and tools belong in the outermost layers. They provide infrastructure support but should not influence business logic.

```java
// Database implementation - framework specific
@Repository
public class JpaUserRepository implements UserRepository {
    private final EntityManager entityManager;

    @Override
    public User save(User user) {
        entityManager.persist(user);
        return user;
    }
}
```

## Testability

Clean Architecture makes testing straightforward by isolating business logic from infrastructure concerns.

```java
@Test
public void testCreateUserWithValidEmail() {
    // Arrange
    UserRepository mockRepository = mock(UserRepository.class);
    CreateUserUseCase useCase = new CreateUserUseCase(mockRepository);

    CreateUserRequest request = new CreateUserRequest("John", "john@example.com");

    // Act
    User result = useCase.execute(request);

    // Assert
    assertNotNull(result);
    verify(mockRepository).save(any(User.class));
}

@Test
public void testCreateUserWithInvalid
