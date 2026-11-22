# Installation et distributions portables

## Préparer les outils de construction

Depuis le workspace contenant les quatre dépôts, avec Python ≥ 3.12 :

```bash
python -m pip install uv
python -m pip install -e ./D2IC_GUI --no-deps
```

Cette installation minimale expose les constructeurs, qui préparent leur propre
runtime. Pour exécuter le GUI dans l’environnement courant, installer aussi ses
dépendances selon le [README](../README.md#installation).

## Construction portable

```bash
python -m D2IC_GUI.build_portable
```

Le constructeur crée un runtime isolé avec CPython 3.12, les composants
scientifiques locaux, les dépendances CPU et OpenCV headless. La compilation
résout et télécharge les dépendances. Les sorties sont placées dans `dist/` et
ne remplacent pas une sortie existante. Options courantes :

```bash
python -m D2IC_GUI.build_portable --output /chemin/livraisons --name D2IC_GUI-v2
python -m D2IC_GUI.build_portable --constraints /chemin/requirements.lock
python -m D2IC_GUI.build_portable --no-archive
```

Le fichier `requirements.lock` permet de réutiliser les versions résolues ; une
reconstruction reproductible demande aussi les mêmes sources et la même version
de Python.

## Cibles et validation

Construire sur chaque système et architecture visés. Les cibles documentées
sont Linux x86_64, Windows x64 et macOS selon l’architecture de construction.
Les lanceurs portables utilisent JAX CPU, ouvrent le navigateur sur une adresse
locale et doivent rester actifs dans leur console. Conserver études et résultats
dans un dossier utilisateur accessible en écriture, distinct de l’installation.

`build_windows` peut assembler depuis Linux ou macOS une archive destinée à
Windows. Les contrôles statiques de l’archive ne remplacent pas une exécution
sur Windows ; `validated_on_windows` reste faux jusqu’à cette vérification.
Une validation Linux x86_64 ne garantit pas la compatibilité avec d’autres
versions de glibc. Windows et macOS doivent être lancés et exercés sur leurs
systèmes cibles avant d’être annoncés comme validés.

Pour le lancement du paquet, extraire l’archive entière puis utiliser
`D2IC_GUI.sh`, `D2IC_GUI.cmd` ou `D2IC_GUI.command` selon le système. Garder la
console ouverte ; `Ctrl+C` arrête le serveur. Fermer le navigateur seul ne
l’arrête pas.
