import httpx
import yt_dlp
import asyncio
import random
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- RECURSOS PARA RENDER ---
executor = ThreadPoolExecutor(max_workers=5)
extraction_semaphore = asyncio.Semaphore(3)

UA_GLOBAL = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

async def stream_video(url: str, headers: dict, cookies: dict) -> AsyncGenerator[bytes, None]:
    # --- LIMPIEZA DE RASTROS PARA EVITAR EL ERROR 500 ---
    headers.pop('Host', None)
    headers.pop('host', None)
    
    # Bajamos la guardia del SSL (verify=False) para que los CDNs de IG/FB no nos reboten
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(
        timeout=120.0, 
        follow_redirects=True, 
        limits=limits, 
        cookies=cookies, 
        verify=False
    ) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    return
                async for chunk in response.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
        except Exception:
            pass

def extraer_info(url: str):
    is_tk = 'tiktok.com' in url.lower()
    
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'cachedir': False,
        'no_check_certificate': True, # Vital para evitar bloqueos de certificados
        'user_agent': UA_GLOBAL,
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    }
    
    # Solo inyectamos el web_id si la batalla es contra TikTok
    if is_tk:
        ydl_opts['extractor_args'] = {
            'tiktok': {
                'web_id': f'734{random.randint(100000000, 999999999)}'
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
                # Ordenamos por TBR (Bitrate) - El video más pesado suele ser el original
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

                    # --- ESTRATEGIA PARA INSTAGRAM (KASHIMO) ---
                    if is_ig:
                        if f.get('ext') == 'mp4' or 'mp4' in f_id:
                            video_url = f_url
                            break
                    
                    # --- ESTRATEGIA PARA TIKTOK (GOJO) ---
                    if is_tk:
                        blacklist = ['watermark', 'download', 'lite', 'fixed', 'tier', 'fallback', 'small']
                        if 'no watermark' in note or 'nowatermark' in f_id:
                            video_url = f_url
                            break
                        if not any(x in f_id for x in blacklist) and not any(x in note for x in blacklist):
                            video_url = f_url
                            break
                
                # Fallback: Si la técnica falla, tomamos el mejor disponible
                if not video_url and sorted_formats:
                    video_url = sorted_formats[0]['url']
            else:
                video_url = info.get('url')

            if not video_url:
                raise HTTPException(status_code=404, detail="No se encontró el video")

            # --- CAMUFLAJE DE HEADERS ---
            headers = {
                'User-Agent': UA_GLOBAL,
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-', 
            }

            if is_ig:
                headers.update({'Referer': 'https://www.instagram.com/', 'Origin': 'https://www.instagram.com/'})
            elif is_tk:
                headers.update({'Referer': 'https://www.tiktok.com/', 'Origin': 'https://www.tiktok.com/'})

            if info.get('http_headers'):
                headers.update(info['http_headers'])

            return StreamingResponse(
                stream_video(video_url, headers, cookies),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "attachment; filename=video_pro.mp4",
                    "Accept-Ranges": "bytes"
                }
            )
        except Exception as e:
            # Mandamos el error detallado a los logs de Render
            print(f"🔴 ERROR CRÍTICO: {str(e)}")
            raise HTTPException(status_code=500, detail="Error interno del monstruo")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)