from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.procedimento_realizado import (
    ProcedimentoRealizadoCreate, ProcedimentoRealizadoRead,
    ProcedimentoRealizadoDetalhado, ProcedimentoRealizadoBase
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


@router.get("/procedimentos-realizados/", response_model=list[ProcedimentoRealizadoDetalhado])
def listar_procedimentos_realizados(
    id_atendimento: int | None = None,
    id_procedimento: int | None = None,
    faturado: bool | None = None,
    db: Session = Depends(get_db),
):
    """
    Lista os procedimentos realizados com o nome do procedimento (JOIN).
    Aceita filtros opcionais: id_atendimento, id_procedimento e faturado.
    """
    sql = """
        SELECT pr.id_atendimento, pr.id_procedimento, pr.quantidade,
               pr.tempo_real_minutos, pr.observacao, pr.faturado,
               p.nome AS nome_procedimento
        FROM procedimento_realizado pr
        INNER JOIN procedimento p ON p.id_procedimento = pr.id_procedimento
    """
    condicoes, params = [], {}
    if id_atendimento is not None:
        condicoes.append("pr.id_atendimento = :id_atendimento")
        params["id_atendimento"] = id_atendimento
    if id_procedimento is not None:
        condicoes.append("pr.id_procedimento = :id_procedimento")
        params["id_procedimento"] = id_procedimento
    if faturado is not None:
        condicoes.append("pr.faturado = :faturado")
        params["faturado"] = faturado
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY pr.id_atendimento, pr.id_procedimento;"

    result = db.execute(text(sql), params)
    return [dict(row._mapping) for row in result]


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
        text("SELECT faturado FROM procedimento_realizado WHERE id_atendimento = :id_at AND id_procedimento = :id_proc;"),
        {"id_at": id_atendimento, "id_proc": id_procedimento}
    ).first()

    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado."
        )

    # Regra de negócio: procedimento já faturado não pode ser removido
    if verificacao.faturado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este procedimento realizado já foi faturado e não pode ser removido."
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
