"""Source unique de vérité pour la version du package."""

__version__ = "0.1.0rc4"
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
