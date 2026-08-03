from fastapi import FastAPI

from routers.analiticas import router as analiticas_router
from routers.atendimento import router as atendimento_router
from routers.auditoria import router as auditoria_router
from routers.concorrencia import router as concorrencia_router
from routers.consultas import router as consultas_router
from routers.escala import router as escala_router
from routers.internacao import router as internacao_router
from routers.pessoa import (
    router_pacientes,
    router_preceptores,
    router_residentes,
)
from routers.procedimento import router as procedimento_router
from routers.procedimento_realizado import router as procedimento_realizado_router
from routers.unidade import router as unidade_router

app = FastAPI(
    title="Hospital API",
    description="API para gerenciamento hospitalar com SQLAlchemy ORM.",
    version="2.0.0",
)

app.include_router(router_pacientes)
app.include_router(router_preceptores)
app.include_router(router_residentes)
app.include_router(unidade_router)
app.include_router(atendimento_router)
app.include_router(procedimento_router)
app.include_router(procedimento_realizado_router)
app.include_router(escala_router)
app.include_router(internacao_router)
app.include_router(analiticas_router)
app.include_router(auditoria_router)
app.include_router(concorrencia_router)
app.include_router(consultas_router)


@app.get("/")
def root():
    return {
        "message": "API Hospitalar rodando com sucesso! Acesse /docs para abrir a documentação interativa.",
        "orm": "SQLAlchemy",
        "versao": "2.0.0",
    }
