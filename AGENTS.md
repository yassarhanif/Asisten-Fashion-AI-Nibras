# AGENTS.md - Nibras Fashion Chatbot

## Project Structure

```
/main.py         - FastAPI app with Qwen integration, streaming
/database.py    - In-memory SQLite, loads all ~600 Products/*.json
/index.html     - Frontend client
/requirements.txt - Dependencies
/.env            - OPENROUTER_API_KEY

**Model**: `qwen/qwen-turbo` (OpenRouter - paid, fast)

## Color Prediction

The search automatically handles extended colors:
- **Extended colors** (e.g., PALE MAUVE, DUSTY PINK, BABY BLUE): two searches - exact match first, then predicted basic color
- **Basic colors** (e.g., BLACK, PINK, MAUVE): single search
- **Results**: exact matches shown first, predicted color matches second (duplicates allowed)

Extended→Basic mappings: PALE MAUVE→MAUVE, DUSTY PINK→PINK, BABY PINK→PINK, DUSTY BLUE→BLUE, etc.

## Color Mapping

The LLM dynamically translates Indonesian color queries to their broad English equivalents (e.g., 'merah' -> 'RED', 'ungu tua' -> 'BURGUNDY'). The backend database automatically expands broad basic colors into sets of synonymous extended colors (e.g., a query for 'RED' expands to match RED, MAROON, BURGUNDY, BRICK, etc.).

**Rule**: If a color is already in English or is a unique/specific shade (e.g., "DUSTY PINK", "PALE MAUVE"), pass it as-is in UPPERCASE.

## System Prompt Rules

- BE EXTREMELY CONCISE. No conversational fillers.
- Always use `search_products` for stock queries.
- When products found: say "Berikut adalah produk yang tersedia:" then stop.
- If no products: explain briefly.