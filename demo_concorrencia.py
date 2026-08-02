"""Item 6 da Etapa 2 pela linha de comando.

Roda os três cenários de orm/concorrencia.py e imprime os logs. Serve para a
demonstração em vídeo, quando mostrar o terminal é mais direto do que abrir a
interface.

Uso, com o banco no ar:

    python demo_concorrencia.py

A mesma simulação está em POST /etapa2/concorrencia/simular e na aba
Concorrência do frontend.
"""

from __future__ import annotations

import sys

from concorrencia import simular

LARGURA = 78


def imprimir_cenario(cenario: dict) -> None:
    print()
    print("=" * LARGURA)
    print(cenario["cenario"].upper())
    print("=" * LARGURA)
    print(cenario["descricao"])
    print()
    print(f"{'instante':>10}  {'ator':<12}  mensagem")
    print("-" * LARGURA)
    for linha in cenario["log"]:
        print(f"{linha['instante']:>10}  {linha['ator']:<12}  {linha['mensagem']}")
    print("-" * LARGURA)
    print("Desfecho:", cenario["desfecho"])
    print("Conflito evitado:", "sim" if cenario["conflito_evitado"] else "NÃO")


def main() -> int:
    print("Simulação de concorrência - Etapa 2")
    print("Duas transações disputando a mesma escala, três estratégias.")

    try:
        resultado = simular()
    except Exception as erro:  # noqa: BLE001 - mensagem direta para quem roda o script
        print()
        print("Falhou ao conversar com o banco:", erro)
        print("O PostgreSQL está no ar? Suba com: docker compose up -d")
        return 1

    for cenario in resultado["cenarios"]:
        imprimir_cenario(cenario)

    print()
    todos_ok = all(c["conflito_evitado"] for c in resultado["cenarios"])
    print("Resumo:", "os três cenários terminaram como esperado" if todos_ok
          else "algum cenário não terminou como esperado, ver os logs acima")
    return 0 if todos_ok else 2


if __name__ == "__main__":
    sys.exit(main())
