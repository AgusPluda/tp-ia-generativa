"""Prueba de humo (descartable) de Gemini: chat y embeddings. T008.

Uso: python scripts/smoke_gemini.py
Requiere GEMINI_API_KEY en .env. Imprime la respuesta del chat y la longitud del vector.
"""
import os
import sys

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

CHAT_MODEL = "gemini-3.8-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 1536

load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    sys.exit("Falta GEMINI_API_KEY en .env (es obligatoria).")

chat = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0)
print("CHAT:", chat.invoke("Respondé solo con la palabra: listo").content)

emb = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, output_dimensionality=EMBEDDING_DIM)
doc = emb.embed_documents(["El congelamiento de la cuota dura hasta 30 días."], task_type="RETRIEVAL_DOCUMENT")[0]
qry = emb.embed_query("¿Cómo funciona el congelamiento?", task_type="RETRIEVAL_QUERY")
print("DOC dim:", len(doc), "| QUERY dim:", len(qry))
assert len(doc) == len(qry) == EMBEDDING_DIM, f"Dimensión inesperada: {len(doc)} / {len(qry)}"
print("OK")
