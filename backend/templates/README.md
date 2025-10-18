+Place JSON template files in this directory to expose them via /api/templates.
+
+Each file should be a single JSON object describing the template (id, title,
+description, graph, etc.). Files must end with .json. The API will read all
+*.json files in this directory and return them as a list.
+
+This allows shipping templates from the server instead of the frontend
+public directory so the UI will always fetch templates from /api/templates.
+
