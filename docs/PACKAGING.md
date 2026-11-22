# Distribution autonome CPU

Le script `build_portable.py` construit un dossier autonome et une archive pour
le système et l’architecture de la machine de construction. Il inclut CPython
3.12, les moteurs locaux D2IC/DICTHFusion/im_jax et OpenCV **headless**.
Le PC destinataire utilise son navigateur habituel ; il n’a besoin ni de
Python installé, ni d’Internet pour exécuter l’application.

## Construire

Depuis la racine du workspace, sur une machine avec Python >= 3.12 :

```bash
python -m pip install uv
python -m pip install -e ./D2IC_GUI --no-deps
python -m D2IC_GUI.build_portable
```

La racine du workspace contient les dossiers `D2IC_GUI`, `D2IC`,
`DICTHFusion` et `im_jax`. L’installation éditable sans dépendances rend le
module de construction accessible ; le script assemble ensuite son propre
environnement isolé.

La construction télécharge Python et les dépendances. Elle ne modifie pas
l’environnement scientifique existant : les installations sont réalisées
uniquement dans la copie temporaire du Python à embarquer.

Sorties par défaut sous `dist/` :

- `D2IC_GUI-cpu-linux-x86_64/` et `.tar.gz` sous Linux x64 ;
- `D2IC_GUI-cpu-windows-amd64/` et `.zip` sous Windows x64 ;
- dossier et `.tar.gz` propres à l’architecture sous macOS.

L’assemblage refuse d’écraser une sortie existante. Pour une autre livraison :

```bash
python -m D2IC_GUI.build_portable --output /chemin/vers/livraisons --name D2IC_GUI-v2
```

Autres options :

```bash
# Versions exactes d’un précédent paquet :
python -m D2IC_GUI.build_portable --constraints /ancien/paquet/requirements.lock

# Dossier autonome sans compression :
python -m D2IC_GUI.build_portable --no-archive

# Exécutable uv situé hors du PATH :
python -m D2IC_GUI.build_portable --uv /chemin/vers/uv
```

Le premier assemblage résout les versions disponibles ; le fichier
`requirements.lock` produit conserve toutes les versions installées. Pour
reconstruire le même environnement, fournir ce fichier comme contraintes et
conserver les mêmes sources et la même version de CPython (`--python 3.12.x`).

## Utiliser le paquet

### Assembler un ZIP Windows depuis Linux ou macOS

```bash
python -m D2IC_GUI.build_windows
```

Ce second script télécharge un véritable CPython Windows x64 et résout les
wheels pour Windows/Python 3.12. Il inclut OpenCV headless et les DLL Microsoft
C++ nécessaires à JAX, placées près de `python.exe`. Il produit seulement
`dist/D2IC_GUI-cpu-windows-amd64.zip` ; le dossier intermédiaire reste temporaire.

Ce parcours ne peut pas exécuter les binaires Windows sur le constructeur
Linux/macOS. Les contrôles portent sur les tags des wheels, les signatures PE
x64 et l’absence des dépendances GPU. Le manifeste porte explicitement
`validated_on_windows = false`.

Sur Windows, extraire **tout** le ZIP puis lancer `Verifier_D2IC_GUI.cmd`.
Cette vérification teste les imports, le JIT CPU, Gmsh, les actifs et un worker
DIC cubique complet ; elle écrit `validation-windows.json` et
`validation-windows.log`. Si elle réussit, ouvrir `D2IC_GUI.cmd`.
Une exécution Windows reste nécessaire avant de déclarer le paquet validé sur
un système cible. Le script natif `build_portable.py` exécuté sous Windows
réalise directement cette validation avant archivage.

Extraire l’archive entière, puis lancer :

- Linux : `D2IC_GUI.sh` ;
- Windows : `D2IC_GUI.cmd` ;
- macOS : `D2IC_GUI.command`.

Le lanceur force JAX sur CPU, choisit un port libre sur `127.0.0.1` et ouvre le
navigateur après réception d’une réponse HTTP. Garder sa console ouverte ;
Ctrl+C arrête le serveur. Fermer seulement le navigateur ne ferme pas le
serveur ni les calculs actifs.

Un dossier d’étude et les options peuvent être passés au lanceur :

```bash
./D2IC_GUI.sh "/chemin/avec espaces/mon_etude" --no-browser --port 8765
```

Enregistrer les études et résultats dans un dossier utilisateur accessible en
écriture, séparé de l’installation.

## Contenu et contrôles

Les sources des projets sont copiées temporairement. Leurs dépendances
`opencv-python` sont remplacées par `opencv-python-headless` **dans ces copies**,
puis les quatre paquets sont construits et installés avec leurs dépendances.
Les dépôts D2IC et DICTHFusion restent inchangés. Le `pyproject.toml` GUI est
destiné à ce parcours d’assemblage avec les métadonnées scientifiques adaptées.
Les modules d’exécution résident dans `src/D2IC_GUI/`. Pour les utiliser depuis
le workspace, installer les paquets scientifiques et le GUI en mode éditable
comme indiqué dans la commande de construction ; les lanceurs du paquet
autonome continuent d’utiliser `python -m D2IC_GUI.desktop`.

Les tests et caches Python sont retirés du runtime, ainsi que les en-têtes et
archives statiques de développement CPython. La base terminfo, inutilisée par le GUI, est retirée pour éviter les collisions de noms différant seulement par la casse sur certains volumes. Les métadonnées et licences des
bibliothèques sont conservées. Le script ne réutilise pas le virtualenv du
développeur et n’embarque pas les bibliothèques CUDA.

Avant archivage, le paquet est déplacé hors de son emplacement de construction
et vérifié avec son interpréteur isolé (`-I`) : dépendances cohérentes, OpenCV
sans GUI, JAX CPU/JIT, maillage Gmsh, actifs web et vrai worker DIC cubique sur
deux images identiques, avec déplacement attendu nul.

`build-manifest.json` conserve les versions, le système, l’architecture, la libc,
les empreintes des sources préparées et la taille du dossier. Un échec après
déplacement produit `BUILD_FAILED.txt` : ce dossier ne doit pas être distribué.

## Limites de portabilité

Construire séparément pour chaque OS et architecture. La validation complète
réalisée ici concerne Linux x86_64 ; Windows et macOS doivent être éprouvés sur
leurs machines cibles, y compris lancement, calcul, arrêt et reprise.

Sous Linux, construire sur la plus ancienne distribution visée et vérifier les
versions de glibc. Le script utilise `ldd` pour embarquer les dépendances natives
de Gmsh autres que glibc ; si une bibliothèque manque sur la machine de
construction, il s’arrête et affiche son nom (par exemple `libGLU.so.1`, paquet
Debian/Ubuntu `libglu1-mesa`). Copier ces bibliothèques ne rend pas une archive
compatible avec une glibc plus ancienne. Un essai sur une machine propre reste
nécessaire pour définir les versions de systèmes officiellement supportées.

Références des outils : [Python géré par uv](https://docs.astral.sh/uv/guides/install-python/),
[OpenCV headless](https://pypi.org/project/opencv-python-headless/).
