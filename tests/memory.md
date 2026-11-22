# Vérifications du GUI

Depuis la racine du workspace, après installation des dépendances :

```bash
PYTHONPATH=D2IC_GUI/src:D2IC/src:im_jax JAX_PLATFORMS=cpu python -m pytest -q D2IC_GUI/tests
node --test D2IC_GUI/tests/*.cjs
```

Exécuter les tests seulement sur demande, selon les instructions du workspace.

| Groupe | Contrats couverts |
| --- | --- |
| `test_project_server`, `test_readiness`, `test_parameter_catalog` | Configuration, API, préparation, snapshots et imports du worker. |
| `test_roi_shapes`, `test_result_overlay`, `test_result_sections` | ROI native, binning, calques, champs disponibles, unités et coupes. |
| `test_thermal`, `test_thermal_streaming` | Interpolation, quadrature, référence, lecture progressive et nettoyage après erreur. |
| `test_synthetic_study`, `test_integration_studies` | Générateur analytique et rejeu des parcours DIC/couplé. |
| `test_desktop`, `test_build_portable`, `test_build_windows` | Lanceurs et packaging ; le contrôle statique Windows ne prouve pas son exécution. |
| Tests `.cjs` | Géométrie, interactions et actualisation dans un environnement Node/DOM simulé. |

Les fixtures écrivent dans des dossiers temporaires. Les tests Node ne remplacent pas une revue visuelle ; les performances sur longues séquences et les systèmes cibles demandent des vérifications dédiées. L’état connu est résumé dans la [feuille de route](../docs/ROADMAP_DEV.md).
