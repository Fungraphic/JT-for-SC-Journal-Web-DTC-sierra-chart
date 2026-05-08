# Changelog

## [1.28.0] - 2025-05-08

### Added
- External CSS files (variables.css, main.css, donut-fixes.css, calendar.css) extracted from inline styles
- CSS custom properties for all hardcoded colors (50+ replacements)
- CSS `:focus-visible` and `prefers-reduced-motion` support
- Subresource Integrity (SRI) hashes on all vendor scripts
- 5-second connection timeout for DTC WebSocket
- Position snapshot handler (DTC Type 305)
- Heartbeat starts after LOGON_RESPONSE (Type 2) instead of on connection
- Exponential backoff with jitter for WebSocket reconnection (max 10 attempts)
- WebSocket URL validation (must be ws:// or wss://)
- RX buffer size limit (1MB) to prevent memory leaks
- Fills buffer cleanup on watchdog timeout

### Changed
- CSP tightened: removed `https:` from default-src, restricted connect-src
- Unified heartbeat mechanism (removed duplicate setInterval ping)
- Deduplicated `.widget-header` CSS rules (3 definitions → 1)
- Replaced hardcoded rgba colors with CSS variables

### Fixed
- Race condition: initial requests now wait for LOGON_RESPONSE
- Dual heartbeat timers causing duplicate pings
- Memory leak: RX buffer and fill keys now bounded
- Duplicate position snapshot handling via Type 305 handler