"""Source unique de vérité pour la version du package."""

__version__ = "0.1.0rc6"
# rc5 -> rc6, 2026-09 : marqueur py.typed (PEP 561) ajouté — le classifier
# pyproject.toml "Typing :: Typed" promettait des types fiables aux
# outils (mypy, pyright) sans le fichier marqueur qui rend cette promesse
# vraie pour un package installé. Build réel vérifié de bout en bout :
# `python -m build` + `twine check` passent sur sdist et wheel, le wheel
# ne contient que sinmonto/*.py + py.typed (rien de superflu). Toujours
# pas publié sur PyPI (workflow prêt, déclenchement manuel jamais fait).
# rc4 -> rc5, 2026-09 : 3 bugs réels corrigés, trouvés en audit adversarial
# (Grok, benchmark rc4) — AlphaIndex écartait silencieusement un NOT sur
# champ absent (violation du contrat "sur-ensemble, jamais sous-ensemble"),
# InMemoryFactStore.query() pouvait lever KeyError sur fact_id dupliqué
# (redélivrance amont), _EngineJSONEncoder plantait sur des bytes non-UTF-8.
# Plus 2 corrections de packaging : pyproject.toml resynchronisé (restait à
# rc3, indépendant de _version.py — passé en versioning dynamique hatchling
# pour empêcher toute récidive), et queue.pop(0) -> deque.popleft() dans la
# cascade (O(n) -> O(1), supprime un terme quadratique mesuré sur les
# cascades larges). Voir docs/journal-integration.md pour le détail complet.
# rc3 -> rc4, 2026-09 : cascade de signaux dérivés câblée (file FIFO dans
# evaluate(), max_derived_depth appliqué, causality chaînée par hop,
# RuleTrace.hop/trigger_signal_id) — synthèse de revue croisée 5 IA (Kimi,
# ChatGPT/Luna, Grok, Gemini, Qwen). Fermait le point #1 du tableau "reste
# ouvert" de constitution-noyau.md §12 depuis rc1. Voir
# docs/journal-integration.md pour le détail complet.
# rc2 -> rc3, 2026-08 : re-revue croisée sur rc2 lui-même (ChatGPT, DeepSeek,
# Kimi, Qwen, Grok). Fact._payload et Effect.payload passés de shallow à
# deepcopy (valeur imbriquée mutable après construction). Clarifié en doc :
# la garantie de déterminisme bit-à-bit exclut explicitement trace_id
# (uuid4, non reproductible par nature). CLAUDE.md : le zip rc2 avait
# aplati le symlink vers AGENTS.md en copie plate (même défaut zip que
# celui déjà diagnostiqué sur l'upload initial) — recréé comme vrai
# symlink, zip repackagé avec `-y`. rc1 -> rc2 : voir entrée précédente.
# Reste en pre-release pour la même raison qu'avant.
