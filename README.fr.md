     1|[English](README.md) | [简体中文](README.zhHans.md) | [繁体中文](README.zhHant.md) | [繁体中文香港](README.zhHantHK.md) | [Français](README.fr.md)
     2|
     3|# Adaptateur Hermes Lansenger
     4|
     5|> 💠 Adaptateur de passerelle Lansenger + plugin d’outils média & messages pour Hermes Agent.
     6|
     7|Connecte Hermes Agent à Lansenger — une plateforme de messagerie d’entreprise — via une connexion longue WebSocket pour la réception de messages en temps réel et via l’API HTTP pour l’envoi de messages.
     8|
     9|Ce dépôt contient **deux plugins** :
    10|
    11|| Plugin | Type | Ce qu’il fait |
    12||--------|------|---------------|
    13|| `platforms/lansenger/` | plateforme | Adaptateur de canal de passerelle — recevoir & envoyer des messages |
    14|| `lansenger-tools/` | autonome (outil) | Outils appelables par l’Agent : envoyer des fichiers/images, révoquer des messages, envoyer des linkCard |
    15|
    16|## Fonctionnalités
    17|
    18|### Adaptateur de plateforme
    19|- **Messagerie en temps réel** via connexion longue WebSocket
    20|- **Support Markdown** utilisant le msgType `formatText`
    21|- **i18nAppCard** — cartes interactives de flux d’approbation
    22|- **Détection automatique du canal principal** — le premier message p2p définit la cible de livraison par défaut
    23|- **Livraison planifiée** — notifications planifiées via `standalone_sender_fn`
    24|- **Autorisation des utilisateurs** — utilisateurs autorisés / autoriser tous les utilisateurs via des variables d’environnement
    25|- **Zéro modification du core** — mode plugin pur, `git diff HEAD` reste INTACT
    26|
    27|### Plugin d’outils média & messages
    28|- **lansenger_send_text** — Envoyer des messages en texte brut avec @mentions optionnelles (groupe/staff uniquement) et pièces jointes
    29|- **lansenger_send_markdown** — Envoyer des messages au format Markdown (pas de @mentions ni pièces jointes)
    30|- **lansenger_send_file** — Envoyer tout fichier/image/vidéo local à un utilisateur ou groupe spécifique
    31|- **lansenger_send_image_url** — Envoyer une image depuis une URL à un utilisateur ou groupe spécifique
    32|- **lansenger_revoke_message** — Révoquer un message Lansenger envoyé 🗑️
    33|- **lansenger_send_link_card** — Envoyer un message de carte linkCard Lansenger 🔗
    34|- **Détection automatique du type de média** — images/vidéos/documents classifiés par extension
    35|- **Contrôle des identifiants** — outils masqués lorsque LANSENGER_APP_ID/SECRET ne sont pas configurés
    36|
    37|## Installation rapide
    38|
    39|### Via le gestionnaire de plugins Hermes (recommandé)
    40|
    41|```bash
    42|hermes plugins install lansenger-pm/hermes-lansenger-adapter
    43|hermes plugins enable hermes-lansenger-adapter
    44|hermes gateway restart
    45|```
    46|
    47|### Installation manuelle
    48|
    49|Clonez ce dépôt dans `~/.hermes/plugins/` :
    50|
    51|```bash
    52|cd ~/.hermes/plugins/
    53|git clone https://github.com/lansenger-pm/hermes-lansenger-adapter.git hermes-lansenger-adapter
    54|hermes plugins enable hermes-lansenger-adapter
    55|hermes gateway restart
    56|```
    57|
    58|### Via pip (avancé)
    59|
    60|```bash
    61|pip install hermes-lansenger-adapter
    62|hermes plugins enable hermes-lansenger-adapter
    63|hermes gateway restart
    64|```
    65|
    66|> **Note :** Le bundle s’étend automatiquement au premier redémarrage du gateway. Les sous-plugins (`lansenger-platform` et `lansenger-tools`) sont automatiquement copiés dans `~/.hermes/plugins/`, auto-activés dans `config.yaml`, et chargés en place — pas besoin d’exécuter des commandes `hermes plugins enable` séparées pour chaque sous-plugin.
    67|
    68|## Configuration
    69|
    70|### Required Environment Variables
    71|
    72|Ajoutez ces variables à `~/.hermes/.env` :
    73|
    74|| Variable | Description | Exemple |
    75||----------|-------------|---------|
    76|| `LANSENGER_APP_ID` | ID App du Bot | `your-app-id` |
    77|| `LANSENGER_APP_SECRET` | Secret App du Bot | `your-app-secret` |
    78|
    79|**Chemin des identifiants :** Lansenger (client desktop) → Contacts → Rebots → Robots personnels → cliquer sur l’icône ℹ️ pour voir les identifiants (le client mobile ne permet pas de voir les identifiants)
    80|
    81|### Variables d’environnement optionnelles
    82|
    83|| Variable | Description | Valeur par défaut |
    84||----------|-------------|-------------------|
    85|| `LANSENGER_API_GATEWAY_URL` | URL de la passerelle API | `https://open.e.lanxin.cn/open/apigw` |
    86|| `LANSENGER_ALLOWED_USERS` | IDs d’utilisateurs autorisés (séparés par des virgules) | — |
    87|| `LANSENGER_ALLOW_ALL_USERS` | Autoriser tous les utilisateurs (développement uniquement) | `false` |
    88|| `LANSENGER_HOME_CHANNEL` | ID de chat par défaut pour la livraison planifiée | Détection automatique |
    89|
    90|### config.yaml
    91|
    92|```yaml
    93|platforms:
    94|  lansenger:
    95|    enabled: true
    96|```
    97|
    98|## Outils média & messages (de lansenger-tools)
    99|
   100|Ces outils permettent à l’Agent d’envoyer des fichiers, images et vidéos, de révoquer des messages et d’envoyer des cartes linkCard — tous appelables indépendamment par le LLM. Les identifiants sont lus depuis les variables d’environnement (LANSENGER_APP_ID/SECRET), et non depuis `load_gateway_config()`.
   101|
   102|| Outil | Paramètres | Description |
   103||------|-----------|-------------|
   104|| `lansenger_send_text` | `chat_id`, `message`, `reminder_all`?, `reminder_user_ids`?, `media_paths`? | Envoyer du texte brut avec @mentions optionnelles (groupe/staff uniquement) et pièces jointes |
   105|| `lansenger_send_markdown` | `chat_id`, `message` | Envoyer du texte Markdown (pas de @mentions ni pièces jointes) |
   106|| `lansenger_send_file` | `chat_id`, `file_path`, `caption`?, `media_type`? | Envoyer un fichier/image/vidéo local à un utilisateur ou groupe |
   107|| `lansenger_send_image_url` | `chat_id`, `image_url`, `caption`? | Télécharger une image depuis une URL et l’envoyer comme image native |
   108|| `lansenger_revoke_message` | `message_ids`, `chat_type`?, `sender_id`? | Révoquer un message Lansenger envoyé (le prompt système est fixe, non personnalisable) |
   109|| `lansenger_send_link_card` | `chat_id`, `title`, `link`, `description`?, `icon_link`?, `pc_link`?, `from_name`?, `from_icon_link`? | Envoyer un message de carte linkCard Lansenger |
   110|
   111|**Exemples d’utilisation (prompts de l’Agent) :**
   112|
   113|```
   114|"Envoyer le rapport report.pdf à l’utilisateur 2285568-abc123"
   115|"Partager cette image du graphique avec le chat de groupe du projet"
   116|"Télécharger cette image URL et l’envoyer à mon collègue"
   117|"Révoquer le message que j’ai刚刚 envoyé à l’utilisateur"
   118|"Envoyer une carte link card à l’utilisateur avec le titre 'Documentation du projet' et le lien https://..."
   119|```
   120|
   121|**Limitations :**
   122|- Les limites de taille de fichier sont déterminées par la configuration Lansenger de l’organisation (aucun plafond fixe)
   123|- Les légendes de média utilisent du texte brut (pas de Markdown) — pour du texte Markdown, envoyer séparément
   124|- `lansenger_send_file` détecte automatiquement le media_type depuis l’extension si non spécifié
   125|- `lansenger_revoke_message` : pour les types de chat staff/groupe, `sender_id` est requis
   126|
   127|## Architecture
   128|
   129|```
   130|hermes plugins install → clone to ~/.hermes/plugins/hermes-lansenger-adapter/
   131|                          ├── plugin.yaml                     # manifeste racine (type : bundle)
   132|                          ├── platforms/lansenger/            # Adaptateur de passerelle
   133|                          │   ├── plugin.yaml                 # manifeste (type : plateforme)
   134|                          │   ├── __init__.py                  # register() → ctx.register_platform()
   135|                          │   └── adapter.py                   # adaptateur complet (pas de gestionnaires d’outils ici)
   136|                          ├── lansenger-tools/           # Outils média & messages
   137|                          │   ├── plugin.yaml                 # manifeste (type : autonome)
   138|                          │   ├── __init__.py                  # register() → ctx.register_tool()
   139|                          │   ├── schemas.py                   # descriptions d’outils pour le LLM
   140|                          │   └── tools.py                     # implémentations des gestionnaires
   141|                          ├── skills/                          # Compétence de décision de l’Agent
   142|                          │   └── lansenger-messaging.md       # stratégie de sélection d’outils + docs token
   143|                          ├── README.md
   144|                          ├── LICENSE
   145|                          ├── VERSION
   146|                          ├── after-install.md
   147|                          ├── pyproject.toml                   # point d’entrée pip
   148|                          └── .gitignore
   149|```
   150|
   151|## Dépendances
   152|
   153|- `websockets` — Client WebSocket pour connexion longue
   154|- `httpx` — Client HTTP pour appels API (aussi utilisé par les outils média)
   155|
   156|## Mise à jour
   157|
   158|Pour mettre à jour vers la dernière version :
   159|
   160|```bash
   161|hermes plugins update hermes-lansenger-adapter
   162|hermes gateway restart
   163|```
   164|
   165|## Journal des modifications
   166|
   167|### v2.6.0 — Approbation : i18nAppCard → appCard dynamique
   168|
   169|- **appCard dynamique (isDynamic=True)** : Les cartes d’approbation utilisent appCard au lieu de i18nAppCard, permettant les mises à jour de statut en place.
   170|- **Détection de langue** : `_user_lang_map` détecte zh/en depuis les messages entrants. Contenu des cartes adapté automatiquement.
   171|
   172|
   173|### v2.5.0 — appArticles, appCard, mise à jour dynamique, routage groupe, requête groupes
   174|
   175|### v2.4.2 — Canal d’accueil auto-amélioré
   176|
   177|- **Auto-sethome**: La première conversation DM est automatiquement désignée comme canal d’accueil Lansenger. Si aucun `home_channel` est configuré, ou si un canal existant est un groupe, le premier DM le remplace (DM > groupe). Écrit `config.yaml` et `os.environ` silencieusement. Suit le modèle AutoSetHomeMiddleware de Yuanbao.
   178|
   227|## Licence
   228|
   229|MIT — voir [LICENSE](LICENSE).