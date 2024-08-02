from pgvector.psycopg import register_vector
import psycopg
import torch
import pickle
import struct

table_name = "rscir_images"
embedding_tuples_path = "/home/ryan/rscir/PatterNet/features/patternnet_remoteclip_tuples.pkl"
dimensions = 768 # this is just what we get from RSCIS

# enable extension
conn = psycopg.connect(
    host="",
    user="",
    password="",
    dbname="",
    port=5432,
    autocommit=True,
)


with conn.cursor() as cursor:
    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
    register_vector(conn)

    # create table
    cursor.execute(f'DROP TABLE IF EXISTS {table_name}')
    cursor.execute(
        f"""
            CREATE TABLE {table_name} (
            filename text,
            url text, 
            embedding vector({dimensions})
            );
        """
    )

    with open(embedding_tuples_path, "rb") as f:
        embedding_tuples = pickle.load(f)

    cursor.executemany(f"INSERT INTO {table_name} VALUES(%s,%s,%s)", embedding_tuples)

print("Complete!")