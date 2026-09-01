# Layered Architecture Transaction Script Vs Domain

## Scope

This article addresses the choice between the transaction script and the domain model pattern within a layered architecture, as catalogued in Martin Fowler's *Patterns of Enterprise Application Architecture*. It explains when transaction scripts are appropriate, when the domain model is necessary, and how a layered architecture should accommodate either. The discussion covers the presentation, domain, and data source layers; the role of the service layer; and the cost of moving from transaction scripts to a domain model once complexity has grown. The article applies to any language or framework that supports a layered structure, including Java, C#, Python, and TypeScript.

## Workflow or implementation guidance

A layered architecture divides the application into horizontal layers: the presentation layer handles user interaction, the domain layer holds the business logic, and the data source layer handles persistence. Each layer depends only on the layer below it. The presentation layer invokes the domain layer, the domain layer invokes the data source layer, and the data source layer talks to the database or external services.

Inside the domain layer, two patterns organise the business logic. The transaction script pattern is the simplest: each use case is a procedure that performs the necessary steps in order. The procedure opens a transaction, reads the relevant rows, applies the business rules in line, writes the result, and commits. The domain model pattern is more sophisticated: the business logic is encapsulated in a network of interconnected objects, each representing a meaningful concept in the domain, with the behaviour distributed across the objects.

The first decision is whether the business logic is simple enough to be expressed as a sequence of steps. Transaction scripts are appropriate when the logic is short, does not involve complex interactions between concepts, and does not need to be reused across use cases. A CRUD-heavy application with little validation beyond "this field is required" is a transaction script. The second decision is whether the logic is complex enough to require a domain model. A domain model is appropriate when the business logic involves many concepts that interact (an order with line items, a customer with credit history, an inventory with reservations), when the same logic is reused across use cases, and when the validation rules are not just "this field is required" but "this field is consistent with the rest of the object".

The third step is to design the layer interfaces. The presentation layer should not know whether the domain layer is using a transaction script or a domain model; it invokes a use case, and the use case returns a result. The service layer, where it exists, can hold the use cases and mediate between the presentation layer and the domain model. The data source layer should expose its operations as a set of finders and savers that the domain layer can use; if the data source layer exposes a generic "execute SQL" interface, the domain layer is not really layered at all.

The fourth step is to plan for the eventual move from transaction scripts to a domain model. Almost every non-trivial application starts as a transaction script. As complexity grows, the scripts begin to duplicate logic ("calculate the discount" appears in five places), and the team must extract a domain model. The layered architecture makes this move easier because the presentation layer does not change, and the data source layer does not change; only the domain layer is refactored. The cost is that the data source layer must expose enough operations to support the domain model (not just "execute this query" but "find orders by customer and date"), and the presentation layer must use a service layer or a use case interface rather than calling the domain objects directly.

## Controls

Layered architecture controls are about enforcing the layer boundaries. The presentation layer must not import the data source layer; the domain layer must not import the presentation layer; the data source layer must not import either. Architectural lint rules enforce this. A second control is the coherence of the domain layer: if the domain layer is composed of many small procedures with no shared concepts, it is a transaction script; if it is composed of interconnected objects with state and behaviour, it is a domain model. The team should know which one it has and should not mix them without discipline.

A third control is the service layer's role. Where the service layer exists, it must mediate between the presentation layer and the domain layer, and it must be the only entry point into the domain layer for the presentation layer. Where the service layer does not exist, the presentation layer invokes the domain layer directly, and the boundary is enforced by convention rather than by structure.

## Validation evidence

Validation of a layered architecture is structural: the import graph must show the expected layers with no upward edges. Validation of the choice between transaction script and domain model is behavioural: the test suite should cover the business logic, and the structure of the tests should reflect the structure of the code. Transaction-script tests look like sequences of "given the database has X, when I call this procedure, then the database has Y." Domain-model tests look like interactions between objects.

Validation of the move from transaction scripts to a domain model is the absence of duplication: the same business rule should not appear in two transaction scripts. A duplication check (a code-search for "calculate discount" or similar) is a useful indicator.

## Failure modes and correction

The dominant failure is the domain layer leaking into the presentation layer. A controller contains business logic because it was convenient. The cure is the architectural lint rule and the code-review gate. A second failure is the data source layer leaking into the domain layer. The domain objects carry database concerns (transactions, sessions, dirty checking) because the ORM makes it convenient. The cure is to define repositories in the domain layer that hide the persistence mechanism.

A third failure is the transition from transaction script to domain model being postponed indefinitely. The duplication grows, the team is afraid to refactor, and the application becomes unmaintainable. The cure is to set a threshold for the move: when a particular business rule appears in three or more transaction scripts, it is extracted into a domain object. A fourth failure is the domain model becoming anemic. The objects have only getters and setters, and all the behaviour lives in a service layer that has nothing to do with the objects. The cure is to push behaviour back into the objects so that the domain model is rich, not anemic.

A fifth failure is the layered architecture being used to justify a "one true path" for the team. The team uses the transaction script for a use case that should clearly be a domain model, or vice versa, because the architecture prescribes one approach. The cure is to recognise that the layered architecture accommodates both, and the choice between them is a per-use-case decision.

## Limitations

Layered architecture is not the only valid architecture, and for some systems it is the wrong choice. A highly modular system with many independent use cases may benefit from a vertical-slice architecture, in which each use case is a self-contained unit that crosses the layers. A reactive system with a heavy event-driven core may benefit from an event-driven architecture, in which the layers are not the primary organising principle. The layered architecture is best suited to systems with a moderate number of use cases, a clear presentation/data-source distinction, and a team that is comfortable with horizontal layering.

The transaction script vs domain model choice is also context-dependent. A small application is well served by transaction scripts, but a small application that will grow into a large one should plan for the move to a domain model. The discipline is to recognise the inflection point and to refactor before the duplication becomes unmanageable.

## Canonical sources

- Martin Fowler — *Patterns of Enterprise Application Architecture* (PoEAA), the canonical reference for the layered architecture, the transaction script, the domain model, the service layer, the table module, the repository, and the unit of work: https://martinfowler.com/eaaCatalog/layers.html (linked from the catalog)
- Martin Fowler — *Presentation Domain DataLayering* bliki entry, on the layering principle in practice: https://martinfowler.com/bliki/PresentationDomainDataLayering.html
- Eric Evans — *Domain-Driven Design*, on the relationship between the domain model pattern and the broader practice of modelling
- Vaughn Vernon — *Implementing Domain-Driven Design*, on the application of layered architecture to DDD projects
