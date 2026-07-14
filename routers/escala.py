from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.escala import EscalaCreate, EscalaRead

router = APIRouter(prefix="/escalas", tags=["Escalas"])

@router.post("/", response_model=EscalaRead, status_code=status.HTTP_201_CREATED)
def criar_escala(escala: EscalaCreate, db: Session = Depends(get_db)):
    # 1. Validações manuais de integridade das FKs
    unidade_existe = db.execute(text("SELECT 1 FROM unidade WHERE id_unidade = :id"), {"id": escala.id_unidade}).first()
    if not unidade_existe:
        raise HTTPException(status_code=400, detail="Unidade informada não existe.")

    residente_existe = db.execute(text("SELECT 1 FROM residente WHERE id_profissional = :id"), {"id": escala.id_residente}).first()
    if not residente_existe:
        raise HTTPException(status_code=400, detail="Residente informado não existe.")

    preceptor_existe = db.execute(text("SELECT 1 FROM preceptor WHERE id_profissional = :id"), {"id": escala.id_preceptor}).first()
    if not preceptor_existe:
        raise HTTPException(status_code=400, detail="Preceptor informado não existe.")

    # 2. Verificação manual da Constraint UNIQUE para evitar erro feio do banco no console
    escala_conflito = db.execute(text("""
        SELECT 1 FROM escala 
        WHERE id_unidade = :id_unidade 
          AND dia_semana = :dia_semana 
          AND turno = :turno 
          AND id_residente = :id_residente;
    """), {
        "id_unidade": escala.id_unidade,
        "dia_semana": escala.dia_semana,
        "turno": escala.turno,
        "id_residente": escala.id_residente
    }).first()
    
    if escala_conflito:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito de Escala: O residente já está escalado nesta unidade, dia e turno."
        )

    try:
        query = text("""
            INSERT INTO escala (id_unidade, dia_semana, turno, id_residente, id_preceptor)
            VALUES (:id_unidade, :dia_semana, :turno, :id_residente, :id_preceptor)
            RETURNING id_escala;
        """)
        
        result = db.execute(query, {
            "id_unidade": escala.id_unidade,
            "dia_semana": escala.dia_semana,
            "turno": escala.turno,
            "id_residente": escala.id_residente,
            "id_preceptor": escala.id_preceptor
        })
        
        id_escala = result.scalar()
        db.commit()

        return {
            "id_escala": id_escala,
            "id_unidade": escala.id_unidade,
            "dia_semana": escala.dia_semana,
            "turno": escala.turno,
            "id_residente": escala.id_residente,
            "id_preceptor": escala.id_preceptor
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao cadastrar escala: {str(e)}"
        )


@router.get("/", response_model=list[EscalaRead])
def listar_escalas(
    id_unidade: int | None = None,
    id_residente: int | None = None,
    id_preceptor: int | None = None,
    dia_semana: str | None = None,
    turno: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Lista as escalas. Aceita filtros opcionais: id_unidade, id_residente,
    id_preceptor, dia_semana e turno.
    """
    sql = """
        SELECT id_escala, id_unidade, dia_semana, turno, id_residente, id_preceptor
        FROM escala
    """
    condicoes, params = [], {}
    if id_unidade is not None:
        condicoes.append("id_unidade = :id_unidade")
        params["id_unidade"] = id_unidade
    if id_residente is not None:
        condicoes.append("id_residente = :id_residente")
        params["id_residente"] = id_residente
    if id_preceptor is not None:
        condicoes.append("id_preceptor = :id_preceptor")
        params["id_preceptor"] = id_preceptor
    if dia_semana:
        condicoes.append("dia_semana = :dia_semana")
        params["dia_semana"] = dia_semana
    if turno:
        condicoes.append("turno = :turno")
        params["turno"] = turno
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY id_unidade, dia_semana, turno;"

    result = db.execute(text(sql), params)
    return [dict(row._mapping) for row in result]


@router.get("/{id_escala}", response_model=EscalaRead)
def buscar_escala(id_escala: int, db: Session = Depends(get_db)):
    query = text("""
        SELECT id_escala, id_unidade, dia_semana, turno, id_residente, id_preceptor 
        FROM escala 
        WHERE id_escala = :id_escala;
    """)
    result = db.execute(query, {"id_escala": id_escala}).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada."
        )
    return dict(result._mapping)


@router.put("/{id_escala}", response_model=EscalaRead)
def atualizar_escala(id_escala: int, escala: EscalaCreate, db: Session = Depends(get_db)):
    verificacao = db.execute(
        text("SELECT 1 FROM escala WHERE id_escala = :id;"), 
        {"id": id_escala}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada."
        )

    # Validando se as novas FKs existem
    unidade_existe = db.execute(text("SELECT 1 FROM unidade WHERE id_unidade = :id"), {"id": escala.id_unidade}).first()
    if not unidade_existe:
        raise HTTPException(status_code=400, detail="Unidade informada não existe.")

    residente_existe = db.execute(text("SELECT 1 FROM residente WHERE id_profissional = :id"), {"id": escala.id_residente}).first()
    if not residente_existe:
        raise HTTPException(status_code=400, detail="Residente informado não existe.")

    preceptor_existe = db.execute(text("SELECT 1 FROM preceptor WHERE id_profissional = :id"), {"id": escala.id_preceptor}).first()
    if not preceptor_existe:
        raise HTTPException(status_code=400, detail="Preceptor informado não existe.")

    # Verificando se a nova configuração de escala não gera conflito com outra escala existente (excluindo ela mesma)
    escala_conflito = db.execute(text("""
        SELECT 1 FROM escala 
        WHERE id_unidade = :id_unidade 
          AND dia_semana = :dia_semana 
          AND turno = :turno 
          AND id_residente = :id_residente
          AND id_escala <> :id_escala;
    """), {
        "id_unidade": escala.id_unidade,
        "dia_semana": escala.dia_semana,
        "turno": escala.turno,
        "id_residente": escala.id_residente,
        "id_escala": id_escala
    }).first()
    
    if escala_conflito:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito de Escala: A nova configuração gera duplicidade para o residente."
        )

    try:
        query = text("""
            UPDATE escala 
            SET id_unidade = :id_unidade, 
                dia_semana = :dia_semana, 
                turno = :turno, 
                id_residente = :id_residente, 
                id_preceptor = :id_preceptor
            WHERE id_escala = :id_escala;
        """)
        
        db.execute(query, {
            "id_escala": id_escala,
            "id_unidade": escala.id_unidade,
            "dia_semana": escala.dia_semana,
            "turno": escala.turno,
            "id_residente": escala.id_residente,
            "id_preceptor": escala.id_preceptor
        })
        db.commit()

        return {
            "id_escala": id_escala,
            "id_unidade": escala.id_unidade,
            "dia_semana": escala.dia_semana,
            "turno": escala.turno,
            "id_residente": escala.id_residente,
            "id_preceptor": escala.id_preceptor
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar escala: {str(e)}"
        )


@router.delete("/{id_escala}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_escala(id_escala: int, db: Session = Depends(get_db)):
    verificacao = db.execute(
        text("SELECT 1 FROM escala WHERE id_escala = :id;"), 
        {"id": id_escala}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada."
        )

    try:
        query = text("DELETE FROM escala WHERE id_escala = :id_escala;")
        db.execute(query, {"id_escala": id_escala})
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao deletar escala: {str(e)}"
        )
