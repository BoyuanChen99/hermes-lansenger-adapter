[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 Adaptateur Lansenger — Configuration post-installation

Deux plugins et une compétence ont été installés :

1. **lansenger-platform** — Adaptateur de canal de passerelle (active Lansenger comme canal de messagerie)
1. **hermes-lansenger-adapter** — Conteneur Bundle (auto-expands into `lansenger-platform` + `lansenger-tools`)
2. **lansenger-messaging** — Compétence qui enseigne à l'Agent comment choisir le bon outil Lansenger

> ⚠️ **Ne pas exécuter `hermes plugins enable lansenger-platform` ou `hermes plugins enable lansenger-tools` manuellement** — le bundle auto-expand et auto-active les deux sous-plugins au redémarrage du gateway. L'activation manuelle échouera car les sous-plugins sont encore dans le bundle.

> 💡 Si vous devez activer les sous-plugins *avant* le redémarrage du gateway, exécutez d'abord le script d'expansion :
> ```bash
> python3 ~/.hermes/plugins/hermes-lansenger-adapter/expand_sub_plugins.py
> ```
> Vous pouvez ensuite exécuter `hermes plugins enable lansenger-platform` et `hermes plugins enable lansenger-tools`.

### Option A : Assistant de configuration interactif (recommandé)

Exécutez l'assistant de configuration intégré — il vous guide étape par étape pour chaque identifiant :

```bash
hermes setup gateway
```

Sélectionnez **Lansenger** dans la liste des plateformes, puis collez votre App ID, App Secret, et confirmez éventuellement l'URL de la passerelle API. Les valeurs déjà configurées sont affichées (les secrets sont masqués) et peuvent être remplacées.

> 💡 L'App ID et l'App Secret se trouvent dans Lansenger desktop → Contacts → Rebots → Robots personnels → icône ℹ️ (le client mobile ne permet pas de voir les identifiants)

### Option B : config.yaml

Ajoutez la configuration suivante à `~/.hermes/config.yaml` sous `platforms.lansenger` :

```yaml
platforms:
  lansenger:
    app_id: "YOUR_APP_ID"
    app_secret: "YOUR_APP_SECRET"
    api_gateway_url: "https://open.e.lanxin.cn/open/apigw"   # ou votre URL de passerelle personnalisée
```

### Option C : fichier .env (manuel)

Éditez `~/.hermes/.env` et ajoutez :

```
LANSENGER_APP_ID=YOUR_APP_ID
LANSENGER_APP_SECRET=YOUR_APP_SECRET
LANSENGER_API_GATEWAY_URL=https://open.e.lanxin.cn/open/apigw
```

## Installation de la compétence

Après avoir installé les plugins, installez la compétence lansenger-messaging (enseigne à l'Agent la frontière de capacité des types de messages et l'arbre de décision des outils) :

**Option A : Depuis le dépôt local cloné (Le plus rapide) :**

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging && cp ~/.hermes/plugins/hermes-lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

**Option B : Depuis l'URL GitHub (Fonctionne sans clone local) :**

```bash
hermes skills install --force --category lansenger https://github.com/lansenger-pm/hermes-lansenger-adapter/raw/main/skills/lansenger-messaging.md
```

Sans cette compétence, l'Agent peut choisir le mauvais type de message et perdre le formatage Markdown ou le support des attachments.

## Redémarrer la passerelle

Après la configuration, redémarrez la passerelle Hermes :

```bash
hermes gateway restart
```

## Vérification

Vérifiez que le plugin est chargé :
- `hermes tools list` devrait afficher `lansenger-tools` dans la section Plugin toolsets
- `hermes plugins list` devrait afficher `hermes-lansenger-adapter` et `lansenger-tools` comme activés

## Vue d'ensemble des outils

```
┌─────────────────────────┬──────────────┬──────────────┬──────────────┐
│  Tool                   │  Markdown    │  @mention    │  Attachments │
├─────────────────────────┼──────────────┼──────────────┼──────────────┤
│  lansenger_send_text    │  ✗           │  ✓           │  ✓           │
│  lansenger_send_markdown│  ✓           │  ✗           │  ✗           │
│  lansenger_send_file    │  ✗           │  —           │  ✓ (only)    │
│  lansenger_send_image_url│ ✗           │  —           │  ✓ (only)    │
│  lansenger_revoke_message│ —           │  —           │  —           │
│  lansenger_send_link_card│ —           │  —           │  —           │
└─────────────────────────┴──────────────┴──────────────┴──────────────┘
```