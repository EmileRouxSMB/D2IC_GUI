# D2IC_GUI — catalogue des paramètres et configuration d’étude

`src/D2IC_GUI/parameters.toml`, à côté de `schema.py` dans le paquet source, décrit les paramètres de l’application. Il est lu au démarrage du serveur ; `/api/schema` fournit ses métadonnées au navigateur, qui génère le panneau de la vue active. Ce fichier est inclus dans le paquet Python et les constructions portables.

Le `config.toml` de chaque **étude** conserve seulement ses valeurs. Les clés absentes reçoivent les défauts du catalogue. Les études existantes gardent leurs valeurs ; leurs clés, unités et défauts restent compatibles. Les réglages visuels (zoom, largeur des panneaux) restent dans le navigateur.

## Ajouter un paramètre

Ajouter une entrée dans `parameters.toml`, puis redémarrer le serveur et recharger le GUI :

```toml
[[parameters]]
key = "dic.nouveau_seuil"
label = "Nouveau seuil"
type = "float"
default = 0.05
minimum = 0.0
view = "Réglages DIC"
group = "Solveur DIC"
help = "Décrire ici le rôle numérique et les hypothèses du seuil."
```

Le paramètre apparaît automatiquement, reçoit son défaut dans les anciennes études et est validé, sauvegardé puis relu sans ajout de code de formulaire. Sa prise en compte dans un nouvel algorithme nécessite aussi de le raccorder à cet algorithme : le catalogue ne modifie pas les équations du moteur D2IC.

## Métadonnées

| Propriété | Signification |
| --- | --- |
| `key` | Clé TOML `section.parametre`, unique ; deux niveaux, noms minuscules et `_`. |
| `label` | Nom affiché dans le GUI. |
| `type` | Type explicite qui détermine le contrôle et la validation. |
| `default` | Valeur par défaut du même type ; visible dans le GUI et utilisée par Réinitialiser. |
| `help` | Description contextuelle affichée par `(i)`, avec la clé TOML. |
| `view` | Onglet d’accès. |
| `choices` | Liste facultative de chaînes autorisées. |
| `unit`, `minimum` | Unité affichée et borne numérique inférieure facultatives. |
| `group`, `order` | Sous-groupe facultatif et ordre numérique (0 par défaut). |
| `view_dic` | Onglet alternatif en parcours DIC seule, par exemple pour la cadence VIS. |
| `hidden` | `true` pour les valeurs internes ou pilotées par une interaction spécialisée. Défaut `false`. |
| `readonly` | `true` désactive la saisie, le navigateur et la réinitialisation. Défaut `false`. Les invariants scientifiques restent validés côté serveur. |
| `picker` | Filtre facultatif du navigateur : `directory`, `image`, `mask`, `registration`, `file`. |

Les propriétés obligatoires sont `key`, `label`, `type`, `default`, `view`, `help`.

| Type | Valeur TOML | Widget |
| --- | --- | --- |
| `string` | Chaîne | Champ texte ; liste déroulante si `choices` est renseigné. |
| `integer` | Entier | Saisie numérique, pas 1. |
| `float` | Réel | Saisie numérique, pas libre ; un entier saisi est converti en réel. |
| `boolean` | Booléen | Case à cocher. |
| `directory` | Chemin chaîne | Champ et bouton Parcourir pour un dossier. |
| `file` | Chemin chaîne | Champ et bouton Parcourir pour un fichier, filtré par `picker` si présent. |
| `array` | Tableau | Saisie JSON ; sélection multiple si `choices` est renseigné. |

Exemple de sélection multiple :

```toml
[[parameters]]
key = "preferences.canaux"
label = "Canaux"
type = "array"
default = ["VIS"]
choices = ["VIS", "TH"]
view = "Export"
help = "Sélectionner un ou plusieurs canaux avec Ctrl/Cmd ou Maj."
```

Onglets disponibles : `VIS`, `ROI`, `Échelle`, `Réglages DIC`, `Thermique`, `Synchro`, `Job Manager`, `Résultats`, `Export`. `Global` désigne les paramètres de la barre d’étude, actuellement masqués dans le panneau. Créer un nouvel onglet avec sa propre vue centrale nécessite de compléter la navigation du GUI.

`thermal_sections` indique les tables réservées au parcours couplé. Une nouvelle étude DIC les omet ; un passage temporaire du mode couplé au mode DIC conserve les valeurs TH enregistrées. Le catalogue masque les exclusions de séquences (gérées dans les tables d’images), les valeurs de morphologie historiques et le masque final calculé. Leur affichage reste configurable par `hidden` ; les interactions scientifiques existantes (ROI, segment d’échelle, calibration) restent spécialisées.

Les choix invalides, clés dupliquées, types ou défauts incohérents et onglets inconnus sont rejetés au chargement du catalogue. Les contraintes entre paramètres (échelle confirmée pour mm, PVD exigeant VTU, etc.) restent dans `schema.validate`.
