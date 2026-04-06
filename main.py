import httpx
import yt_dlp
import asyncio
import random
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- RECURSOS PARA RENDER (Optimización de RAM) ---
executor = ThreadPoolExecutor(max_workers=5)
extraction_semaphore = asyncio.Semaphore(3)

UA_GLOBAL = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

async def stream_video(url: str, headers: dict, cookies: dict) -> AsyncGenerator[bytes, None]:
    # Limpieza de rastros para el CDN de Instagram/Facebook
    headers.pop('Host', None)
    headers.pop('host', None)
    
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    # verify=False es el "Desmantelar" contra errores de SSL en Render
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, limits=limits, cookies=cookies, verify=False) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    return
                async for chunk in response.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
        except Exception:
            pass

def extraer_info(url: str):
    is_ig = 'instagram.com' in url.lower()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'no_check_certificate': True,
        'cachedir': False,
        'user_agent': UA_GLOBAL,
    }
    
    # Si no es Instagram, aplicamos la configuración pesada de TikTok
    if not is_ig:
        ydl_opts['extractor_args'] = {'tiktok': {'web_id': f'734{random.randint(100000000, 999999999)}'}}
        ydl_opts['format'] = 'best'

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

            # --- LÓGICA NINJA: INSTAGRAM (KASHIMO) ---
            if is_ig:
                # Prioridad 1: URL directa de la raíz (el atajo que funcionaba)
                video_url = info.get('url')
                
                # Prioridad 2: Si no está en la raíz, buscar en formatos sin filtros pesados
                if not video_url and 'formats' in info:
                    for f in reversed(info['formats']):
                        f_url = f.get('url')
                        if f.get('vcodec') != 'none' and f_url and ('mp4' in str(f.get('format_id')).lower() or f.get('ext') == 'mp4'):
                            video_url = f_url
                            break

            # --- LÓGICA ROBUSTA: TIKTOK (GOJO) ---
            elif is_tk and 'formats' in info:
                blacklist = ['watermark', 'download', 'lite', 'fixed', 'tier', 'fallback', 'small']
                # Ordenamos por Bitrate (tbr) para asegurar máxima pureza
                sorted_fs = sorted([f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('url')],
                                   key=lambda x: x.get('tbr') or 0, reverse=True)
                
                for f in sorted_fs:
                    f_id, note, f_url = str(f.get('format_id')).lower(), str(f.get('format_note')).lower(), f.get('url')
                    if 'no watermark' in note or 'nowatermark' in f_id:
                        video_url = f_url; break
                    if not any(x in f_id for x in blacklist) and not any(x in note for x in blacklist):
                        video_url = f_url; break
                
                if not video_url and sorted_fs: 
                    video_url = sorted_fs[0]['url']
            
            # Fallback final si ninguna técnica funcionó
            if not video_url:
                video_url = info.get('url')

            if not video_url:
                raise HTTPException(status_code=404, detail="Corte fallido: No se halló URL")

            # --- CONFIGURACIÓN DE HEADERS DE CAMUFLAJE ---
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
                headers={"Content-Disposition": "attachment; filename=video_monstruo.mp4", "Accept-Ranges": "bytes"}
            )
        except Exception as e:
            print(f"🔴 ERROR EN EL MONSTRUO: {str(e)}")
            raise HTTPException(status_code=500, detail="El Santuario Malévolo ha colapsado")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)