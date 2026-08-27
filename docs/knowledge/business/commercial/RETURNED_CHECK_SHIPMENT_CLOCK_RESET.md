# Returned-Check Shipment Clock Reset

Handle shipment timing consistently when payment fails and is later corrected.

- Record when the payment failure stops the clock.
- Restart timing when qualifying payment is received.
- Preserve the original promised timeframe logic.

Primary source: FTC order-merchandise rule guide.