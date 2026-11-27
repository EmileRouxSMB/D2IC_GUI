# D2IC_GUI

Interface web locale pour la corrélation d’images 2D (**DIC seule**) et le couplage **DIC + thermique**. Elle prépare les études, pilote D2IC, affiche les champs et exporte vers ParaView.

## 1. Installer l’application autonome sous Windows

Télécharger l’archive ZIP pour **Windows x64** dans les fichiers de la [release V0.1](https://github.com/EmileRouxSMB/D2IC_GUI/releases/tag/V0.1).

1. Extraire entièrement le ZIP dans un dossier accessible en écriture.
2. Lancer `Verifier_D2IC_GUI.cmd` pour vérifier la distribution sur la machine.
3. Si la vérification réussit, lancer `D2IC_GUI.cmd` : l’interface s’ouvre dans le navigateur.
4. Garder la console ouverte pendant l’utilisation. Pour arrêter l’application, revenir dans la console et faire **Ctrl + C**.

Python et les dépendances CPU sont inclus : aucune installation de Python n’est nécessaire. Enregistrer les études et les résultats dans un dossier utilisateur distinct du dossier de l’application.

## 2. Utilisation simple

Suivre le [guide rapide du GUI](docs/GUIDE_RAPIDE.md), qui présente le parcours complet :

1. Créer ou ouvrir une étude.
2. Choisir les images VIS et l’image de référence.
3. Dessiner la ROI avec des rectangles ou des ellipses, puis créer le masque.
4. Générer le maillage.
5. Préparer et lancer le job.
6. Consulter les cartes de résultats, suivre des points, tracer une coupe et exporter les valeurs en CSV.

Les images sources restent à leur emplacement. Pour les fonctions avancées et le parcours **DIC + thermique**, voir le [manuel d’utilisation](docs/MANUEL_UTILISATION.md). Un [exemple synthétique](examples/README.md) est également disponible.

## 3. Développeurs : installer la version de développement

### Prérequis

Utiliser **Python 3.12 ou plus récent** et disposer des quatre dépôts sources dans un même dossier de travail :

```text
workspace/
  im_jax/
  D2IC/
  DICTHFusion/
  D2IC_GUI/
```

### Installation

Depuis ce dossier de travail, créer et activer un environnement virtuel.

Sous Windows, dans PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Sous Linux ou macOS :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Installer ensuite les quatre paquets en mode éditable :

```bash
python -m pip install --upgrade pip
python -m pip install -e ./im_jax -e ./D2IC -e ./DICTHFusion -e ./D2IC_GUI
```

### Lancement

```bash
python -m D2IC_GUI
```

Ouvrir [http://127.0.0.1:8765](http://127.0.0.1:8765) dans le navigateur. Pour ouvrir directement une étude existante :

```bash
python -m D2IC_GUI /chemin/vers/etude
```

Pour construire une distribution autonome avec Python embarqué, suivre le [guide de packaging](docs/PACKAGING.md).

### Organisation du code et références

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
