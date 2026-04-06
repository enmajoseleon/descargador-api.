import httpx
import yt_dlp
import asyncio
import random
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- BLINDAJE DE RECURSOS PARA RENDER (512MB RAM) ---
executor = ThreadPoolExecutor(max_workers=5)
extraction_semaphore = asyncio.Semaphore(3)

# Identidad visual de un navegador real actualizado
UA_GLOBAL = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

@app.get("/")
def home():
    return {"status": "Tanque Operativo 🛡️", "engine": "yt-dlp + HTTPX + CookieJar"}

async def stream_video(url: str, headers: dict, cookies: dict) -> AsyncGenerator[bytes, None]:
    """Transmisión de bytes con persistencia de sesión total."""
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    
    async with httpx.AsyncClient(
        timeout=120.0, 
        follow_redirects=True, 
        limits=limits, 
        cookies=cookies
    ) as client:
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    print(f"❌ Error en CDN: {response.status_code}")
                    return

                # Enviamos trozos de 128KB para fluidez en Flutter
                async for chunk in response.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
        except Exception as e:
            print(f"⚠️ Stream interrumpido: {e}")

def extraer_info_tank(url: str):
    """Extracción con camuflaje de WebID y captura de Cookies."""
    ydl_opts = {
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
        # Bypass de detección: Generamos un ID de sesión aleatorio
        'extractor_args': {
            'tiktok': {
                'web_id': f'734{random.randint(100000000, 999999999)}'
            }
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
        # Extraemos el "tarro de galletas" (Cookies) para que el Stream funcione
        cookie_dict = {c.name: c.value for c in ydl.cookiejar}
            
        return ydl.sanitize_info(info), cookie_dict

@app.get("/descargar")
async def descargar_video(url: str = Query(..., description="Link de TikTok o IG")):
    async with extraction_semaphore:
        try:
            loop = asyncio.get_event_loop()
            # Paso 1: Extracción pesada en hilo secundario
            info, cookies_vuelo = await loop.run_in_executor(executor, extraer_info_tank, url)
            
            # Paso 2: Localizar la URL real del video (sin marca de agua si es posible)
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                # Buscamos el formato de video más pesado (mejor calidad)
                v_formats = [f for f in info['formats'] if f.get('url') and f.get('vcodec') != 'none']
                if v_formats:
                    video_url = v_formats[-1]['url']

            if not video_url:
                raise HTTPException(status_code=404, detail="No se encontró el rastro del video")

            # Paso 3: Headers de Bypass dinámicos
            is_tk = 'tiktok' in url.lower()
            headers_bypass = {
                'User-Agent': UA_GLOBAL,
                'Accept': '*/*',
                'Accept-Encoding': 'identity', # Evita archivos vacíos/comprimidos
                'Referer': 'https://www.tiktok.com/' if is_tk else 'https://www.instagram.com/',
                'Origin': 'https://www.tiktok.com/' if is_tk else 'https://www.instagram.com/',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-', 
            }

            # Inyectamos headers adicionales que yt-dlp considere necesarios
            if info.get('http_headers'):
                headers_bypass.update(info['http_headers'])

            print(f"🚀 Tanque disparando: {url[:40]}...")

            return StreamingResponse(
                stream_video(video_url, headers_bypass, cookies_vuelo),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "attachment; filename=descarga_emmanuel.mp4",
                    "Accept-Ranges": "bytes"
                }
            )
            
        except Exception as e:
            print(f"🔥 Impacto en el tanque: {str(e)}")
            raise HTTPException(status_code=500, detail="Error interno en el motor de extracción")

# Para correr localmente si quieres probar antes de subir a Render
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)