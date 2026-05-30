# Changelog

## [1.32.0] - 2026-05-30

### Changed
- **Calendrier économique** : remplacement du widget fxverify (Cloudflare Turnstile bloqué) par un **proxy ForexFactory local** (`proxy_calendar.py`, port 5000)
  - Scraping direct de `forexfactory.com/calendar/summary` → JSON formaté
  - Cache serveur 5 min, filtres `day`, `impact`, `currency` côté proxy
- **Filtres impact** : 3 cases à cocher 🔴 High / 🟠 Medium / 🟡 Low dans le header du calendrier (coche/décoche recharge les données dynamiquement)
- **Mode collapsible par défaut** : le calendrier démarre en mode dépliable avec bouton Replier/Déplier (le mode compact est toujours disponible dans les paramètres)
- Correction du débordement du calendrier sur les widgets suivants

### Added
- `proxy_calendar.py` — serveur Flask proxy ForexFactory (port 5000, venv `.venv-proxy/`)
- `start.sh` — script de démarrage complet (proxy + serveur HTTP)

### Removed
- Dépendance fxverify.com (widget JS + iframe plus fonctionnels)

## [1.29.0] - 2025-05-08

### Changed
- **Moteur d'agrégation Flat-to-Flat** : remplacement complet du système FIFO par lots par le moteur `FlatToFlatEngine` (méthode officielle Sierra Chart)
  - Un trade = un cycle complet (position 0 → non-nul → retour à 0)
  - Scale-in (rajout de contrats) : avgEntry dynamique pondéré
  - Scale-out (TP partiel) : PnL accumulé sur chaque fermeture partielle, trade finalisé à plat
  - Reversal (inversion) : fermeture du trade actuel + ouverture d'un nouveau dans le sens opposé
  - Commissions réparties proportionnellement sur chaque portion fermée
  - `ensureSeedForClose` adapté : injecte un trade hérité avec la quantité complète du snapshot serveur

### Fixed
- Bug fix : PnL du trade fermé calculé via somme des `scaleOuts[].pnl` (au lieu d'un `cumulPnl` remis à 0 à chaque appel)
- Bug fix : `ensureSeedForClose` utilise `Math.abs(pos.qty)` au lieu de `incomingQty` pour le trade hérité
- Connexion DTC : timeout 15s, flag `_timedOut`, nettoyage heartbeat dans onClose/onError
- SRI/crossorigin retiré (cassait le chargement en `file://`)

## [1.28.1] - 2025-05-08

### Added
- CSS custom properties for all hardcoded colors (50+ replacements)
- CSS `:focus-visible` and `prefers-reduced-motion` support

### Changed
- Default WebSocket URL set to `127.0.0.1:11099` instead of blank
- Guard against recursive reconnection calls (avoid stacking `reconnect()` invocations)
- Deduplicated `.widget-header` CSS rules (3 definitions → 1)

### Fixed
- Recursive reconnection loop when WebSocket disconnects during ongoing reconnect

## [1.28.0] - 2025-05-08

### Added
- External CSS files (variables.css, main.css, donut-fixes.css, calendar.css) extracted from inline styles
- 5-second connection timeout for DTC WebSocket
- Position snapshot handler (DTC Type 305)
- Heartbeat starts after LOGON_RESPONSE (Type 2) instead of on connection
- Exponential backoff with jitter for WebSocket reconnection (max 10 attempts)
- WebSocket URL validation (must be ws:// or wss://)
- RX buffer size limit (1 MB) to prevent memory leaks
- Fills buffer cleanup on watchdog timeout

### Changed
- SRI hashes removed for vendor scripts (file:// protocol compatibility)
- CSP tightened: removed `https:` from default-src, restricted connect-src
- Unified heartbeat mechanism (removed duplicate setInterval ping)
- Replaced hardcoded rgba colors with CSS variables

### Fixed
- Race condition: initial requests now wait for LOGON_RESPONSE
- Dual heartbeat timers causing duplicate pings
- Memory leak: RX buffer and fill keys now bounded
- Duplicate position snapshot handling via Type 305 handler
- `_connecting` guard prevents parallel connection attempts