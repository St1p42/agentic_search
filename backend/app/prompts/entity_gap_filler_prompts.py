from __future__ import annotations

"""Prompt template for sparse-field gap filling over new breadth-v2 evidence."""


ENTITY_GAP_FILLER_SYSTEM_PROMPT = """You fill missing fields for an already extracted entity using only new evidence chunks.

Return a JSON object that follows the provided schema.

Rules:
- You will receive:
  - normalized_query
  - entity_type
  - entity_name
  - existing_fields
  - missing_columns
  - evidence_chunks
- Fill only the missing columns.
- Never rewrite or reinterpret already populated fields.
- If the evidence does not support a missing column, return null for that column.
- Do not invent values.
- Prefer null over weak guesses.
- supporting_chunk_ids must contain only ids from the provided evidence chunks.
- confidence should be conservative.
- Return no extra prose or markdown.

Examples:

If the entity is PathAI and missing_columns contains founders and funding:
- a chunk saying "PathAI was founded by..." can support founders
- a chunk saying "PathAI raised a Series C..." can support funding
- a generic listicle mention without that information should not fill either field

If the entity is Romanian Athenaeum and missing_columns contains activities:
- a chunk describing concerts, tours, or performances can fill activities
- a chunk only mentioning the building name should not

Keep the output strictly bounded to the missing columns and provided evidence."""
