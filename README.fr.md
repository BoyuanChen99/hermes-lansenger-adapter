[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Adaptateur Hermes Lansenger

> 💠 Adaptateur de passerelle Lansenger + plugin d'outils média & messages pour Hermes Agent.

Connecte Hermes Agent à Lansenger — une plateforme de messagerie d'entreprise — via une connexion longue WebSocket pour la réception de messages en temps réel et via l'API HTTP pour l'envoi de messages.

Ce dépôt contient **deux plugins** :

| Plugin | Type | Ce qu'il fait |
|--------|------|---------------|
| `platforms/lansenger/` | plateforme | Adaptateur de canal de passerelle — recevoir & envoyer des messages |
| `lansenger-tools/` | autonome (outil) | Outils appelables par l'Agent : envoyer des fichiers/images, révoquer des messages, envoyer des linkCard |

## Fonctionnalités

### Adaptateur de plateforme
- **Messagerie en temps réel** via connexion longue WebSocket
- **Support Markdown** utilisant le msgType `formatText`
- **i18nAppCard** — cartes interactives de flux d'approbation
- **Détection automatique du canal principal** — le premier message p2p définit la cible de livraison par défaut
- **Livraison planifiée** — notifications planifiées via `standalone_sender_fn`
- **Autorisation des utilisateurs** — utilisateurs autorisés / autoriser tous les utilisateurs via des variables d'environnement
- **Zéro modification du core** — mode plugin pur, `git diff HEAD` reste INTACT

### Plugin d'outils média & messages
- **lansenger_send_text** — Envoyer des messages en texte brut avec @mentions optionnelles (groupe/staff uniquement) et pièces jointes
- **lansenger_send_markdown** — Envoyer des messages au format Markdown (pas de @mentions ni pièces jointes)
- **lansenger_send_file** — Envoyer tout fichier/image/vidéo local à un utilisateur ou groupe spécifique
- **lansenger_send_image_url** — Envoyer une image depuis une URL à un utilisateur ou groupe spécifique
- **lansenger_revoke_message** — Révoquer un message Lansenger envoyé 🗑️
- **lansenger_send_link_card** — Envoyer un message de carte linkCard Lansenger 🔗
- **Détection automatique du type de média** — images/vidéos/documents classifiés par extension
- **Contrôle des identifiants** — outils masqués lorsque LANSENGER_APP_ID/SECRET ne sont pas configurés

## Installation rapide

### Via le gestionnaire de plugins Hermes (recommandé)

```bash
hermes plugins install lansenger-pm/hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### Installation manuelle

Clonez ce dépôt dans `~/.hermes/plugins/` :

```bash
cd ~/.hermes/plugins/
git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

### Via pip (avancé)

```bash
pip install hermes-lansenger-adapter
hermes plugins enable hermes-lansenger-adapter
hermes gateway restart
```

> **Note :** Le bundle s'étend automatiquement au premier redémarrage du gateway. Les sous-plugins (`lansenger-platform` et `lansenger-tools`) sont automatiquement copiés dans `~/.hermes/plugins/`, auto-activés dans `config.yaml`, et chargés en place — pas besoin d'exécuter des commandes `hermes plugins enable` séparées pour chaque sous-plugin.

## Configuration

### Required Environment Variables

Ajoutez ces variables à `~/.hermes/.env` :

| Variable | Description | Exemple |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | ID App du Bot | `your-app-id` |
| `LANSENGER_APP_SECRET` | Secret App du Bot | `your-app-secret` |

**Chemin des identifiants :** Lansenger (client desktop) → Contacts → Robot intelligent → Robot personnel → cliquer sur l'icône ℹ️ pour voir les identifiants (le client mobile ne permet pas de voir les identifiants)

### Variables d'environnement optionnelles

| Variable | Description | Valeur par défaut |
|----------|-------------|-------------------|
| `LANSENGER_API_GATEWAY_URL` | URL de la passerelle API | `https://open.e.lanxin.cn/open/apigw` |
| `LANSENGER_ALLOWED_USERS` | IDs d'utilisateurs autorisés (séparés par des virgules) | — |
| `LANSENGER_ALLOW_ALL_USERS` | Autoriser tous les utilisateurs (développement uniquement) | `false` |
| `LANSENGER_HOME_CHANNEL` | ID de chat par défaut pour la livraison planifiée | Détection automatique |

### config.yaml

```yaml
platforms:
  lansenger:
    enabled: true
```

## Outils média & messages (de lansenger-tools)

Ces outils permettent à l'Agent d'envoyer des fichiers, images et vidéos, de révoquer des messages et d'envoyer des cartes linkCard — tous appelables indépendamment par le LLM. Les identifiants sont lus depuis les variables d'environnement (LANSENGER_APP_ID/SECRET), et non depuis `load_gateway_config()`.

| Outil | Paramètres | Description |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | Envoyer du texte brut avec @mentions optionnelles (groupe/staff uniquement) et pièces jointes |
| `lansenger_send_markdown` | `chat_id`, `message` | Envoyer du texte Markdown (pas de @mentions ni pièces jointes) |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Envoyer un fichier/image/vidéo local à un utilisateur ou groupe |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Télécharger une image depuis une URL et l'envoyer comme image native |
| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | Révoquer un message Lansenger envoyé (le prompt système est fixe, non personnalisable) |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | Envoyer un message de carte linkCard Lansenger |

**Exemples d'utilisation (prompts de l'Agent) :**

```
"Envoyer le rapport report.pdf à l'utilisateur 2285568-abc123"
"Partager cette image du graphique avec le chat de groupe du projet"
"Télécharger cette image URL et l'envoyer à mon collègue"
"Révoquer le message que j'ai刚刚 envoyé à l'utilisateur"
"Envoyer une carte link card à l'utilisateur avec le titre 'Documentation du projet' et le lien https://..."
```

**Limitations :**
- Les limites de taille de fichier sont déterminées par la configuration Lansenger de l'organisation (aucun plafond fixe)
- Les légendes de média utilisent du texte brut (pas de Markdown) — pour du texte Markdown, envoyer séparément
- `lansenger_send_file` détecte automatiquement le media_type depuis l'extension si non spécifié
- `lansenger_revoke_message` : pour les types de chat staff/groupe, `sender_id` est requis

## Architecture

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # manifeste racine (type : bundle)
                          ├── platforms/lansenger/            # Adaptateur de passerelle
                          │   ├── plugin.yaml                 # manifeste (type : plateforme)
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   └── adapter.py                   # adaptateur complet (pas de gestionnaires d'outils ici)
                          ├── lansenger-tools/           # Outils média & messages
                          │   ├── plugin.yaml                 # manifeste (type : autonome)
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # descriptions d'outils pour le LLM
                          │   └── tools.py                     # implémentations des gestionnaires
                          ├── skills/                          # Compétence de décision de l'Agent
                          │   └── lansenger-messaging.md       # stratégie de sélection d'outils + docs token
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # point d'entrée pip
                          └── .gitignore
```

## Dépendances

- `websockets` — Client WebSocket pour connexion longue
- `httpx` — Client HTTP pour appels API (aussi utilisé par les outils média)

## Mise à jour

Pour mettre à jour vers la dernière version :

```bash
hermes plugins update hermes-lansenger-adapter
hermes gateway restart
```

## Journal des modifications

### v2.3.0 (2026-05-12)

- ✅ Expansion automatique du bundle — le `__init__.py` racine copie les sous-plugins au niveau supérieur de `~/.hermes/plugins/`, les auto-active dans `config.yaml`, et les charge en place via `importlib`
- ✅ Flux d'installation simplifié — seul `hermes plugins enable hermes-lansenger-adapter` est nécessaire (les sous-plugins sont auto-activés au redémarrage du gateway)
- ✅ Le bundle se retire de la liste enabled après expansion (il sert uniquement de conteneur)

### v2.2.0 (2026-05-11)

- ✅ Implémentation de `reminder` (@mentions) pour `send_text` et `send_text_with_media` — `reminder_all` (bool, @tous) + `reminder_user_ids` (array, utilisateurs spécifiés), correspondant à l'objet `reminder` de l'API Lansenger
- ✅ Les @mentions ne fonctionnent que dans les chats de groupe/staff ; les chats privés ne les supportent pas
- ✅ Correction du champ schema `at_user_ids` qui était défini mais jamais passé aux méthodes de l'adaptateur

### v2.1.0 (2026-05-11)

- 🔄 Migration en mode plugin — aucune modification du code core
- ✅ `ctx.register_platform()` pour l'injection de l'adaptateur
- ✅ `standalone_sender_fn` pour la livraison cron
- ✅ Détection automatique du canal home
- ✅ Autorisation des utilisateurs via variables d'environnement
- ✅ Flux d'approbation i18nAppCard
- ✅ Plugin d'outils média & message — `lansenger_send_file`, `lansenger_send_image_url`
- ✅ `lansenger_revoke_message` et `lansenger_send_link_card` extraits de l'adaptateur en plugin d'outils autonome
- ✅ Implémentation de la méthode `send_link_card()` dans LansengerAdapter (précédemment manquante)
- ✅ Correction de l'erreur revoke/linkCard « Lansenger non configuré » — lecture des variables d'environnement au lieu de `load_gateway_config()`

## Licence

MIT — voir [LICENSE](LICENSE).