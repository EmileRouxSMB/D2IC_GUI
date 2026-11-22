# Repères de maintenance — D2IC_GUI

## Où lire

- [README](README.md) : installation et architecture ; [manuel](docs/MANUEL_UTILISATION.md) : opérations utilisateur.
- [Contrats](docs/INTEGRATION_CONTRACTS.md) : hypothèses, équations, unités et intégration D2IC/DICTHFusion.
- [Résultats](docs/RESULT_MODEL.md) : stockage, reprise et exports ; [catalogue](docs/CONFIG_SCHEMA.md) : ajout de paramètres.
- [Spécifications](docs/SPEC_TECHNIQUE.md) et [feuille de route](docs/ROADMAP_DEV.md) : responsabilités et limites de validation.

## Où modifier

| Emplacement | Responsabilité |
| --- | --- |
| `src/D2IC_GUI/schema.py`, `parameters.toml`, `project.py` | Catalogue, validation et configuration persistée. |
| `imaging.py`, `roi.py`, `readiness.py` dans le paquet | Images, masques, empreintes et préparation sans créer de run. |
| `dic_run.py`, `worker.py`, `thermal.py` dans le paquet | Snapshots, processus, fusion et exports. |
| `results.py`, `server.py` dans le paquet | Consultation scientifique puis transport HTTP. |
| [static](src/D2IC_GUI/static/memory.md), [tests](tests/memory.md), [examples](examples/memory.md) | Repères propres à ces dossiers. |

Les ressources sont voisines du code dans `src/D2IC_GUI/`. Les constructeurs restent importables sous `D2IC_GUI.build_portable` et `D2IC_GUI.build_windows` ; ils copient les sources avant de modifier leurs métadonnées. Le worker préfère `im_jax` installé, avec repli limité au checkout source.

Les [instructions du workspace](../AGENTS.md) font autorité : décisions scientifiques/architecturales à valider, tests sur demande. Consulter les contrats plutôt que recopier leurs règles dans cette mémoire.
