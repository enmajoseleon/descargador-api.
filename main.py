import httpx
import yt_dlp
import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- CONFIGURACIÓN DE ARMADURA (RECURSOS) ---
# Limitamos hilos y concurrencia para sobrevivir en los 512MB de Render
executor = ThreadPoolExecutor(max_workers=5)
# El semáforo asegura que solo 3 extracciones ocurran estrictamente en paralelo
extraction_semaphore = asyncio.Semaphore(3)

@app.get("/")
def home():
    return {"status": "Motor Blindado y Monitoreado 🛡️⚡", "autor": "Emmanuel Pro"}

async def stream_video(url: str, headers: dict) -> AsyncGenerator[bytes, None]:
    """Transmisión asíncrona con monitoreo de tamaño y gestión de errores."""
    try:
        # follow_redirects=True es vital para no perder el rastro del video
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code >= 400:
                    print(f"❌ Error CDN: {response.status_code}")
                    return

                # Monitoreo de carga en logs de Render
                content_length = response.headers.get("Content-Length")
                if content_length:
                    size_mb = int(content_length) / (1024 * 1024)
                    print(f"🚀 Transmitiendo video: {size_mb:.2f} MB")
                
                # Enviamos el video por trozos de 128KB para no saturar la RAM
                async for chunk in response.aiter_bytes(chunk_size=1024 * 128):
                    yield chunk
    except Exception as e:
        print(f"⚠️ Interrupción en el flujo: {e}")

def extraer_info_sync(url: str):
    """Extracción en hilo secundario para no bloquear el servidor."""
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'cachedir': False, # No escribe en el disco efímero de Render
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@app.get("/descargar")
async def descargar_video(url: str = Query(..., description="URL de TikTok o Instagram")):
    # El semáforo protege la CPU de Render contra picos de tráfico
    async with extraction_semaphore:
        try:
            loop = asyncio.get_event_loop()
            
            # PASO 1: Extracción segura fuera del hilo principal
            info = await loop.run_in_executor(executor, extraer_info_sync, url)
            
            video_url = info.get('url')
            if not video_url:
                raise HTTPException(status_code=404, detail="URL no encontrada en el motor")

            # PASO 2: Headers de Bypass optimizados para TikTok/Instagram
            custom_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Referer': 'https://www.tiktok.com/' if 'tiktok' in url else 'https://www.instagram.com/',
                'Range': 'bytes=0-',
                'Connection': 'keep-alive'
            }

            # PASO 3: Retorno del flujo directo a tu App en Flutter
            return StreamingResponse(
                stream_video(video_url, custom_headers),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": "attachment; filename=video_pro.mp4",
                    "Content-Type": "video/mp4",
                    "X-Content-Type-Options": "nosniff", # Seguridad para el cliente
                    "Cache-Control": "no-cache" # No guardar basura en caché
                }
            )

        except Exception as e:
            print(f"🔥 Error crítico en API: {e}")
            raise HTTPException(status_code=500, detail="Error procesando la solicitud")

@app.on_event("shutdown")
async def shutdown_event():
    # Apagado limpio del pool de hilos
    executor.shutdown(wait=True)