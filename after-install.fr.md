[English](after-install.md) | [简体中文](after-install.zhHans.md) | [繁体中文](after-install.zhHant.md) | [繁体中文香港](after-install.zhHantHK.md) | [Français](after-install.fr.md)

# 💠 Adaptateur Lansenger — Configuration post-installation

Deux plugins et une compétence ont été installés :

1. **lansenger-platform** — Adaptateur de canal de passerelle (active Lansenger comme canal de messagerie)
2. **lansenger-tools** — Outils de l'Agent pour envoyer des messages, fichiers, images, révoquer des messages, cartes linkCard
3. **lansenger-messaging** — Compétence qui enseigne à l'Agent comment choisir le bon outil Lansenger

## Configuration

### Option A : Configuration en une ligne (recommandée)

Remplacez `YOUR_APP_ID` et `YOUR_APP_SECRET` par vos identifiants réels, puis exécutez :

```bash
grep -q "^LANSENGER_APP_ID=" ~/.hermes/.env 2>/dev/null || echo "LANSENGER_APP_ID=YOUR_APP_ID" >> ~/.hermes/.env && \
grep -q "^LANSENGER_APP_SECRET=" ~/.hermes/.env 2>/dev/null || echo "LANSENGER_APP_SECRET=YOUR_APP_SECRET" >> ~/.hermes/.env
```

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

> 💡 L'App ID et l'App Secret peuvent être trouvés dans Lansenger → Contacts → Bot personnel (pas Espace de travail)

## Installation de la compétence

Après avoir installé les plugins, copiez la compétence dans le répertoire des compétences Hermes :

```bash
mkdir -p ~/.hermes/skills/mlops/lansenger-messaging
cp lansenger-adapter/skills/lansenger-messaging.md ~/.hermes/skills/mlops/lansenger-messaging/SKILL.md
```

Note : Hermes requiert que chaque compétence soit un répertoire contenant un fichier `SKILL.md`, et non un simple fichier `.md`.

Cette compétence enseigne à l'Agent la frontière de capacité des types de messages Lansenger (text vs formatText) et fournit un arbre de décision pour choisir l'outil correct. Sans elle, l'Agent peut choisir le mauvais type de message et perdre le formatage Markdown ou le support des attachments.

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