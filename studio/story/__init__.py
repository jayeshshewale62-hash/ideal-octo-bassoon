"""Module 1 - Story Development Engine.

Status: PLANNED for Milestone 9. This package is an explicit placeholder that marks
the module boundary. It contains no implementation yet. See docs/MODULES.md.

Turns a brief into story.yaml (premise, outline, beat sheet) and a script with
dialogue per character. Works without any LLM (hand-written scripts); the ``llm``
provider is optional assistance.

Boundaries:
    inputs   brief.yaml, optional LLM provider
    outputs  <project>/story/story.yaml, script text (registered as SCRIPT assets)
    depends  studio.core (projects, assets), studio.providers.llm
"""
