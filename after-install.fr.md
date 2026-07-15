[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 Adaptateur Lansenger — Configuration post-installation

Un plugin Bundle et deux compétences ont été installés :

1. **hermes-lansenger-adapter** — Conteneur Bundle (s'auto-expand en `lansenger-platform` + `lansenger-tools`)
2. **lansenger-messaging** — Compétence qui enseigne à l'Agent comment choisir le bon outil Lansenger
3. **lansenger-setup** — Compétence qui enseigne à l'Agent comment configurer le plugin Lansenger

## Configuration

### Option A : Assistant de configuration interactif (recommandé)

Exécutez l'assistant de configuration intégré — il vous guide étape par étape pour chaque identifiant :

```bash
hermes setup gateway
```

Sélectionnez **Lansenger** dans la liste des plateformes, puis collez votre App ID, App Secret, et fournissez l'URL de la passerelle API (ex. `https://apigw.lx.qianxin.com` pour le cloud public). Les valeurs déjà configurées sont affichées (les secrets sont masqués) et peuvent être remplacées.

> 💡 L'App ID et l'App Secret se trouvent dans Lansenger desktop → Contacts → Robots → Robots personnels → icône ℹ️ (le client mobile ne permet pas de voir les identifiants)

### Option B : config.yaml

Ajoutez la configuration suivante à `~/.hermes/config.yaml` sous `platforms.lansenger` :

```yaml
platforms:
  lansenger:
    enabled: true
    extra:
      app_id: "YOUR_APP_ID"
      app_secret: "YOUR_APP_SECRET"
      api_gateway_url: "https://apigw.lx.qianxin.com"   # requis
```

### Option C : fichier .env (manuel)

Éditez `~/.hermes/.env` et ajoutez :

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://apigw.lx.qianxin.com
```

## Redémarrer la passerelle

Après la configuration, redémarrez la passerelle Hermes :

```bash
hermes gateway restart
```

## Vérification

Vérifiez que le plugin est chargé :
- `hermes tools list` devrait afficher `lansenger-tools` dans la section Plugin toolsets
- `hermes plugins list` devrait afficher `lansenger-platform` et `lansenger-tools` comme activés

## Configuration des groupes

Tous les paramètres utilisent des **booléens natifs YAML** (`true`/`false`, sans guillemets). Les variables d'environnement utilisent des chaînes.

### Paramètres globaux

```yaml
platforms:
  lansenger:
    extra:
      group_policy: open              # open | allowlist | disabled
      require_mention: true           # @bot requis dans les groupes
      respond_to_at_all: false       # ne répond pas à @all quand require_mention=true
      auto_mention_reply: false       # @expéditeur auto dans les réponses de groupe
      auto_quote_reply: false         # refMsgId auto dans les réponses (groupes + DMs)
```

### Remplacements par groupe

```yaml
platforms:
  lansenger:
    extra:
      groups:
        "<group_id>":
          enabled: true
          require_mention: false
          respond_to_at_all: false
          auto_mention_reply: true
          auto_quote_reply: true
          allow_from:
            - "<staff_id>"
```

### Priorité de décision (de haut en bas, première correspondance)

1. `enabled: false` par groupe → bloqué
2. `allow_from` par groupe non vide et expéditeur absent de la liste → bloqué
3. `enabled: true` par groupe → ignore la politique globale
4. `group_policy` global → `disabled` bloque tout / `allowlist` vérifie les clés de la map `groups`
5. `group_allow_from` global (niveau expéditeur) non vide et expéditeur absent de la liste → bloqué
6. `require_mention` (par groupe > global) à true et `is_at_me=false` → bloqué (`respond_to_at_all` false par défaut, @all est bloqué)

## Fonctionnalités de réponse automatique

### autoMentionReply

Lorsqu'il est activé, les réponses de groupe mentionnent automatiquement l'expéditeur avec @. Utilise `fromType` pour distinguer :
- `fromType=0` (utilisateur) → `reminder.userIds`
- `fromType=1` (application/bot) → `reminder.botIds`

### autoQuoteReply

Lorsqu'il est activé, les réponses incluent automatiquement `refMsgId` faisant référence au message entrant. Fonctionne dans les groupes et les discussions privées.

## Commandes Slash

Au démarrage, l'adaptateur enregistre automatiquement toutes les commandes slash intégrées et plugins d'Hermes (ex. `/help`, `/status`, `/approve`) dans l'API Bot Lansenger. Les commandes apparaissent dans la barre de saisie du chat Lansenger.

### Désactiver l'enregistrement automatique

```yaml
platforms:
  lansenger:
    extra:
      commands:
        native: false   # désactiver par profile
```

Ou via variable d'env : `LANSENGER_SLASH_COMMANDS_NATIVE=0`

### Permissions des commandes

Contrôlez quels chats peuvent voir chaque commande :

```yaml
platforms:
  lansenger:
    extra:
      command_permissions:
        approve: owner       # propriétaire uniquement
        status: everyone     # tous les chats (défaut)
        restart: disabled    # exclure cette commande
```

| Permission | Portée |
|-----------|--------|
| `owner` | Chat privé du propriétaire |
| `admin` | Propriétaire + admins de groupe |
| `everyone` | Propriétaire + tous les groupes (défaut) |
| `disabled` | Commande exclue |

## Approbation des Commandes Dangereuses

Quand Hermes détecte une commande dangereuse (ex. `rm -rf`, `curl | sh`, `chmod 777`), il suspend l'exécution et envoie une **approveCard** avec des boutons cliquables. Approuvez ou refusez directement :

- En cliquant sur les boutons de la carte
- En répondant `/approve`, `/approve session`, `/approve always`, ou `/deny`

La carte se met à jour sur place pour afficher la décision (ex. « Allowed once »). Bascule automatiquement vers appCard si le serveur ne supporte pas approveCard.

## Multi-espace de travail (Profiles)

Hermes prend en charge plusieurs espaces de travail isolés via les Profiles :

```bash
hermes profile create bot-prod
hermes profile create bot-test
hermes -p bot-prod gateway start
hermes -p bot-test gateway start
```

Chaque profil possède son propre config.yaml, sessions, mémoires, compétences, journaux et fichiers de données (token, chat_type, owner).

## Vue d'ensemble des outils

```
┌───────────────────────────────┬──────────────┬──────────────┬──────────────┐
│  Tool                         │  Markdown    │  @mention    │  Attachments │
├───────────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text          │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown      │  ✓           │  ✓ (opt)     │  ✗           │
│  lansenger_send_file          │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_image_url     │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_link_card     │  —           │  —           │  —           │
│  lansenger_send_app_articles  │  —           │  —           │  —           │
│  lansenger_send_app_card      │  ✗ (div)     │  —           │  —           │
│  lansenger_update_dynamic_card│  —           │  —           │  —           │
│  lansenger_revoke_message     │  —           │  —           │  —           │
│  lansenger_query_groups       │  —           │  —           │  —           │
└───────────────────────────────┴──────────────┴──────────────┴──────────────┘

@mention notes :
- send_text : fonctionne en chat groupe ; chat privé supporte mais inutile (un seul participant)
- send_markdown : capacité API plus récente ; anciennes versions acceptent
  sans notification. En chat groupe, recommandé d'inclure @姓名 dans le texte.
```