"""Source unique de vérité pour la version du package."""

__version__ = "0.1.0rc2"
# rc1 -> rc2, 2026-08 : bugs bloquants de la revue croisée multi-IA corrigés
# (atomicité ctx, causality, validation entity_id/opérateurs/retours
# d'action, copies défensives — voir journal-integration.md). Reste en
# pre-release (pas 0.1.0 nu) : un `pip install sinmonto` sans --pre
# n'installe pas rc2 par défaut, cohérent avec l'esprit "preview technique,
# API 0.x pas encore figée" plutôt qu'une promesse de stabilité. Passage à
# 0.1.0 (sans suffixe) prévu après un premier retour d'usage externe réel.
