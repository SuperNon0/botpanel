# Logo de l'intégration Home Assistant

Home Assistant **ne lit pas** le logo depuis le dossier du composant
(`custom_components/botpanel/`). Il le récupère depuis le dépôt officiel
**[home-assistant/brands](https://github.com/home-assistant/brands)**, servi via
`https://brands.home-assistant.io/`.

Ce dossier contient les images **déjà aux bonnes tailles**, prêtes à être
soumises. Elles ont été générées depuis `app/web/static/logo.svg`.

```
brands/custom_integrations/botpanel/
├── icon.png        256×256   (icône carrée, fond transparent)
├── [email protected]     512×512
├── logo.png        256×256
└── [email protected]     512×512
```

## Comment faire apparaître le logo dans Home Assistant

1. Va sur https://github.com/home-assistant/brands et **fork** le dépôt.
2. Copie le dossier `custom_integrations/botpanel/` de **ce dossier** (`brands/`)
   dans le dépôt `brands` forké, au même chemin :
   `custom_integrations/botpanel/{icon.png,[email protected],logo.png,[email protected]}`.
3. Ouvre une **pull request** vers `home-assistant/brands`.
4. Une fois la PR **mergée**, le logo apparaît automatiquement dans Home Assistant
   (page Appareils et services, assistant de configuration) et dans HACS —
   **rien à changer** côté intégration ni côté HACS.

> Contraintes respectées par ces fichiers : PNG, carré, fond **transparent**
> autour du logo, `icon.png` = 256 px et `@2x` = 512 px. Voir les règles du dépôt
> `brands` (dossier `custom_integrations/`) si elles évoluent.

## Régénérer les images

Si le logo change (`app/web/static/logo.svg`) :

```bash
pip install pillow cairosvg
python - <<'PY'
import cairosvg, io
from PIL import Image
SRC = "app/web/static/logo.svg"; OUT = "brands/custom_integrations/botpanel"
def render(px):
    png = cairosvg.svg2png(url=SRC, output_width=px, output_height=px)
    return Image.open(io.BytesIO(png)).convert("RGBA")
for name, px in [("icon.png",256),("[email protected]",512),("logo.png",256),("[email protected]",512)]:
    render(px).save(f"{OUT}/{name}", format="PNG")
PY
```
