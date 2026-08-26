# Flutter Flame Workers Game State Sync with Durable Objects

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Multiplayer Flutter Flame games need authoritative real-time game state that survives client disconnects, supports up to dozens of concurrent players per room, and does not require a dedicated game server—only Cloudflare infrastructure.

## Context
Flutter Flame is a lightweight 2D game engine built on Flutter. Its game loop runs at up to 60 fps, but network I/O must be kept off the game loop thread to avoid jank. Cloudflare Durable Objects provide a single-threaded, strongly-consistent per-room WebSocket hub with hibernation support—ideal for authoritative game state like player positions, scores, and turn order. The Dart client connects via `web_socket_channel` and dispatches state patches into the Flame component tree via a `ChangeNotifier` or `StreamController`.

## Durable Object: Game Room

```typescript
// worker/src/game-room.ts
import { DurableObject } from "cloudflare:workers";

export interface Env {
  GAME_ROOM: DurableObjectNamespace;
}

interface PlayerState {
  id: string;
  x: number;
  y: number;
  score: number;
  lastSeen: number;
}

interface GameState {
  players: Record<string, PlayerState>;
  tick: number;
  startedAt: number | null;
}

type ClientMessage =
  | { type: "join"; playerId: string; displayName: string }
  | { type: "move"; playerId: string; x: number; y: number }
  | { type: "score"; playerId: string; delta: number }
  | { type: "leave"; playerId: string };

export class GameRoom extends DurableObject {
  private sessions: Map<WebSocket, string> = new Map(); // ws -> playerId
  private state: GameState = { players: {}, tick: 0, startedAt: null };

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket upgrade", { status: 426 });
    }

    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server);
    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    let msg: ClientMessage;
    try {
      msg = JSON.parse(typeof message === "string" ? message : new TextDecoder().decode(message));
    } catch {
      return;
    }

    this.state.tick++;

    switch (msg.type) {
      case "join":
        this.sessions.set(ws, msg.playerId);
        this.state.players[msg.playerId] = {
          id: msg.playerId,
          x: 0,
          y: 0,
          score: 0,
          lastSeen: Date.now(),
        };
        if (!this.state.startedAt) this.state.startedAt = Date.now();
        break;

      case "move": {
        const p = this.state.players[msg.playerId];
        if (p) {
          // Server-side clamp: prevent out-of-bounds positions
          p.x = Math.max(0, Math.min(1920, msg.x));
          p.y = Math.max(0, Math.min(1080, msg.y));
          p.lastSeen = Date.now();
        }
        break;
      }

      case "score": {
        const p = this.state.players[msg.playerId];
        if (p) p.score = Math.max(0, p.score + msg.delta);
        break;
      }

      case "leave":
        delete this.state.players[msg.playerId];
        this.sessions.delete(ws);
        break;
    }

    this.broadcast();
  }

  webSocketClose(ws: WebSocket): void {
    const playerId = this.sessions.get(ws);
    if (playerId) {
      delete this.state.players[playerId];
      this.sessions.delete(ws);
      this.state.tick++;
      this.broadcast();
    }
  }

  private broadcast(): void {
    const payload = JSON.stringify({ type: "state", state: this.state });
    for (const [ws] of this.sessions) {
      try {
        ws.send(payload);
      } catch {
        // session closed
      }
    }
  }
}

// worker/src/index.ts
export { GameRoom } from "./game-room";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const roomId = url.searchParams.get("room") ?? "default";
    const stub = env.GAME_ROOM.get(env.GAME_ROOM.idFromName(roomId));
    return stub.fetch(request);
  },
};
```

```toml
# wrangler.toml
name = "flame-game-worker"
compatibility_date = "2026-01-01"

[[durable_objects.bindings]]
name = "GAME_ROOM"
class_name = "GameRoom"

[[migrations]]
tag = "v1"
new_classes = ["GameRoom"]
```

## Flutter Dart Client

```dart
// lib/services/game_room_client.dart
import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:flutter/foundation.dart';

class PlayerState {
  final String id;
  final double x;
  final double y;
  final int score;

  const PlayerState({
    required this.id,
    required this.x,
    required this.y,
    required this.score,
  });

  factory PlayerState.fromJson(Map<String, dynamic> json) => PlayerState(
        id: json['id'] as String,
        x: (json['x'] as num).toDouble(),
        y: (json['y'] as num).toDouble(),
        score: json['score'] as int,
      );
}

class GameState {
  final Map<String, PlayerState> players;
  final int tick;

  const GameState({required this.players, required this.tick});

  factory GameState.fromJson(Map<String, dynamic> json) {
    final rawPlayers = json['players'] as Map<String, dynamic>? ?? {};
    return GameState(
      tick: json['tick'] as int,
      players: rawPlayers.map(
        (k, v) => MapEntry(k, PlayerState.fromJson(v as Map<String, dynamic>)),
      ),
    );
  }
}

class GameRoomClient extends ChangeNotifier {
  static const String _baseUrl = String.fromEnvironment(
    'WORKERS_WS_URL',
    defaultValue: 'wss://flame-game-worker.your-subdomain.workers.dev',
  );

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  GameState? _gameState;
  Timer? _reconnectTimer;
  bool _disposed = false;

  final String roomId;
  final String playerId;

  GameRoomClient({required this.roomId, required this.playerId});

  GameState? get gameState => _gameState;

  void connect() {
    final uri = Uri.parse('$_baseUrl?room=${Uri.encodeComponent(roomId)}');
    _channel = WebSocketChannel.connect(uri);
    _sub = _channel!.stream.listen(
      _onMessage,
      onError: (_) => _scheduleReconnect(),
      onDone: _scheduleReconnect,
    );
    _send({'type': 'join', 'playerId': playerId, 'displayName': playerId});
  }

  void sendMove(double x, double y) {
    _send({'type': 'move', 'playerId': playerId, 'x': x, 'y': y});
  }

  void sendScore(int delta) {
    _send({'type': 'score', 'playerId': playerId, 'delta': delta});
  }

  void _onMessage(dynamic raw) {
    final Map<String, dynamic> msg = jsonDecode(raw as String);
    if (msg['type'] == 'state') {
      _gameState = GameState.fromJson(msg['state'] as Map<String, dynamic>);
      notifyListeners();
    }
  }

  void _send(Map<String, dynamic> payload) {
    _channel?.sink.add(jsonEncode(payload));
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (!_disposed) connect();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _sub?.cancel();
    _send({'type': 'leave', 'playerId': playerId});
    _channel?.sink.close();
    super.dispose();
  }
}
```

## Flame Component Integration

```dart
// lib/game/multiplayer_game.dart
import 'package:flame/game.dart';
import 'package:flame/components.dart';
import 'package:flutter/material.dart';
import '../services/game_room_client.dart';

class RemotePlayerComponent extends PositionComponent {
  final String playerId;
  RemotePlayerComponent({required this.playerId, required Vector2 position})
      : super(position: position, size: Vector2(32, 32));

  @override
  void render(Canvas canvas) {
    canvas.drawCircle(
      Offset(size.x / 2, size.y / 2),
      16,
      Paint()..color = Colors.blue,
    );
  }
}

class MultiplayerGame extends FlameGame {
  final GameRoomClient client;
  final Map<String, RemotePlayerComponent> _remoteComponents = {};

  MultiplayerGame({required this.client}) {
    client.addListener(_onStateChange);
  }

  void _onStateChange() {
    final state = client.gameState;
    if (state == null) return;

    final incoming = state.players.keys.toSet();
    final existing = _remoteComponents.keys.toSet();

    // Add new players
    for (final id in incoming.difference(existing)) {
      final p = state.players[id]!;
      final comp = RemotePlayerComponent(
        playerId: id,
        position: Vector2(p.x, p.y),
      );
      _remoteComponents[id] = comp;
      add(comp);
    }

    // Remove disconnected players
    for (final id in existing.difference(incoming)) {
      final comp = _remoteComponents.remove(id);
      if (comp != null) remove(comp);
    }

    // Update existing positions
    for (final id in incoming.intersection(existing)) {
      final p = state.players[id]!;
      _remoteComponents[id]?.position = Vector2(p.x, p.y);
    }
  }

  @override
  void onRemove() {
    client.removeListener(_onStateChange);
    super.onRemove();
  }
}

// Throttle move events to avoid flooding the DO
class ThrottledMoveNotifier {
  final GameRoomClient client;
  DateTime _lastSent = DateTime.fromMillisecondsSinceEpoch(0);

  ThrottledMoveNotifier(this.client);

  void move(double x, double y) {
    final now = DateTime.now();
    if (now.difference(_lastSent).inMilliseconds >= 50) {
      // 20 Hz max
      client.sendMove(x, y);
      _lastSent = now;
    }
  }
}
```

## Anti-patterns
- Sending a position update on every Flame tick (60 per second)—throttle to 20 Hz or use delta-only updates
- Running WebSocket I/O on the Flame game isolate—use a separate isolate or `ChangeNotifier` bridge
- Trusting client-reported scores without server-side validation in the Durable Object
- Using `DurableObjectNamespace.idFromRandom()` for room IDs—players cannot rejoin the same room; use `idFromName(roomId)` with a user-supplied room code
- Storing per-room state only in Durable Object memory without periodic `this.ctx.storage.put` checkpoints; a DO eviction loses all in-memory state

## Gotchas
- Durable Objects with WebSocket hibernation wake on each message; `this.sessions` (an in-memory `Map`) is cleared on hibernation—use `this.ctx.getWebSockets()` to re-populate it
- `web_socket_channel` on Flutter web uses the browser `WebSocket` API; on mobile it uses `dart:io`—behavior on connection close differs slightly
- `String.fromEnvironment` in Dart is resolved at compile time, not runtime; pass `--dart-define=WORKERS_WS_URL=...` to `flutter build` or use a runtime config file instead
- Cloudflare limits each Durable Object instance to 1 MiB of in-memory state; large player counts (100+) will require sharding rooms across multiple DO IDs
- The DO's `broadcast()` call is synchronous within the actor; a slow WebSocket send can delay the next message—use try/catch and remove dead sessions eagerly

## Verification
1. Run `wrangler dev` and connect two browser WebSocket clients to `ws://localhost:8787?room=test`; confirm both receive state updates when one sends a `move` message.
2. In Flutter, run `flutter test` with a mock `WebSocketChannel` that emits a canned state JSON; assert `GameRoomClient.gameState?.players` parses correctly.
3. Disconnect one client and verify the DO removes that player from state and broadcasts the update.
4. Load-test with 30 simultaneous `wscat` connections sending moves at 20 Hz; check DO CPU time stays below the 30 ms per request limit in the Cloudflare dashboard.
5. Enable DO hibernation in `wrangler.toml` and confirm reconnect logic re-establishes the WebSocket within 5 seconds.

## Related
- `react-native-durable-objects-realtime.md`
- `capacitor-workers-sse-streaming.md`
- `flutter-workers-dart-client.md`
- `mobile-websocket-realtime-connections.md`

## Sources
- https://developers.cloudflare.com/durable-objects/
- https://flame-engine.org/docs/
- https://pub.dev/packages/web_socket_channel
