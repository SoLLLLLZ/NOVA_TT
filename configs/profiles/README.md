# Registered model profiles

`byteshape.json`, `glimmer.json`, and `flash.json` pin the exact Wright artifacts, runtime/library hashes, launch arguments and complete settings. Configurations have content-derived profile IDs. Glimmer includes its patched libllama identity and the original DFlash head; Flash includes all four target shards, projector and MTP head plus its MMQ environment.

Production `/profiles` and Astra selection expose only the selected model's llama.cpp profiles. Ollama references are retained solely for standalone comparison scripts. They never run through Optimize. ByteShape/Glimmer each require one L40; Flash requires three on one node. The compute worker verifies assets and runtime before loading. Descriptive settings become writable only with an explicit validated adapter mapping.
