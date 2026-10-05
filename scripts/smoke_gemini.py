"""Prueba de humo (descartable) de Gemini: chat y embeddings. T008.

Uso: python scripts/smoke_gemini.py
Requiere GEMINI_API_KEY en .env. Prueba cada modelo de `CHAT_MODELS` (una llamada por modelo)
e imprime la longitud de los vectores de embeddings. Los nombres salen de `gym_agent.config`.
"""
import os
import sys

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from gym_agent.config import CHAT_MODELS, EMBEDDING_DIM, EMBEDDING_MODEL  # también carga .env

if not os.getenv("GEMINI_API_KEY"):
    sys.exit("Falta GEMINI_API_KEY en .env (es obligatoria).")

for modelo in CHAT_MODELS:
    chat = ChatGoogleGenerativeAI(model=modelo, temperature=0)
    print(f"CHAT {modelo}:", chat.invoke("Respondé solo con la palabra: listo").text)

emb = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, output_dimensionality=EMBEDDING_DIM)
doc = emb.embed_documents(["El congelamiento de la cuota dura hasta 30 días."], task_type="RETRIEVAL_DOCUMENT")[0]
qry = emb.embed_query("¿Cómo funciona el congelamiento?", task_type="RETRIEVAL_QUERY")
print("DOC dim:", len(doc), "| QUERY dim:", len(qry))
assert len(doc) == len(qry) == EMBEDDING_DIM, f"Dimensión inesperada: {len(doc)} / {len(qry)}"
print("OK")
