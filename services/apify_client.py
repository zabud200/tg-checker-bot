import aiohttp, asyncio, os

ANALYZE_URL = "https://api.apify.com/v2/acts/s_actors~telegram-channel-analytics/run-sync-get-dataset-items"
SEARCH_URL = "https://api.apify.com/v2/acts/seemuapps~telegram-channel-search/run-sync-get-dataset-items"

async def analyze_channel(username):
    token = os.getenv("APIFY_TOKEN")
    if not token: return {"error": "APIFY_TOKEN не настроен"}
    clean = username.replace("https://t.me/", "").replace("@", "").strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"channels": [clean], "postsToAnalyze": 50}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(ANALYZE_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status not in (200, 201):
                    return {"error": f"Apify error {r.status}"}
                data = await r.json()
                return data[0] if data else {"error": "Канал не найден"}
        except asyncio.TimeoutError:
            return {"error": "Таймаут аналитики"}
        except Exception as e:
            return {"error": str(e)}

async def search_channels(keyword, limit=10):
    token = os.getenv("APIFY_TOKEN")
    if not token: return []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"keywords": [keyword], "maxItems": limit, "includeChats": False}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(SEARCH_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status not in (200, 201): 
                    print(f"Search error: {r.status}")
                    return []
                data = await r.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"Search exception: {e}")
            return []
