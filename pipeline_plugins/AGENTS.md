# Example stage plugins

Read docs/STAGE_PLUGINS.md. These are Saber processing plugins, not Codex plugins
and not the legacy before/after plugins under plugins/.

Each plugin implements only its chosen execute port. Do not add route/provider
branches to install one. No automatic directory discovery; only trusted explicit
factory configuration may load code. Examples must never contain credentials,
silently fake model inference, or download models when imported.
