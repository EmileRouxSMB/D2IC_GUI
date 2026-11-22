# D2IC_GUI

Interface web locale pour la corrélation d’images 2D (**DIC seule**) et le couplage **DIC + thermique**. Elle prépare les études, pilote D2IC, affiche les champs et exporte vers ParaView.

## Installation

Python 3.12 ou plus récent. Depuis le workspace contenant les quatre dépôts :

```bash
python -m pip install -e ./im_jax -e ./D2IC -e ./DICTHFusion -e ./D2IC_GUI
python -m D2IC_GUI
```

Ouvrir [http://127.0.0.1:8765](http://127.0.0.1:8765). Pour rouvrir une étude :

```bash
python -m D2IC_GUI /chemin/vers/etude
```

Une distribution autonome CPU avec Python embarqué peut être construite : [guide de packaging](docs/PACKAGING.md).

## Utilisation rapide

1. Créer une étude dans **Fichier** et choisir **DIC seule** ou **DIC + thermique**.
2. Sélectionner les images VIS, la référence et les temps d’acquisition.
3. Importer ou dessiner la ROI, puis **Mailler** ; confirmer l’échelle pour les sorties en mm.
4. En parcours couplé, approuver la correspondance VIS–TH et vérifier la synchronisation.
5. Dans **Job Manager**, **Préparer le job**, corriger les erreurs éventuelles puis **Lancer**.
6. Examiner **Résultats** et retrouver les fichiers ParaView dans **Export**.

Les images sources restent à leur emplacement. Voir le [manuel d’utilisation](docs/MANUEL_UTILISATION.md) et l’[exemple synthétique](examples/README.md).

## Développement et architecture

```text
src/D2IC_GUI/   paquet Python, catalogue et actifs web
  static/      interface HTML/CSS/JavaScript
  examples/    générateur synthétique importable
docs/          contrats, spécifications et guides
tests/         vérifications Python et Node
examples/      configurations et lanceur d’exemple
```

FastAPI sert l’interface ; un worker séparé lance D2IC et la fusion thermique. `roi.py` partage la préparation des masques ; `results.py` consulte les champs indépendamment du transport HTTP. Les paramètres d’étude sont enregistrés dans `config.toml`.

Références : [contrats scientifiques et intégration](docs/INTEGRATION_CONTRACTS.md), [architecture](docs/SPEC_TECHNIQUE.md), [résultats persistés](docs/RESULT_MODEL.md), [ajout de paramètres](docs/CONFIG_SCHEMA.md), [travaux restants](docs/ROADMAP_DEV.md).

Les [instructions de recherche](../AGENTS.md) et leur [routage haut/bas niveau](../.agents/skills/research-task-routing/SKILL.md) s’appliquent. Les commandes de vérification et leurs limites sont dans [tests/memory.md](tests/memory.md).
