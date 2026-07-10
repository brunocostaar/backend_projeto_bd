from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.procedimento_realizado import (
    ProcedimentoRealizadoCreate, ProcedimentoRealizadoRead, ProcedimentoRealizadoBase
)

router = APIRouter(tags=["Procedimentos Realizados"])

@router.post("/procedimentos-realizados/", response_model=ProcedimentoRealizadoRead, status_code=status.HTTP_201_CREATED)
def registrar_procedimento_realizado(dados: ProcedimentoRealizadoCreate, db: Session = Depends(get_db)):
    try:
        query = text("""
            INSERT INTO procedimento_realizado 
                (id_atendimento, id_procedimento, quantidade, tempo_real_minutos, observacao, faturado)
            VALUES 
                (:id_atendimento, :id_procedimento, :quantidade, :tempo_real_minutos, :observacao, :faturado);
        """)
        db.execute(query, {
            "id_atendimento": dados.id_atendimento,
            "id_procedimento": dados.id_procedimento,
            "quantidade": dados.quantidade,
            "tempo_real_minutos": dados.tempo_real_minutos,
            "observacao": dados.observacao,
            "faturado": dados.faturado
        })
        db.commit()
        return dados
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao registrar procedimento no atendimento: {str(e)}"
        )


@router.get("/procedimentos-realizados/{id_atendimento}/{id_procedimento}", response_model=ProcedimentoRealizadoRead)
def buscar_procedimento_realizado(id_atendimento: int, id_procedimento: int, db: Session = Depends(get_db)):
    query = text("""
        SELECT id_atendimento, id_procedimento, quantidade, tempo_real_minutos, observacao, faturado
        FROM procedimento_realizado
        WHERE id_atendimento = :id_atendimento AND id_procedimento = :id_procedimento;
    """)
    result = db.execute(query, {
        "id_atendimento": id_atendimento,
        "id_procedimento": id_procedimento
    }).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Esse procedimento não está registrado para este atendimento."
        )
    return dict(result._mapping)


@router.put("/procedimentos-realizados/{id_atendimento}/{id_procedimento}", response_model=ProcedimentoRealizadoRead)
def atualizar_procedimento_realizado(
    id_atendimento: int, 
    id_procedimento: int, 
    dados: ProcedimentoRealizadoBase, 
    db: Session = Depends(get_db)
):
    verificacao = db.execute(
        text("SELECT 1 FROM procedimento_realizado WHERE id_atendimento = :id_at AND id_procedimento = :id_proc;"),
        {"id_at": id_atendimento, "id_proc": id_procedimento}
    ).first()

    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro de procedimento realizado não encontrado."
        )

    try:
        query = text("""
            UPDATE procedimento_realizado
            SET quantidade = :quantidade, 
                tempo_real_minutos = :tempo_real_minutos, 
                observacao = :observacao, 
                faturado = :faturado
            WHERE id_atendimento = :id_atendimento AND id_procedimento = :id_procedimento;
        """)
        db.execute(query, {
            "id_atendimento": id_atendimento,
            "id_procedimento": id_procedimento,
            "quantidade": dados.quantidade,
            "tempo_real_minutos": dados.tempo_real_minutos,
            "observacao": dados.observacao,
            "faturado": dados.faturado
        })
        db.commit()

        return {
            "id_atendimento": id_atendimento,
            "id_procedimento": id_procedimento,
            "quantidade": dados.quantidade,
            "tempo_real_minutos": dados.tempo_real_minutos,
            "observacao": dados.observacao,
            "faturado": dados.faturado
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar: {str(e)}"
        )


@router.delete("/procedimentos-realizados/{id_atendimento}/{id_procedimento}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_procedimento_realizado(id_atendimento: int, id_procedimento: int, db: Session = Depends(get_db)):
    verificacao = db.execute(
        text("SELECT 1 FROM procedimento_realizado WHERE id_atendimento = :id_at AND id_procedimento = :id_proc;"),
        {"id_at": id_atendimento, "id_proc": id_procedimento}
    ).first()

    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado."
        )

    try:
        query = text("""
            DELETE FROM procedimento_realizado 
            WHERE id_atendimento = :id_atendimento AND id_procedimento = :id_procedimento;
        """)
        db.execute(query, {
            "id_atendimento": id_atendimento,
            "id_procedimento": id_procedimento
        })
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao remover associação: {str(e)}"
        )
