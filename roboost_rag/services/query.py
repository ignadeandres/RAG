"""Question answering: retrieve authorised context, then generate a grounded answer."""

from __future__ import annotations

import logging

from roboost_rag.domain import Answer, RetrievedChunk, Role, Source
from roboost_rag.ports import LLM, LLMUnavailableError
from roboost_rag.services.retrieval import RetrievalService

log = logging.getLogger(__name__)

NO_INFORMATION = (
    "No dispongo de información sobre esa consulta en la documentación a la que tienes acceso."
)
UNAVAILABLE = "El servicio no está disponible en este momento. Inténtalo de nuevo en unos minutos."

SYSTEM_PROMPT = """\
Eres el asistente de Recursos Humanos de ROBOOST.
Reglas:
1. Responde ÚNICAMENTE con la información de los fragmentos de contexto proporcionados.
2. Si el contexto no contiene la respuesta, di exactamente: "No dispongo de esa información."
   No inventes datos, cifras ni políticas.
3. Cita los fragmentos que uses con su número entre corchetes, por ejemplo [1] o [2][3].
4. Responde en el mismo idioma que la pregunta, de forma clara y concisa.
5. No menciones documentos, títulos ni información que no aparezcan en el contexto."""


class ServiceUnavailableError(RuntimeError):
    """A dependency is down; the message is safe to show to the user."""


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(
        f"[{i}] (Fuente: {c.title})\n{c.content}" for i, c in enumerate(chunks, start=1)
    )
    return f"Contexto:\n{context}\n\nPregunta: {question}"


def sources_of(chunks: list[RetrievedChunk]) -> list[Source]:
    seen: dict[str, Source] = {}
    for c in chunks:
        seen.setdefault(
            c.document_path,
            Source(title=c.title, path=c.document_path, access_level=c.access_level),
        )
    return list(seen.values())


class QueryService:
    def __init__(self, retrieval: RetrievalService, llm: LLM):
        self.retrieval = retrieval
        self.llm = llm

    def ask(self, question: str, role: Role) -> Answer:
        chunks = self.retrieval.retrieve(question, role)
        if not chunks:
            return Answer(text=NO_INFORMATION)
        try:
            text = self.llm.generate(SYSTEM_PROMPT, build_prompt(question, chunks))
        except LLMUnavailableError:
            log.exception("Fallo al generar la respuesta")
            raise ServiceUnavailableError(UNAVAILABLE) from None
        return Answer(text=text, sources=sources_of(chunks))
