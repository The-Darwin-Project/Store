# Test: FRIDAY Redis Event State Validation

This PR tests FRIDAY's behavior after the Redis-only event state fix.

Verifying:
- No SPIRAL (repeated tool calls)
- No double-messages (2-legs)
- No thinking leak
- Proper FC/FR handling with thought_signature
