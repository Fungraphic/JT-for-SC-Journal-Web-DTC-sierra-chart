# Contribuer à JT for SC — Journal Web DTC

Merci de votre intérêt ! Voici comment contribuer.

## Développement local

1. Clonez le repo
2. Ouvrez `index.html` dans un navigateur — c'est une app purement client-side
3. Connectez-vous à un serveur DTC (Sierra Chart) via WebSocket

## Structure du projet

- `index.html` — Application principale (HTML + JS inline)
- `assets/css/` — Feuilles de style extraites
  - `variables.css` — Design tokens (couleurs, rayons, ombres)
  - `main.css` — Styles principaux
  - `donut-fixes.css` — Correctifs pour les graphiques donut
  - `calendar.css` — Styles du calendrier économique
- `assets/vendor/` — Bibliothèques tierces (Chart.js, D3, etc.)
- `assets/logo.svg` — Logo

## Conventions

- Les couleurs doivent utiliser les variables CSS définies dans `variables.css`
- Les nouvelles couleurs doivent être ajoutées comme variables avant utilisation
- Les modifications DTC doivent respecter le protocole DTC (messages JSON)
- Préférez `textContent` à `innerHTML` quand seul du texte est inséré

## Pull Requests

- Décrivez le problème résolu
- Testez avec un serveur Sierra Chart DTC en fonctionnement
- Vérifiez que les SRI hashes sont à jour si vous modifiez un vendor