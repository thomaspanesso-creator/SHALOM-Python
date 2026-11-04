@'
import os
import sys
from django.conf import settings
from django.core.management import execute_from_command_line
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from google import genai
from google.genai import types

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='shalom_spa_secret_key_ia_2026',
        ROOT_URLCONF=__name__,
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': ['.'], 
        }],
    )

# CONFIGURACIÓN DE LA IA
# Recuerda abrir este archivo y poner tu API KEY real antes de usar la web
os.environ["GEMINI_API_KEY"] = "AQ.Ab8RN6LvmGKgIpuVwTe3iZMNAgRLOgjJJQ0GEFeIIxm-B5BgmA"
client = genai.Client()

INSTRUCCIONES_ENTREVISTADORA = """
Eres Valeria, reclutadora de SHALOM SPA. Entrevistas a una candidata para el puesto de manicurista.
Haz una sola pregunta corta a la vez. Sé amable y profesional. 
Evalúa su experiencia y actitud. Al cumplir 4 preguntas, despídete cordialmente.
"""

historial_plano = ""

def pagina_entrevista(request):
    global historial_plano
    historial_plano = "" 
    return render(request, 'entrevista.html')

@csrf_exempt
def enviar_respuesta(request):
    global historial_plano
    if request.method == 'POST':
        mensaje_usuario = request.POST.get('mensaje_usuario', '').strip()
        if not mensaje_usuario:
            return JsonResponse({'respuesta_ia': 'Por favor, escribe un mensaje válido.'})
        
        historial_plano += f"\nCandidata: {mensaje_usuario}"
        
        prompt_final = f"""
        {INSTRUCCIONES_ENTREVISTADORA}
        
        Historial de la entrevista hasta ahora:
        {historial_plano}
        
        Valeria:"""
        
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt_final,
            )
            pregunta_ia = response.text.strip()
            historial_plano += f"\nValeria: {pregunta_ia}"
            return JsonResponse({'respuesta_ia': pregunta_ia})
        except Exception as e:
            return JsonResponse({'respuesta_ia': f"Error con la IA: {str(e)}"})
            
    return JsonResponse({'respuesta_ia': 'Método no permitido'}, status=405)

from django.urls import path
urlpatterns = [
    path('', pagina_entrevista),
    path('enviar_respuesta/', enviar_respuesta),
]

if __name__ == '__main__':
    # LISTA PLANA SIN SYS.ARGV PARA EVITAR EL ERROR DE WINDOWS
    execute_from_command_line(['entrevista_django.py', 'runserver', '8000', '--nothreading'])
'@ | Out-File -FilePath entrevista_django.py -Encoding utf8
