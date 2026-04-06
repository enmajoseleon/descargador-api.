import httpx
import yt_dlp
import asyncio
import random
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- BLINDAJE DE RECURSOS PARA RENDER ---
executor = ThreadPoolExecutor(max_workers=5)
extraction_semaphore = asyncio.Semaphore(3)

UA_GLOBAL = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

async def stream_video(url: str, headers: dict, cookies: dict) -> AsyncGenerator[bytes, None]:
    """Transmisión de bytes con bypass de sesión."""
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, limits=limits, cookies=cookies) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    print(f"❌ Error CDN: {response.status_code}")
                    return
                async for chunk in response.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
        except Exception as e:
            print(f"⚠️ Error Stream: {e}")

def extraer_info_tank(url: str):
    """Extracción optimizada para buscar el video 'limpio'."""
    ydl_opts = {
        # 'best' ayuda a que yt-dlp traiga la lista completa de formatos
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'cachedir': False,
        'no_check_certificate': True,
        'user_agent': UA_GLOBAL,
        'http_headers': {
            'Referer': 'https://www.tiktok.com/',
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
async def descargar_video(url: str = Query(...)):
    async with extraction_semaphore:
        try:
            loop = asyncio.get_event_loop()
            info, cookies_vuelo = await loop.run_in_executor(executor, extraer_info_tank, url)
            
            video_url = None
            
            # --- LÓGICA DE FILTRADO ANTI-MARCA DE AGUA ---
            if 'formats' in info:
                # Buscamos de mejor a peor calidad (reversed)
                for f in reversed(info['formats']):
                    f_id = f.get('format_id', '').lower()
                    vcodec = f.get('vcodec', 'none')
                    f_url = f.get('url')

                    # Saltamos si es solo audio o no tiene URL
                    if vcodec == 'none' or not f_url:
                        continue

                    # EL FILTRO: TikTok suele meter 'watermark' o 'download' en el ID del video con logo
                    # Los formatos 'h264' o 'bytevc1' sin esas palabras suelen ser los limpios
                    if 'watermark' not in f_id and 'download' not in f_id:
                        video_url = f_url
                        print(f"✅ Formato limpio detectado: {f_id}")
                        break
                
                # Si el filtro falló, usamos el mejor disponible por defecto
                if not video_url:
                    video_url = info['formats'][-1]['url']
            else:
                video_url = info.get('url')

            if not video_url:
                raise HTTPException(status_code=404, detail="No se encontró URL válida")

            # Headers de simulación
            is_tk = 'tiktok' in url.lower()
            headers_bypass = {
                'User-Agent': UA_GLOBAL,
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Referer': 'https://www.tiktok.com/' if is_tk else 'https://www.instagram.com/',
                'Range': 'bytes=0-', 
            }

            if info.get('http_headers'):
                headers_bypass.update(info['http_headers'])

            return StreamingResponse(
                stream_video(video_url, headers_bypass, cookies_vuelo),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "attachment; filename=video_emmanuel.mp4",
                    "Accept-Ranges": "bytes"
                }
            )
            
        except Exception as e:
            print(f"🔥 Error: {str(e)}")
            raise HTTPException(status_code=500, detail="Error en el motor")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)