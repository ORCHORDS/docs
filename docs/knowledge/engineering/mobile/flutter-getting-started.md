# Flutter Integration Guide

## Getting Started with Flutter

Flutter is Google's UI toolkit for building natively compiled applications for mobile, web, and desktop from a single codebase. It uses Dart as its programming language and provides a rich set of pre-designed widgets.

```dart
// Basic Flutter widget structure
import 'package:flutter/material.dart';

void main() {
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      home: Scaffold(
        appBar: AppBar(title: Text('My App')),
        body: Center(child: Text('Hello World!')),
      ),
    );
  }
}
```

## Dart Language Fundamentals

Dart is a client-optimized language for fast apps on any platform. It supports both synchronous and asynchronous programming with `async`/`await`.

```dart
// Dart basics
class Person {
  String name;
  int age;

  Person(this.name, this.age);

  Future<String> getGreeting() async {
    await Future.delayed(Duration(seconds: 1));
    return 'Hello, $name!';
  }
}

// Using streams for real-time data
Stream<int> countStream() async* {
  int count = 0;
  while (true) {
    await Future.delayed(Duration(seconds: 1));
    yield ++count;
  }
}
```

## Widgets vs React Native Components

Flutter uses a widget-based architecture where everything is a widget. Unlike React Native's component system, Flutter widgets are immutable and rebuilt when their state changes.

```dart
// Flutter Widget example
class CounterWidget extends StatefulWidget {
  @override
  _CounterWidgetState createState() => _CounterWidgetState();
}

class _CounterWidgetState extends State<CounterWidget> {
  int counter = 0;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text('Count: $counter'),
        ElevatedButton(
          onPressed: () => setState(() => counter++),
          child: Text('Increment'),
        ),
      ],
    );
  }
}
```

## Hot Reload Feature

Flutter's hot reload feature allows developers to see changes instantly without restarting the app, significantly improving development speed.

```bash
# Enable hot reload in terminal
flutter run

# Press 'r' to reload or 'R' for full restart
``
