import httpx
import yt_dlp
import asyncio
import random
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- RECURSOS PARA RENDER (512MB RAM) ---
executor = ThreadPoolExecutor(max_workers=5)
extraction_semaphore = asyncio.Semaphore(3)

UA_GLOBAL = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

async def stream_video(url: str, headers: dict, cookies: dict) -> AsyncGenerator[bytes, None]:
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, limits=limits, cookies=cookies) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    print(f"❌ Error CDN: {response.status_code}")
                    return
                async for chunk in response.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
        except Exception:
            pass

def extraer_info(url: str):
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'cachedir': False,
        'no_check_certificate': True,
        'user_agent': UA_GLOBAL,
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        'extractor_args': {
            'tiktok': {
                'web_id': f'734{random.randint(100000000, 999999999)}'
            }
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        cookie_dict = {c.name: c.value for c in ydl.cookiejar}
        return ydl.sanitize_info(info), cookie_dict

@app.get("/descargar")
async def descargar(url: str = Query(...)):
    async with extraction_semaphore:
        try:
            loop = asyncio.get_event_loop()
            info, cookies = await loop.run_in_executor(executor, extraer_info, url)
            
            video_url = None
            is_ig = 'instagram.com' in url.lower()
            is_tk = 'tiktok.com' in url.lower()

            if 'formats' in info:
                # --- FILTRADO POR DOMINIO ---
                blacklist = ['watermark', 'download', 'lite', 'fixed', 'tier', 'watermark_fixed', 'fallback', 'small', 'medium']
                
                # Ordenar por calidad de bitrate (tbr)
                sorted_formats = sorted(
                    [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('url')],
                    key=lambda x: x.get('tbr') or 0,
                    reverse=True
                )

                for f in sorted_formats:
                    f_id = str(f.get('format_id', '')).lower()
                    note = str(f.get('format_note', '')).lower()
                    f_url = f.get('url')

                    if not f_url: continue

                    # Técnica para Instagram: No discriminamos por ID, solo buscamos la mejor calidad
                    if is_ig:
                        video_url = f_url
                        break
                    
                    # Técnica para TikTok: Limpieza total de residuos (Marca de Agua)
                    if is_tk:
                        if 'no watermark' in note or 'nowatermark' in f_id:
                            video_url = f_url
                            break
                        if not any(x in f_id for x in blacklist) and not any(x in note for x in blacklist):
                            video_url = f_url
                            break
                
                # Fallback: Si nada funcionó, agarra el de mayor calidad disponible
                if not video_url and sorted_formats:
                    video_url = sorted_formats[0]['url']
            else:
                video_url = info.get('url')

            if not video_url:
                raise HTTPException(status_code=404)

            # --- HEADERS DE CAMUFLAJE DINÁMICO ---
            headers = {
                'User-Agent': UA_GLOBAL,
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-', 
            }

            # Referer y Origin específicos para burlar el bloqueo de Kashimo (IG)
            if is_ig:
                headers['Referer'] = 'https://www.instagram.com/'
                headers['Origin'] = 'https://www.instagram.com/'
            elif is_tk:
                headers['Referer'] = 'https://www.tiktok.com/'
                headers['Origin'] = 'https://www.tiktok.com/'

            if info.get('http_headers'):
                headers.update(info['http_headers'])

            return StreamingResponse(
                stream_video(video_url, headers, cookies),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "attachment; filename=video_monstruo.mp4",
                    "Accept-Ranges": "bytes"
                }
            )
        except Exception:
            raise HTTPException(status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)