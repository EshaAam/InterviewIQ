---
title: OOP, SOLID and design patterns
topic: oop-design
license: hand-written for InterviewIQ
url:
---

# OOP, SOLID and design patterns

## What are the four pillars of object-oriented programming?

Encapsulation keeps an object's data private and exposes behaviour through
methods, so the object can protect its own rules — a bank account that cannot
go negative because the balance is only changed through `withdraw`.
Abstraction exposes what an object does and hides how. Inheritance lets a class
reuse and extend another class. Polymorphism lets code work with a general type
while each concrete class supplies its own behaviour, so `shape.area()` works
for circles and squares alike.

In interviews it helps to give an example of each rather than definitions, and
to mention that encapsulation and polymorphism are the ones that pay off most in
real code.

## Why prefer composition over inheritance?

Inheritance creates a tight "is-a" relationship: a subclass depends on the
parent's internal behaviour, and a change in the parent can break every
subclass. Deep hierarchies also force awkward choices when an object needs
behaviour from two branches.

Composition builds objects from smaller parts they hold and delegate to: a
`Car` has an `Engine` rather than being one. Parts can be swapped at runtime and
tested on their own. Inheritance still fits genuine "is-a" relationships that are
stable; composition is the safer default.

## What do the Single Responsibility and Open/Closed principles mean in practice?

Single Responsibility means a class should have one reason to change. A
controller that validates input, calculates prices, writes to the database and
sends an email changes whenever any of those rules change; splitting them makes
each part smaller and testable.

Open/Closed means software should be open to extension but closed to
modification: adding a new payment provider should mean adding a new class that
implements a payment interface, not editing a growing `if provider == ...` chain
in code that already works.

## What are the Liskov, Interface Segregation and Dependency Inversion principles?

Liskov Substitution says a subclass must be usable wherever its parent is
expected without surprising the caller. A `ReadOnlyList` that throws on `add` is
the classic violation.

Interface Segregation says clients should not depend on methods they do not use:
several small interfaces are better than one large one.

Dependency Inversion says high-level code should depend on abstractions, not
concrete classes. A service that receives a `PaymentGateway` interface through
its constructor can be given a real gateway in production and a fake one in
tests. This is what dependency injection containers in Laravel, Spring or
FastAPI's `Depends` support.

## Which design patterns have you used, and why?

Strategy: several interchangeable algorithms behind one interface, chosen at
runtime — different shipping cost calculators or payment providers.
Factory: one place decides which concrete class to create, often from
configuration. Observer: objects subscribe to events, as in event listeners or
pub/sub. Adapter: wraps a third-party API in the interface your code expects, so
switching vendors touches one class. Decorator: wraps an object to add behaviour
without changing it, such as adding caching or retries around a client. Repository:
hides data access behind collection-like methods.

The best answers name the problem the pattern solved in a real project, not just
the definition.

## Why is the Singleton pattern often considered an anti-pattern?

A Singleton guarantees one instance and global access to it. In practice it acts
as global state: any code can reach it, dependencies become hidden, and tests
interfere with each other because they share the instance.

Most legitimate uses — one database connection pool, one configuration object —
are better handled by creating the object once at startup and passing it in, or
letting a dependency injection container manage its lifetime.

## What is the difference between an abstract class and an interface?

An interface only declares what methods a type must have; a class can implement
many interfaces. An abstract class can also contain shared fields and
implemented methods, but a class can extend only one (in Java and C#).

Use an interface to define a capability that unrelated classes share, such as
`Comparable` or `PaymentGateway`. Use an abstract class when several closely
related classes share real code and state. Modern Java interfaces can have
default methods, which narrows the difference.

## What is the difference between overloading and overriding?

Overloading is several methods with the same name but different parameters in
the same class, chosen at compile time from the arguments. Overriding is a
subclass replacing a method it inherited with the same signature, chosen at
runtime from the object's actual type — this is runtime polymorphism.

In C++, overriding only works through pointers or references when the base
method is declared `virtual`, and a base class meant for inheritance should have
a virtual destructor so deleting through a base pointer cleans up correctly.
