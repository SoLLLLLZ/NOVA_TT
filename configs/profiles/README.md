# Registered inference profiles

`byteshape.json` contains the conservative MTP3, preferred MTP5 / temperature 0.75, and untouched Ollama baseline profiles. Profile IDs hash the complete configuration. The manifest pins the model hash and runtime/library hashes from the saved Wright receipts. The compute worker verifies these before loading.

Only ByteShape execution is enabled. Other model references remain in `docs/demo/DEMO_MODELS.md`. Do not turn descriptive source flags into writable settings without an explicit adapter mapping and validation.
