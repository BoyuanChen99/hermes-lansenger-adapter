[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)

# Adaptateur Hermes Lansenger

> 💠 Adaptateur de passerelle Lansenger + plugin d’outils média & messages pour Hermes Agent.

Connecte Hermes Agent à Lansenger — une plateforme de messagerie d’entreprise — via une connexion longue WebSocket pour la réception de messages en temps réel et via l’API HTTP pour l’envoi de messages.

Ce dépôt contient **deux plugins** :

| Plugin | Type | Ce qu’il fait |
|--------|------|---------------|
| `platforms/lansenger/` | plateforme | Adaptateur de canal de passerelle — recevoir & envoyer des messages |
| `lansenger-tools/` | autonome (outil) | Outils appelables par l’Agent : envoyer des messages/cartes/fichiers, révoquer des messages, requête groupes |

## Fonctionnalités

### Adaptateur de plateforme
- **Messagerie en temps réel** via connexion longue WebSocket (ping/pong intégré)
- **Support Markdown** utilisant le msgType `formatText` (avec @mentions optionnelles, API plus récente)
- **Cartes d'approbation** — appCard / approveCard avec mises à jour de statut en place après approbation/rejet
- **Détection automatique du canal principal** — le premier message p2p définit la cible de livraison par défaut
- **Persistance du type de chat** — map chat_id→groupe/dm entrante persistée pour le routage inter-processus
- **Livraison planifiée** — notifications planifiées via `standalone_sender_fn`
- **Autorisation des utilisateurs** — utilisateurs autorisés / autoriser tous les utilisateurs via des variables d’environnement
- **Zéro modification du core** — mode plugin pur, `git diff HEAD` reste INTACT
- **Politique de chat de groupe** — ouvert/liste blanche/désactivé avec dérogations par groupe (require_mention, auto_mention_reply, auto_quote_reply, filtrage allow_from par expéditeur)
- **Réponse automatique @mention** — @mentionne automatiquement l'expéditeur dans les réponses de groupe (userIds pour les utilisateurs, botIds pour les robots selon fromType 0/1)
- **Réponse automatique avec citation** — inclut automatiquement refMsgId faisant référence au message entrant (groupes + DMs)
- **Support multi-espace de travail** — respecte la variable d'environnement HERMES_HOME ; tous les fichiers token/chat_type/owner sont limités au profil actif
- **Analyse FormatText entrante** — analyse correctement les messages Markdown msgType=format provenant d'OpenClaw et d'autres robots

### Plugin d’outils média & messages
- **lansenger_send_text** — Envoyer du texte brut avec @mentions optionnelles et pièces jointes
- **lansenger_send_markdown** — Envoyer du texte Markdown avec @mentions optionnelles (API plus récente, pas de pièces jointes)
- **lansenger_send_file** — Envoyer tout fichier/image/vidéo local à un utilisateur ou groupe spécifique
- **lansenger_send_image_url** — Envoyer une image depuis une URL à un utilisateur ou groupe spécifique
- **lansenger_revoke_message** — Révoquer un message envoyé (détection automatique groupe/DM via chat_id)
- **lansenger_send_link_card** — Envoyer une carte linkCard (6 champs requis par la spec)
- **lansenger_send_app_articles** — Envoyer une carte multi-article appArticles
- **lansenger_send_app_card** — Envoyer une carte riche appCard avec mises à jour dynamiques optionnelles
- **lansenger_send_approve_card** — Envoyer une carte approveCard avec des boutons cliquables pour les workflows interactifs
- **lansenger_update_dynamic_card** — Mettre à jour le statut d’une appCard dynamique en place
- **lansenger_query_groups** — Requête la liste des ID de groupes du robot
- **lansenger_get_group_info** — Obtenir les informations détaillées d'un groupe (nom, membres, état)
- **lansenger_get_group_members** — Obtenir la liste des membres d'un groupe avec pagination
- **lansenger_check_in_group** — Vérifier si un utilisateur ou un robot est dans un groupe
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

> **Note :** Le bundle s’étend automatiquement au premier redémarrage du gateway. Les sous-plugins (`lansenger-platform` et `lansenger-tools`) sont automatiquement copiés dans `~/.hermes/plugins/`, auto-activés dans `config.yaml`, et chargés en place — pas besoin d’exécuter des commandes `hermes plugins enable` séparées pour chaque sous-plugin.

## Configuration

### Variables d'environnement requises

Ajoutez ces variables à `~/.hermes/.env` :

| Variable | Description | Exemple |
|----------|-------------|---------|
| `LANSENGER_APP_ID` | ID App du Bot | `your-app-id` |
| `LANSENGER_APP_SECRET` | Secret App du Bot | `your-app-secret` |

**Chemin des identifiants :** Lansenger (client desktop) → Contacts → Rebots → Robots personnels → cliquer sur l’icône ℹ️ pour voir les identifiants (le client mobile ne permet pas de voir les identifiants)

### Variables d’environnement optionnelles

| Variable | Description | Valeur par défaut |
|----------|-------------|-------------------|
| `LANSENGER_API_GATEWAY_URL` | URL de la passerelle API | `https://open.e.lanxin.cn/open/apigw` |
| `LANSENGER_ALLOWED_USERS` | IDs d’utilisateurs autorisés (séparés par des virgules) | — |
| `LANSENGER_ALLOW_ALL_USERS` | Autoriser tous les utilisateurs (développement uniquement) | `false` |
| `LANSENGER_HOME_CHANNEL` | ID de chat par défaut pour la livraison planifiée | Détection automatique |
| `LANSENGER_HOOK_LOGGING` | Activer/désactiver la journalisation des hooks | `true` |

### config.yaml

Les identifiants peuvent être configurés via des variables d'environnement (recommandé) ou config.yaml. Les variables d'environnement sont prioritaires.

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      # Identifiants (optionnel si défini via variables d'env; variables d'env prioritaires)
      # app_id: "your-app-id"
      # app_secret: "your-app-secret"
      # api_gateway_url: "https://open.e.lanxin.cn/open/apigw"
      # Optionnel : désactiver la journalisation des hooks (défaut : true)
      # hook_logging: false
```

## Outils média & messages (de lansenger-tools)

Ces outils permettent à l’Agent d’envoyer des messages, fichiers, images, cartes, de révoquer des messages et de requête groupes — tous appelables indépendamment par le LLM. Les identifiants sont lus depuis les variables d’environnement (LANSENGER_APP_ID/SECRET), et non depuis `load_gateway_config()`.

| Outil | Paramètres | Description |
|------|-----------|-------------|
| `lansenger_send_text` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`?, `file_path`?, `media_type`? | Envoyer du texte brut avec @mentions optionnelles et pièces jointes |
| `lansenger_send_markdown` | `chat_id`, `content`, `reminder_all`?, `reminder_user_ids`? | Envoyer du texte Markdown avec @mentions optionnelles (API plus récente, pas de pièces jointes) |
| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Envoyer un fichier/image/vidéo local à un utilisateur ou groupe |
| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Télécharger une image depuis une URL et l’envoyer comme image native |
| `lansenger_revoke_message` | `message_ids`, `chat_id`? | Révoquer un message (détection auto groupe/DM via chat_id) |
| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`, `icon_link`, `from_name`, `from_icon_link`, `pc_link`? | Envoyer une carte linkCard (6 champs requis par la spec, pc_link optionnel) |
| `lansenger_send_app_articles` | `chat_id`, `articles` | Envoyer une carte multi-article appArticles |
| `lansenger_send_app_card` | `chat_id`, `body_title`, `head_title`?, `is_dynamic`?, `head_status_info`?, ... | Envoyer une carte riche appCard avec mises à jour dynamiques optionnelles |
| `lansenger_send_approve_card` | `chat_id`, `head_title`, `body_title`, `body_content`?, `buttons`, `fields`?, `head_status`?, `head_status_color`? | Envoyer une carte approveCard avec des boutons cliquables pour les workflows interactifs |
| `lansenger_update_dynamic_card` | `msg_id`, `head_status_info`?, `is_last_update`? | Mettre à jour le statut d’une appCard dynamique en place |
| `lansenger_query_groups` | `page_offset`?, `page_size`? | Requête la liste des ID de groupes du robot |
| `lansenger_get_group_info` | `group_id` | Obtenir les informations détaillées d'un groupe (nom, membres, état) |
| `lansenger_get_group_members` | `group_id`, `page_offset`?, `page_size`? | Obtenir la liste des membres d'un groupe avec pagination |
| `lansenger_check_in_group` | `group_id`, `staff_id`? | Vérifier si un utilisateur ou un robot est dans un groupe |

**Exemples d’utilisation (prompts de l’Agent) :**

```
"Envoyer le rapport report.pdf à l’utilisateur 2285568-abc123"
"Partager cette image du graphique avec le chat de groupe du projet"
"Télécharger cette image URL et l’envoyer à mon collègue"
"Révoquer le message que j’ai envoyé à l’utilisateur"
"Envoyer une carte linkCard avec le titre 'Documentation du projet' et le lien https://..."
"Envoyer une carte d’approbation appCard pour la commande dangereuse"
"Mettre à jour le statut de la carte d’approbation à 'approuvé'"
```

**Limitations :**
- Les limites de taille de fichier sont déterminées par la configuration Lansenger de l’organisation (aucun plafond fixe)
- Les légendes de média utilisent du texte brut (pas de Markdown) — pour du texte Markdown, envoyer séparément
- `lansenger_send_file` détecte automatiquement le media_type depuis l’extension si non spécifié
- `lansenger_revoke_message` : le message système est fixe (non personnalisable)
- `lansenger_send_link_card` : 6 champs requis par la spec API (title, description, iconLink, link, fromName, fromIconLink); pc_link optionnel
- `lansenger_send_markdown` @mentions : capacité API plus récente; les anciennes versions acceptent sans notification
- Vidéo (mediaType=1) nécessite 2 mediaIds: [videoId, coverImageId] (upload vidéo et couverture séparément, puis combiner)

## Architecture

```
hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
                          ├── plugin.yaml                     # manifeste racine (type : bundle)
                          ├── platforms/lansenger/            # Adaptateur de passerelle
                          │   ├── plugin.yaml                 # manifeste (type : plateforme)
                          │   ├── __init__.py                  # register() → ctx.register_platform()
                          │   ├── adapter.py                   # adaptateur principal (héritage multiple des modules Mixin)
                          │   ├── commands.py                  # enregistrement des commandes slash
                          │   └── _*.py / ws_*.py             # modules Mixin modulaires (WS, messages, jeton, média, groupes, cartes, approbation, i18n)
                          ├── lansenger-tools/           # Outils média & messages
                          │   ├── plugin.yaml                 # manifeste (type : autonome)
                          │   ├── __init__.py                  # register() → ctx.register_tool()
                          │   ├── schemas.py                   # descriptions d’outils pour le LLM
                          │   └── tools.py                     # implémentations des gestionnaires
                          ├── skills/                          # Compétence de décision de l’Agent
                          │   └── lansenger-messaging/           # répertoire skill (SKILL.md + references) d’outils + docs token
                          ├── README.md
                          ├── LICENSE
                          ├── VERSION
                          ├── after-install.md
                          ├── pyproject.toml                   # point d’entrée pip
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

Voir [CHANGELOG.md](CHANGELOG.md) pour l’historique détaillé des versions.

## Licence

MIT — voir [LICENSE](LICENSE).