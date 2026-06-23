import os
import json
import asyncio
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import AsyncOpenAI
from database import db
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Nibras Fashion Assistant")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r") as f:
        return f.read()

# Configuration for OpenRouter (with credits)
client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

#MODEL_NAME = "qwen/qwen-turbo"
MODEL_NAME = "qwen/qwen3.5-flash-02-23"

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

# Tool definition for Qwen
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search for fashion products in the Nibras store inventory based on keyword, color, price range, brand, category, and status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "The product type and modifier (e.g., 'gamis', 'koko panjang', 'koko anak')."
                    },
                    "feature": {
                        "type": "string",
                        "description": "Material or feature mentioned in description (e.g., 'viscose', 'busui friendly', 'bordir')."
                    },
                    "color": {
                        "type": "string",
                        "description": "Color name in English (e.g., 'BLACK', 'WHITE', 'RED', 'BLUE', 'NAVY')."
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "The maximum price in IDR."
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "The minimum price in IDR. Use with max_price for price ranges."
                    },
                    "size": {
                        "type": "string",
                        "description": "Strict size filter (e.g., 'S', 'M', 'L', 'XL', 'XXL', 'P0', 'L12'). Use this if user specifies a size."
                    },
                    "brand": {
                        "type": "string",
                        "description": "Brand name filter (e.g., 'NBR', 'NBR S', 'NBR L', 'NBR XL')."
                    },
                    "category": {
                        "type": "string",
                        "description": "Category filter (e.g., 'Gamis', 'Koko', 'Tunik', 'Outer', 'Scarf', 'Belt', 'Bag', 'Socks', 'Hijab')."
                    },
                    "sku": {
                        "type": "string",
                        "description": "SKU code filter. Use if user provides a specific SKU."
                    },
                    "in_stock": {
                        "type": "boolean",
                        "description": "Whether to only search for items currently in stock. Defaults to true.",
                        "default": True
                    },
                    "only_new": {
                        "type": "boolean",
                        "description": "If true, only returns new arrival products."
                    },
                    "only_discounted": {
                        "type": "boolean",
                        "description": "If true, only returns products currently on discount."
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["newest", "price_low", "price_high", "name", "stock"],
                        "description": "Sort results. 'newest' (default), 'price_low' (cheapest first), 'price_high' (expensive first), 'name' (alphabetical), 'stock' (most stock first)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default 100, max 200."
                    }
                },
                "required": []
            }
        }
    }
]

SYSTEM_PROMPT = """You are a highly efficient fashion store assistant for Nibras.
Your goal is to help customers find products accurately and quickly.

IMPORTANT: All colors in the database are in ENGLISH. Translate Indonesian colors to English (e.g. 'merah' -> 'RED', 'ungu tua' -> 'BURGUNDY'). If the color is already in English, or it is a unique/specific shade (e.g. 'DUSTY PINK', 'PALE MAUVE'), pass it exactly as the user types it. Convert all color names to UPPERCASE.

STRICT RULES:
1. BE EXTREMELY CONCISE. No conversational fillers.
2. ALWAYS use 'search_products' for inventory queries.
3. LOGIC FOR FILTERS:
   - 'keyword': Product type and sub-type modifiers (e.g., 'gamis', 'koko panjang', 'tunik anak').
   - 'brand': Brand name (e.g., 'NBRS', 'Alnita', 'Haitwo').
   - 'category': Category (e.g., 'Gamis', 'Koko', 'Tunik', 'Outer', 'Scarf', 'Belt', 'Bag', 'Socks', 'Hijab').
   - 'color': Use translated English color in UPPERCASE (e.g., 'maroon' -> 'MAROON', 'merah' -> 'RED').
   - 'size': Strict size filter (e.g., 'XL', 'S').
   - 'min_price' / 'max_price': Price range in IDR (e.g., "150-250rb" -> min_price=150000, max_price=250000).
   - 'feature': Materials or details (e.g., 'viscose', 'busui').
   - 'sku': SKU code if user provides one.
   - 'sort_by': 'newest' (default), 'price_low', 'price_high', 'name', 'stock'.
   - 'limit': Max results (default 100, max 5000).
4. When products are found, say "Berikut adalah produk yang tersedia:" and stop.
5. If no products are found, explain briefly.
"""

async def chat_streamer(messages):
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + [m.model_dump() for m in messages],
            tools=TOOLS,
            stream=False 
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls

        # 2. Handle Tool Calls
        if tool_calls:
            messages_with_tools = [{"role": "system", "content": SYSTEM_PROMPT}] + [m.model_dump() for m in messages]
            messages_with_tools.append(message)

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                print(f"Calling tool: {function_name} with {function_args}")
                
                if function_name == "search_products":
                    limit_val = function_args.get("limit", 5000)
                    if limit_val and limit_val > 10000:
                        limit_val = 200
                    results = db.search_products_with_prediction(
                        keyword=function_args.get("keyword"),
                        color=function_args.get("color"),
                        max_price=function_args.get("max_price"),
                        min_price=function_args.get("min_price"),
                        in_stock=function_args.get("in_stock", True),
                        only_new=function_args.get("only_new", False),
                        only_discounted=function_args.get("only_discounted", False),
                        size=function_args.get("size"),
                        feature=function_args.get("feature"),
                        brand=function_args.get("brand"),
                        category=function_args.get("category"),
                        sku=function_args.get("sku"),
                        limit=limit_val,
                        sort_by=function_args.get("sort_by", "newest")
                    )
                    
                    # Stream the raw results to the frontend immediately for instant rendering
                    # Skip second LLM call - return products directly (no token usage for response)
                    yield f"data: {json.dumps({'products': results})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

        else:
            # No tool call, just stream the response
            stream = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + [m.model_dump() for m in messages],
                stream=True
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    yield "data: [DONE]\n\n"

@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(chat_streamer(request.messages), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
