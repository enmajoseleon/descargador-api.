import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

# 1. Modelo de datos
class VideoRequest(BaseModel):
    url: str

# 2. Función de validación (Lista Blanca)
def es_url_valida(url_a_validar: str) -> bool:
    # Usamos minúsculas aquí para que el filtro sea infranqueable
    dominios_permitidos = [
        "tiktok.com", "x.com", "twitter.com", 
        "instagram.com", "facebook.com", "fb.watch"
    ]
    return any(dominio in url_a_validar.lower() for dominio in dominios_permitidos)

# 3. Ruta de extracción corregida
@app.post("/extraer")
async def extraer_video(request: VideoRequest):
    # Mantenemos la URL original intacta para no romper los IDs de los videos
    url_original = request.url.strip()
    
    # --- 🛡️ FILTRO DE SEGURIDAD (Validamos en minúsculas) ---
    if not es_url_valida(url_original):
        raise HTTPException(
            status_code=403, 
            detail="Plataforma no soportada o prohibida por seguridad."
        )

    # Configuración de extracción
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 20,
        'retries': 5,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    }

    try:
        # Usamos el loop para que sea asíncrono y no bloquee a otros usuarios
        loop = asyncio.get_running_loop()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 🚀 ¡EXTRACCIÓN CON LA URL ORIGINAL! 
            info = await loop.run_in_executor(
                None, 
                lambda: ydl.extract_info(url_original, download=False)
            )
            
            return {
                "status": "success",
                "titulo": info.get('title', 'Video sin título'),
                "url_descarga": info.get('url'),
                "miniatura": info.get('thumbnail'),
                "plataforma": info.get('extractor_key'),
                "duracion": info.get('duration')
            }
            
    except Exception as e:
        print(f"Error técnico: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail="El video es privado, el link expiró o no pudimos procesarlo."
        )

if __name__ == "__main__":
    import uvicorn
    print("🚀 Motor de Emmanuel: ASÍNCRONO, SEGURO Y PRECISO")
    uvicorn.run(app, host="0.0.0.0", port=8000)