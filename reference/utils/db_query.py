#!/usr/bin/env python3
"""Executa SQL PostgreSQL com as conexoes locais do projeto.

Contrato de uso
---------------
- Execute somente com ``.venv/bin/python utils/db_query.py``.
- ``--profile dbt`` usa ``DBT_IP``, ``DBT_PGPORT``, ``DBT_DATABASE_NAME``,
  ``DBT_USER`` e ``DBT_SENHA``. Use para ``raw_timed_dtw``, ``silver_timed``
  e ``gold_timed``.
- ``--profile subhue`` usa as mesmas variaveis com prefixo ``SUBHUE_``.
  Use para tabelas do app e operacoes fora do dbt.
- O script carrega ``.env`` da raiz sem sobrescrever variaveis exportadas.
- SQL vem de ``stdin`` ou de ``--file CAMINHO``. Nao existe opcao ``--sql``.
- ``--params`` recebe objeto ou lista JSON e passa os valores separadamente
  para ``psycopg2.cursor.execute``.
- Placeholders nomeados: ``%(nome)s`` com objeto JSON.
- Placeholders posicionais: ``%s`` com lista JSON.
- Parametros servem apenas para valores. Nomes de schema, tabela e coluna
  devem constar no SQL e nunca devem ser recebidos de entrada nao confiavel.
- Sem ``--write``, a transacao e somente leitura e termina em rollback.
- Com ``--write``, a transacao permite escrita e executa commit se nao houver
  erro. Nunca use ``--write`` para consultas de leitura.
- ``--timeout-ms`` limita o tempo da consulta; padrao: 30000 ms.
- ``--format`` aceita ``table`` (padrao), ``json`` ou ``csv``.
- Resultados sao carregados integralmente em memoria. Sempre limite consultas
  potencialmente grandes.
- Erro gera mensagem em stderr, rollback e codigo de saida 1.

Exemplos
--------
Leitura dbt com parametro nomeado::

    printf 'SELECT * FROM silver_timed.paciente WHERE paciente_gid = %(gid)s' |
      .venv/bin/python utils/db_query.py --profile dbt \
      --params '{"gid":"00000000-0000-0000-0000-000000000000"}' --format json

Leitura do app por arquivo::

    .venv/bin/python utils/db_query.py --profile subhue \
      --file /tmp/consulta.sql --format csv

Escrita explicita com parametro posicional::

    printf 'UPDATE app.tabela SET ativo = %s WHERE id = %s' |
      .venv/bin/python utils/db_query.py --profile subhue \
      --params '[false,123]' --write

Em caso de duvida, nao adivinhe flags, perfil, variaveis ou sintaxe:
execute ``.venv/bin/python utils/db_query.py --help`` e leia este contrato.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

import psycopg2
from psycopg2.extensions import connection as PgConnection


ROOT_DIR = Path(__file__).resolve().parents[1]
PROFILE_PREFIXES = {
    "dbt": "DBT",
    "subhue": "SUBHUE",
}


def load_dotenv(path: Path) -> None:
    """Carrega .env sem sobrescrever variaveis ja exportadas."""
    if not path.exists():
        return

    with path.open(encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(
                key.strip(),
                value.strip().strip('"').strip("'"),
            )


def connection_config(profile: str) -> dict[str, Any]:
    """Monta configuracao psycopg2 para o perfil solicitado."""
    prefix = PROFILE_PREFIXES[profile]
    env_names = {
        "host": f"{prefix}_IP",
        "port": f"{prefix}_PGPORT",
        "dbname": f"{prefix}_DATABASE_NAME",
        "user": f"{prefix}_USER",
        "password": f"{prefix}_SENHA",
    }
    missing = [name for name in env_names.values() if not os.environ.get(name)]
    if missing:
        raise ValueError(
            "Variaveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )

    config = {key: os.environ[name] for key, name in env_names.items()}
    config["port"] = int(config["port"])
    return config


def parse_params(raw_params: str | None) -> Any:
    """Converte parametros JSON para uso no cursor.execute."""
    if raw_params is None:
        return None
    try:
        params = json.loads(raw_params)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON invalido em --params: {error}") from error
    if not isinstance(params, (dict, list)):
        raise ValueError("--params deve ser objeto JSON ou lista JSON")
    return params


def read_sql(file_path: Path | None, stdin: TextIO) -> str:
    """Le SQL de arquivo ou stdin."""
    sql = file_path.read_text(encoding="utf-8") if file_path else stdin.read()
    if not sql.strip():
        raise ValueError("SQL vazio")
    return sql


def serialize_value(value: Any) -> Any:
    """Converte tipos de banco nao nativos em JSON para texto."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def write_json(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    output: TextIO,
) -> None:
    records = [
        {
            column: serialize_value(value)
            for column, value in zip(columns, row, strict=True)
        }
        for row in rows
    ]
    json.dump(records, output, ensure_ascii=False, indent=2)
    output.write("\n")


def write_csv(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    output: TextIO,
) -> None:
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(rows)


def write_table(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    output: TextIO,
) -> None:
    rendered_rows = [
        ["" if value is None else str(value) for value in row] for row in rows
    ]
    widths = [
        max([len(column), *(len(row[index]) for row in rendered_rows)])
        for index, column in enumerate(columns)
    ]
    output.write(
        " | ".join(column.ljust(width) for column, width in zip(columns, widths))
        + "\n"
    )
    output.write("-+-".join("-" * width for width in widths) + "\n")
    for row in rendered_rows:
        output.write(
            " | ".join(value.ljust(width) for value, width in zip(row, widths))
            + "\n"
        )


def execute_sql(
    connection: PgConnection,
    sql: str,
    params: Any,
    output_format: str,
    output: TextIO,
    timeout_ms: int,
) -> None:
    """Executa SQL e escreve resultado ou contagem de linhas afetadas."""
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
        cursor.execute(sql, params)

        if cursor.description is None:
            output.write(f"{cursor.rowcount} linha(s) afetada(s)\n")
            return

        columns = [description.name for description in cursor.description]
        rows = cursor.fetchall()
        writers = {
            "csv": write_csv,
            "json": write_json,
            "table": write_table,
        }
        writers[output_format](columns, rows, output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa SQL usando credenciais DBT_* ou SUBHUE_*.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_PREFIXES),
        required=True,
        help="Conexao: dbt usa DBT_*; subhue usa SUBHUE_*.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Arquivo SQL. Sem esta opcao, le SQL do stdin.",
    )
    parser.add_argument(
        "--params",
        help='Parametros JSON, ex.: \'{"id": 123}\' ou \'[123]\'.',
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        dest="output_format",
        help="Formato do resultado (padrao: table).",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30_000,
        help="Timeout da consulta em milissegundos (padrao: 30000).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Permite escrita e confirma a transacao. Padrao: somente leitura.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.timeout_ms <= 0:
        parser.error("--timeout-ms deve ser maior que zero")

    try:
        load_dotenv(ROOT_DIR / ".env")
        sql = read_sql(args.file, sys.stdin)
        params = parse_params(args.params)
        connection = psycopg2.connect(**connection_config(args.profile))
        try:
            connection.set_session(readonly=not args.write)
            execute_sql(
                connection=connection,
                sql=sql,
                params=params,
                output_format=args.output_format,
                output=sys.stdout,
                timeout_ms=args.timeout_ms,
            )
            if args.write:
                connection.commit()
            else:
                connection.rollback()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    except (OSError, ValueError, psycopg2.Error) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
