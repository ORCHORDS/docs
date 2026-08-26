# Web Bluetooth API Workers Device Bridge

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Pages PWA needs to read data from BLE peripherals (fitness sensors, environmental monitors, industrial gauges) and relay that data to a Cloudflare Worker for storage, aggregation, or alerting. The browser's Web Bluetooth API is async and permission-gated; the Worker-side contract defines the canonical schema.

---

## Context

Web Bluetooth is available in Chrome 56+ on Android, macOS, and Windows (behind a flag on Linux). It requires a secure context (HTTPS) and a user gesture for `requestDevice()`. There is no iOS support as of 2026.

Cloudflare Workers handle the server-side leg: receiving POST requests from the browser after each BLE read cycle, validating the payload, and writing to KV or D1.

The flow:
1. User taps "Connect Device" → gesture opens the BLE device chooser.
2. Browser connects to GATT server, discovers services and characteristics.
3. App subscribes to `characteristicvaluechanged` notifications or polls by reading.
4. On each reading, the app POSTs the structured payload to `/api/ble/reading`.
5. Worker persists and optionally fans out to a Durable Object for real-time streaming.

---

## Feature Detection

```typescript
// src/ble/support.ts
export function isBluetoothSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    "bluetooth" in navigator
  );
}

export async function checkBluetoothAvailability(): Promise<boolean> {
  if (!isBluetoothSupported()) return false;
  return navigator.bluetooth.getAvailability();
}
```

---

## Device Connection

```typescript
// src/ble/device.ts

// Standard GATT service and characteristic UUIDs
const BATTERY_SERVICE = "battery_service";
const BATTERY_LEVEL   = "battery_level";

// Custom environmental sensor UUIDs (replace with your peripheral's UUIDs)
const ENV_SENSING_SERVICE = "environmental_sensing";
const TEMPERATURE_CHAR    = "temperature";
const HUMIDITY_CHAR       = "0x2A6F";

export interface BLEDevice {
  name: string;
  id: string;
  gatt: BluetoothRemoteGATTServer;
}

export async function connectDevice(
  serviceFilters: BluetoothServiceUUID[]
): Promise<BLEDevice> {
  const device = await navigator.bluetooth.requestDevice({
    filters: [{ services: serviceFilters }],
    optionalServices: [BATTERY_SERVICE],
  });

  if (!device.gatt) {
    throw new Error("Device does not support GATT");
  }

  const server = await device.gatt.connect();

  return {
    name: device.name ?? "Unknown Device",
    id: device.id,
    gatt: server,
  };
}

export async function readBatteryLevel(
  server: BluetoothRemoteGATTServer
): Promise<number | null> {
  try {
    const service = await server.getPrimaryService(BATTERY_SERVICE);
    const characteristic = await service.getCharacteristic(BATTERY_LEVEL);
    const value = await characteristic.readValue();
    return value.getUint8(0);
  } catch {
    return null;
  }
}
```

---

## Notification Subscription

```typescript
// src/ble/notifications.ts
export type ReadingCallback = (payload: SensorReading) => void;

export interface SensorReading {
  deviceId: string;
  deviceName: string;
  temperatureCelsius: number | null;
  humidityPercent: number | null;
  batteryPercent: number | null;
  recordedAt: number;
}

export async function subscribeToEnvironmentalSensor(
  server: BluetoothRemoteGATTServer,
  deviceMeta: { id: string; name: string },
  onReading: ReadingCallback
): Promise<() => void> {
  const service = await server.getPrimaryService("environmental_sensing");
  const tempChar = await service.getCharacteristic("temperature");
  const humidChar = await service.getCharacteristic("0x2A6F");

  let lastTemp: number | null = null;
  let lastHumid: number | null = null;

  const handleTemp = (event: Event) => {
    const value = (event.target as BluetoothRemoteGATTCharacteristic).value!;
    // Temperature in 0.01 °C units per BT spec
    lastTemp = value.getInt16(0, true) / 100;
    emitReading();
  };

  const handleHumid = (event: Event) => {
    const value = (event.target as BluetoothRemoteGATTCharacteristic).value!;
    // Humidity in 0.01 % units
    lastHumid = value.getUint16(0, true) / 100;
    emitReading();
  };

  function emitReading() {
    onReading({
      deviceId: deviceMeta.id,
      deviceName: deviceMeta.name,
      temperatureCelsius: lastTemp,
      humidityPercent: lastHumid,
      batteryPercent: null, // polled separately
      recordedAt: Date.now(),
    });
  }

  await tempChar.startNotifications();
  await humidChar.startNotifications();
  tempChar.addEventListener("characteristicvaluechanged", handleTemp);
  humidChar.addEventListener("characteristicvaluechanged", handleHumid);

  return () => {
    tempChar.removeEventListener("characteristicvaluechanged", handleTemp);
    humidChar.removeEventListener("characteristicvaluechanged", handleHumid);
    tempChar.stopNotifications().catch(() => {});
    humidChar.stopNotifications().catch(() => {});
  };
}
```

---

## Forwarding to a Worker

```typescript
// src/ble/pipeline.ts
import type { SensorReading } from "./notifications";

export async function postReading(
  reading: SensorReading,
  signal?: AbortSignal
): Promise<{ id: string; storedAt: string }> {
  const res = await fetch("/api/ble/reading", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reading),
    signal,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ message: "Unknown error" }));
    throw new Error(`Worker error ${res.status}: ${body.message}`);
  }

  return res.json();
}
```

---

## Cloudflare Pages Function — `/api/ble/reading`

```typescript
// functions/api/ble/reading.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  BLE_READINGS: D1Database;
  BLE_ALERTS: KVNamespace;
}

interface SensorReading {
  deviceId: string;
  deviceName: string;
  temperatureCelsius: number | null;
  humidityPercent: number | null;
  batteryPercent: number | null;
  recordedAt: number;
}

const MAX_TEMP_C = 40;   // configurable threshold
const MIN_BATTERY = 15;  // alert below 15%

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  let reading: SensorReading;
  try {
    reading = (await request.json()) as SensorReading;
  } catch {
    return Response.json({ message: "Invalid JSON body" }, { status: 400 });
  }

  if (!reading.deviceId || typeof reading.recordedAt !== "number") {
    return Response.json({ message: "Missing deviceId or recordedAt" }, { status: 422 });
  }

  const id = crypto.randomUUID();
  const storedAt = new Date().toISOString();

  await env.BLE_READINGS.prepare(
    `INSERT INTO ble_readings
       (id, device_id, device_name, temperature_c, humidity_pct, battery_pct, recorded_at, stored_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      id,
      reading.deviceId,
      reading.deviceName,
      reading.temperatureCelsius,
      reading.humidityPercent,
      reading.batteryPercent,
      new Date(reading.recordedAt).toISOString(),
      storedAt
    )
    .run();

  // Write alert flag to KV if thresholds exceeded
  const alerts: string[] = [];
  if (reading.temperatureCelsius !== null && reading.temperatureCelsius > MAX_TEMP_C) {
    alerts.push(`temperature:${reading.temperatureCelsius}`);
  }
  if (reading.batteryPercent !== null && reading.batteryPercent < MIN_BATTERY) {
    alerts.push(`battery:${reading.batteryPercent}`);
  }
  if (alerts.length > 0) {
    await env.BLE_ALERTS.put(
      `alert:${reading.deviceId}`,
      JSON.stringify({ alerts, triggeredAt: storedAt }),
      { expirationTtl: 86400 }
    );
  }

  return Response.json({ id, storedAt }, { status: 201 });
};
```

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS ble_readings (
  id             TEXT PRIMARY KEY,
  device_id      TEXT NOT NULL,
  device_name    TEXT NOT NULL,
  temperature_c  REAL,
  humidity_pct   REAL,
  battery_pct    REAL,
  recorded_at    TEXT NOT NULL,
  stored_at      TEXT NOT NULL
);

CREATE INDEX idx_ble_readings_device    ON ble_readings (device_id, recorded_at);
CREATE INDEX idx_ble_readings_stored_at ON ble_readings (stored_at);
```

---

## React Hook

```typescript
// src/hooks/useBLE.ts
import { useState, useRef, useCallback } from "react";
import { connectDevice, readBatteryLevel } from "../ble/device";
import { subscribeToEnvironmentalSensor } from "../ble/notifications";
import { postReading } from "../ble/pipeline";
import type { SensorReading } from "../ble/notifications";

export function useBLE() {
  const [connected, setConnected] = useState(false);
  const [latestReading, setLatestReading] = useState<SensorReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  const connect = useCallback(async () => {
    setError(null);
    try {
      const device = await connectDevice(["environmental_sensing"]);
      const battery = await readBatteryLevel(device.gatt);

      const unsubscribe = await subscribeToEnvironmentalSensor(
        device.gatt,
        { id: device.id, name: device.name },
        async (reading) => {
          const enriched = { ...reading, batteryPercent: battery };
          setLatestReading(enriched);
          try {
            await postReading(enriched);
          } catch (err) {
            console.warn("Failed to post reading:", err);
          }
        }
      );

      unsubscribeRef.current = unsubscribe;
      setConnected(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const disconnect = useCallback(() => {
    unsubscribeRef.current?.();
    unsubscribeRef.current = null;
    setConnected(false);
    setLatestReading(null);
  }, []);

  return { connected, latestReading, error, connect, disconnect };
}
```

---

## Anti-patterns

- **Calling `requestDevice()` programmatically on page load.** This throws `SecurityError`. The call must originate from a synchronous user gesture (click, keydown).
- **Creating a new GATT connection per reading.** Connect once and reuse the server. Reconnecting triggers the OS pairing dialog again on some Android builds.
- **Not removing `characteristicvaluechanged` listeners on cleanup.** Stale listeners accumulate and fire after the component unmounts, causing "state update on unmounted component" React warnings.
- **Posting every individual characteristic change as a separate fetch.** For high-frequency sensors, batch readings client-side (e.g., every 5 seconds) and POST an array to reduce Worker invocations.
- **Storing `DataView` objects directly in React state.** `DataView` is not serializable to JSON. Decode to primitives before storing.

---

## Gotchas

- Web Bluetooth has no API access in iframes unless the frame is same-origin and the `bluetooth` Permissions-Policy allows it.
- On macOS, Chrome requires Bluetooth permission from System Settings → Privacy → Bluetooth. First-run prompts may be confusing to users.
- `device.gatt.connect()` does not automatically reconnect if the BLE connection drops. Listen to `device.addEventListener("gattserverdisconnected", ...)` and reconnect manually.
- Characteristic UUIDs can be specified as full 128-bit strings (`"0000180f-0000-1000-8000-00805f9b34fb"`) or as the 16-bit alias (`"battery_service"`, `0x180F`). The alias form only works for Bluetooth SIG assigned numbers.
- `startNotifications()` on a characteristic that does not support the Notify property throws `NotSupportedError`. Check `characteristic.properties.notify` before subscribing.

---

## Verification

1. Open the Pages site in Chrome on Android or macOS.
2. Click "Connect Device" and confirm the OS Bluetooth picker appears.
3. Select your test peripheral; verify `device.gatt.connected` is `true` in console.
4. Confirm `characteristicvaluechanged` events fire; log decoded values.
5. Check Worker logs for incoming POST requests to `/api/ble/reading`.
6. Query D1: `SELECT * FROM ble_readings ORDER BY stored_at DESC LIMIT 10`.
7. Simulate a battery-below-threshold reading and confirm KV `alert:{deviceId}` is set.

---

## Related

- `web-serial-api-workers-device-bridge.md`
- `web-nfc-api-workers-scan-pipeline.md`
- `user-activation-transient-sticky-gating.md`
- `pwa-service-worker-cloudflare-pages.md`
- `cloudflare-pages-headers-csp-mobile.md`

---

## Sources

- MDN Web Bluetooth API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API
- Web Bluetooth Community Group Spec: https://webbluetoothcg.github.io/web-bluetooth/
- Bluetooth SIG GATT Services: https://www.bluetooth.com/specifications/assigned-numbers/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Chrome Web Bluetooth samples: https://googlechrome.github.io/samples/web-bluetooth/
