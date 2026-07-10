from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.atendimento import AtendimentoCreate, AtendimentoRead

router = APIRouter(prefix="/atendimentos", tags=["Atendimentos"])

@router.post("/", response_model=AtendimentoRead, status_code=status.HTTP_201_CREATED)
def criar_atendimento(atendimento: AtendimentoCreate, db: Session = Depends(get_db)):
    # 1. Validações manuais de integridade das FKs
    paciente_existe = db.execute(text("SELECT 1 FROM paciente WHERE id_pessoa = :id"), {"id": atendimento.id_paciente}).first()
    if not paciente_existe:
        raise HTTPException(status_code=400, detail="Paciente informado não existe.")

    residente_existe = db.execute(text("SELECT 1 FROM residente WHERE id_profissional = :id"), {"id": atendimento.id_residente}).first()
    if not residente_existe:
        raise HTTPException(status_code=400, detail="Residente informado não existe.")

    preceptor_existe = db.execute(text("SELECT 1 FROM preceptor WHERE id_profissional = :id"), {"id": atendimento.id_preceptor}).first()
    if not preceptor_existe:
        raise HTTPException(status_code=400, detail="Preceptor informado não existe.")

    try:
        query = text("""
            INSERT INTO atendimento (data_hora, duracao_minutos, id_paciente, id_residente, id_preceptor)
            VALUES (:data_hora, :duracao_minutos, :id_paciente, :id_residente, :id_preceptor)
            RETURNING id_atendimento;
        """)
        
        result = db.execute(query, {
            "data_hora": atendimento.data_hora,
            "duracao_minutos": atendimento.duracao_minutos,
            "id_paciente": atendimento.id_paciente,
            "id_residente": atendimento.id_residente,
            "id_preceptor": atendimento.id_preceptor
        })
        
        id_atendimento = result.scalar()
        db.commit()

        return {
            "id_atendimento": id_atendimento,
            "data_hora": atendimento.data_hora,
            "duracao_minutos": atendimento.duracao_minutos,
            "id_paciente": atendimento.id_paciente,
            "id_residente": atendimento.id_residente,
            "id_preceptor": atendimento.id_preceptor
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao registrar atendimento: {str(e)}"
        )


@router.get("/", response_model=list[AtendimentoRead])
def listar_atendimentos(db: Session = Depends(get_db)):

    query = text("""
        SELECT id_atendimento, data_hora, duracao_minutos, id_paciente, id_residente, id_preceptor 
        FROM atendimento;
    """)
    result = db.execute(query)
    return [dict(row._mapping) for row in result]


@router.get("/{id_atendimento}", response_model=AtendimentoRead)
def buscar_atendimento(id_atendimento: int, db: Session = Depends(get_db)):
    query = text("""
        SELECT id_atendimento, data_hora, duracao_minutos, id_paciente, id_residente, id_preceptor 
        FROM atendimento 
        WHERE id_atendimento = :id_atendimento;
    """)
    result = db.execute(query, {"id_atendimento": id_atendimento}).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atendimento não encontrado."
        )
    return dict(result._mapping)


@router.put("/{id_atendimento}", response_model=AtendimentoRead)
def atualizar_atendimento(id_atendimento: int, atendimento: AtendimentoCreate, db: Session = Depends(get_db)):
    verificacao = db.execute(
        text("SELECT 1 FROM atendimento WHERE id_atendimento = :id;"), 
        {"id": id_atendimento}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atendimento não encontrado."
        )

    # Validando se as novas FKs existem
    paciente_existe = db.execute(text("SELECT 1 FROM paciente WHERE id_pessoa = :id"), {"id": atendimento.id_paciente}).first()
    if not paciente_existe:
        raise HTTPException(status_code=400, detail="Paciente informado não existe.")

    residente_existe = db.execute(text("SELECT 1 FROM residente WHERE id_profissional = :id"), {"id": atendimento.id_residente}).first()
    if not residente_existe:
        raise HTTPException(status_code=400, detail="Residente informado não existe.")

    preceptor_existe = db.execute(text("SELECT 1 FROM preceptor WHERE id_profissional = :id"), {"id": atendimento.id_preceptor}).first()
    if not preceptor_existe:
        raise HTTPException(status_code=400, detail="Preceptor informado não existe.")

    try:
        query = text("""
            UPDATE atendimento 
            SET data_hora = :data_hora, 
                duracao_minutos = :duracao_minutos, 
                id_paciente = :id_paciente, 
                id_residente = :id_residente, 
                id_preceptor = :id_preceptor
            WHERE id_atendimento = :id_atendimento;
        """)
        
        db.execute(query, {
            "id_atendimento": id_atendimento,
            "data_hora": atendimento.data_hora,
            "duracao_minutos": atendimento.duracao_minutos,
            "id_paciente": atendimento.id_paciente,
            "id_residente": atendimento.id_residente,
            "id_preceptor": atendimento.id_preceptor
        })
        db.commit()

        return {
            "id_atendimento": id_atendimento,
            "data_hora": atendimento.data_hora,
            "duracao_minutos": atendimento.duracao_minutos,
            "id_paciente": atendimento.id_paciente,
            "id_residente": atendimento.id_residente,
            "id_preceptor": atendimento.id_preceptor
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar atendimento: {str(e)}"
        )


@router.delete("/{id_atendimento}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_atendimento(id_atendimento: int, db: Session = Depends(get_db)):
    verificacao = db.execute(
        text("SELECT 1 FROM atendimento WHERE id_atendimento = :id;"), 
        {"id": id_atendimento}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atendimento não encontrado."
        )

    try:
        query = text("DELETE FROM atendimento WHERE id_atendimento = :id_atendimento;")
        db.execute(query, {"id_atendimento": id_atendimento})
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao deletar atendimento: {str(e)}"
        )
